"""Security decisions, scanner failures and evidence retention."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import dependency_audit as audit
import lru_vendor_provenance as provenance


def report(unsound=False):
    row = {'advisory': {'id': 'RUSTSEC-TEST', 'title': 'test'},
           'package': {'name': 'example', 'version': '1.0.0', 'source': 'registry+test'}}
    return {'settings': {'ignore': [], 'target_arch': [], 'target_os': [], 'severity': None,
                         'informational_warnings': ['notice', 'unmaintained', 'unsound']},
            'lockfile': {'dependency-count': 1},
            'vulnerabilities': {'found': not unsound, 'count': 0 if unsound else 1,
                                'list': [] if unsound else [row]},
            'warnings': {'unsound': [row]} if unsound else {}}


class MemoryTree:
    def __init__(self, files, revision='fixture-revision'):
        self.files, self.revision = files, revision

    def read(self, path):
        data = self.files.get(path)
        if not isinstance(data, bytes):
            raise ValueError(f'missing or nonregular fixture file: {path}')
        return data


def fixture_tree(vendored=False):
    manifest = '[workspace]\n[patch.crates-io]\n'
    lock = 'version = 4\n\n'
    files = {}
    for version, (checksum, dependencies, alias) in provenance.BACKPORTS.items():
        lock += f'[[package]]\nname = "lru"\nversion = "{version}"\n'
        if vendored:
            manifest += f'{alias} = {{ package = "lru", path = "vendor/lru-{version}" }}\n'
        else:
            lock += f'source = "{provenance.REGISTRY}"\nchecksum = "{checksum}"\n'
        lock += f'dependencies = {json.dumps(dependencies)}\n\n'
    lock += ('[[package]]\nname = "other"\nversion = "9.9.9"\n'
             'source = "registry+example"\nchecksum = "unchanged"\n'
             '\n[metadata]\n"an unrelated key" = "preserved verbatim"\n')
    files['quickwit/Cargo.lock'] = lock.encode()
    files['quickwit/Cargo.toml'] = manifest.encode()
    if vendored:
        quickwit = Path(__file__).resolve().parents[2]
        files[provenance.MANIFEST] = (quickwit / 'vendor/lru-provenance.json').read_bytes()
        for version in provenance.BACKPORTS:
            for path in (quickwit / f'vendor/lru-{version}').rglob('*'):
                if path.is_file():
                    files['quickwit/' + path.relative_to(quickwit).as_posix()] = path.read_bytes()
    return MemoryTree(files)


def fixture_args(root, base, head):
    (root / 'base.lock').write_bytes(base.read('quickwit/Cargo.lock'))
    (root / 'head.lock').write_bytes(head.read('quickwit/Cargo.lock'))
    return SimpleNamespace(output=root, scanner=root / 'scanner', database=root,
                           base_lock=root / 'base.lock', head_lock=root / 'head.lock',
                           repository=root, base_ref='base-ref', head_ref='head-ref')


def fake_scan(responses):
    results = iter(responses)

    def scan(scanner, database, lockfile, output, label):
        payload, matches = next(results)
        (output / f'{label}.json').write_text(json.dumps(payload))
        (output / f'{label}.stderr').write_text('')
        return payload, matches

    return scan


class AuditTests(unittest.TestCase):
    def test_vulnerabilities_and_unsoundness_block(self):
        self.assertEqual(audit.findings(report(), 1), audit.findings(report(True), 1))

    def test_source_and_version_are_part_of_identity(self):
        original = audit.findings(report(), 1)
        for field in ('version', 'source'):
            changed = report()
            changed['vulnerabilities']['list'][0]['package'][field] += '-different'
            self.assertTrue(audit.findings(changed, 1) - original)

    def test_filters_and_ignored_advisories_rejected(self):
        for field, value in [('ignore', ['RUSTSEC-TEST']), ('target_arch', ['x86_64']),
                             ('target_os', ['linux']), ('severity', 'high'),
                             ('informational_warnings', ['notice'])]:
            changed = report()
            changed['settings'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                audit.findings(changed, 1)

    def test_inconsistent_status_and_counts_rejected(self):
        for status in (0, 2, -9):
            with self.assertRaises(ValueError):
                audit.findings(report(), status)
        changed = report()
        changed['vulnerabilities']['count'] = 2
        with self.assertRaises(ValueError):
            audit.findings(changed, 1)
        changed = report()
        changed['warnings']['unknown'] = []
        with self.assertRaises(ValueError):
            audit.findings(changed, 1)

    def test_delta_and_complete_evidence(self):
        for introduced in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                tree = fixture_tree()
                args = fixture_args(root, tree, tree)
                keys = audit.findings(report(), 1)
                baseline = (report(), set() if introduced else keys)
                with patch.object(audit.subprocess, 'check_output',
                                  side_effect=['cargo-audit 0.22.2', 'db-sha', 'db-sha']), \
                     patch.object(audit, 'GitTree', return_value=tree), \
                     patch.object(audit, 'scan', side_effect=fake_scan(
                         [baseline, baseline, (report(), keys), (report(), keys)])):
                    self.assertEqual(audit.run(args), int(introduced))
                evidence = json.loads((root / 'comparison.json').read_text())
                self.assertEqual(len(evidence['current']), 1)
                self.assertEqual(len(evidence['introduced']), int(introduced))
                self.assertIn('not a clean full audit', (root / 'summary.md').read_text())

    def test_database_change_and_wrong_scanner_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tree = fixture_tree()
            args = fixture_args(root, tree, tree)
            for versions in (['wrong'], ['cargo-audit 0.22.2', 'before', 'after']):
                with patch.object(audit.subprocess, 'check_output', side_effect=versions), \
                     patch.object(audit, 'GitTree', return_value=tree), \
                     patch.object(audit, 'scan', side_effect=fake_scan([(report(), set())] * 4)), \
                     self.assertRaises(ValueError):
                    audit.run(args)

    def test_missing_lock_and_malformed_output_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / 'missing.lock'
            with self.assertRaises(ValueError):
                audit.scan(root, root, lock, root, 'base')
            lock.touch()
            result = subprocess.CompletedProcess([], 2, 'invalid JSON', 'scanner error')
            with patch.object(audit.subprocess, 'run', return_value=result), \
                 self.assertRaises(ValueError):
                audit.scan(root, root, lock, root, 'base')
            self.assertEqual((root / 'base.stderr').read_text(), 'scanner error')

    def test_required_validation_cannot_be_omitted(self):
        with self.assertRaisesRegex(ValueError, 'required for source validation'):
            audit.run(SimpleNamespace())
        result = subprocess.run(
            [sys.executable, str(Path(audit.__file__)), '--scanner', '/tmp/scanner',
             '--database', '/tmp/db', '--base-lock', '/tmp/base.lock', '--head-lock', '/tmp/head.lock',
             '--output', '/tmp/output'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--repository', result.stderr)
        self.assertIn('--base-ref', result.stderr)
        self.assertIn('--head-ref', result.stderr)

    def test_original_lru_advisory_rows_remain_visible_and_raw_findings_are_kept(self):
        base, head = fixture_tree(), fixture_tree(True)
        original = report()
        rows = [dict(advisory={'id': 'RUSTSEC-2026-0253'},
                     package={'name': 'lru', 'version': version, 'source': provenance.REGISTRY})
                for version in provenance.BACKPORTS]
        original['vulnerabilities'].update(count=2, list=rows)
        original_keys = audit.findings(original, 1)
        raw_keys = audit.findings(report(), 1)
        baseline = report()
        baseline['vulnerabilities'].update(count=3, list=rows + baseline['vulnerabilities']['list'])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = fixture_args(root, base, head)
            with patch.object(audit.subprocess, 'check_output',
                              side_effect=['cargo-audit 0.22.2', 'db-sha', 'db-sha']), \
                 patch.object(audit, 'GitTree', side_effect=[base, head]), \
                 patch.object(audit.subprocess, 'run', side_effect=[
                     subprocess.CompletedProcess([], 1, json.dumps(payload), '')
                     for payload in (baseline, baseline, report(), original)]):
                self.assertEqual(audit.run(args), 0)
            evidence = json.loads((root / 'comparison.json').read_text())
            self.assertEqual({tuple(row) for row in evidence['current']}, original_keys | raw_keys)
            self.assertEqual(evidence['no_longer_reported'], [])
            self.assertEqual(evidence['registry_identity_current'], [list(key) for key in sorted(original_keys)])
            self.assertEqual(evidence['raw_current'], [list(key) for key in sorted(raw_keys)])
            summary = (root / 'summary.md').read_text()
            self.assertEqual(summary.count('RUSTSEC-2026-0253'), 2)
            self.assertIn('does **not** describe the built vendor bytes', summary)
            self.assertEqual((root / 'head.raw.lock').read_bytes(), head.read('quickwit/Cargo.lock'))
            for side in ('base', 'head'):
                for kind in ('raw', 'registry-identity'):
                    prefix = f'{side}.{kind}'
                    self.assertTrue((root / f'{prefix}.stderr').exists())
                    key = 'raw_lock_sha256' if kind == 'raw' else 'registry_identity_lock_sha256'
                    self.assertEqual(evidence['scan_inputs'][side][key],
                                     provenance.sha256((root / f'{prefix}.lock').read_bytes()))
                    self.assertEqual(evidence['scan_inputs'][side][f'{kind}_report_sha256'],
                                     provenance.sha256((root / f'{prefix}.json').read_bytes()))

    def test_projected_scanner_failure_cannot_produce_a_verdict(self):
        tree = fixture_tree(True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = fixture_args(root, tree, tree)
            responses = [subprocess.CompletedProcess([], 1, json.dumps(report()), '')] * 3
            responses.append(subprocess.CompletedProcess([], 2, 'invalid JSON', 'projection scan failed'))
            with patch.object(audit.subprocess, 'check_output',
                              side_effect=['cargo-audit 0.22.2', 'db-sha']), \
                 patch.object(audit, 'GitTree', return_value=tree), \
                 patch.object(audit.subprocess, 'run', side_effect=responses), \
                 self.assertRaises(ValueError):
                audit.run(args)
            self.assertTrue((root / 'head.raw.json').exists())
            self.assertEqual((root / 'head.registry-identity.stderr').read_text(), 'projection scan failed')
            self.assertFalse((root / 'comparison.json').exists())

    def test_run_validates_a_vendored_base_before_scanning(self):
        base, head = fixture_tree(True), fixture_tree(True)
        base.files['quickwit/vendor/lru-0.16.4/src/lib.rs'] += b'// changed base\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = fixture_args(root, base, head)
            with patch.object(audit.subprocess, 'check_output',
                              side_effect=['cargo-audit 0.22.2', 'db-sha']), \
                 patch.object(audit, 'GitTree', side_effect=[base, head]) as reader, \
                 patch.object(audit, 'scan') as scanner, \
                 self.assertRaisesRegex(ValueError, 'vendor file hash differs'):
                audit.run(args)
            reader.assert_called_once_with(root, 'base-ref')
            scanner.assert_not_called()


class ProvenanceTests(unittest.TestCase):
    def project(self, tree):
        return provenance.validate_and_project(tree, tree.read('quickwit/Cargo.lock'))

    def test_original_registry_lock_is_unchanged(self):
        tree = fixture_tree()
        projected, evidence = self.project(tree)
        self.assertEqual(projected, tree.read('quickwit/Cargo.lock'))
        self.assertEqual(evidence['projected_lru_versions'], [])

    def test_verified_vendors_restore_only_original_identity_fields(self):
        tree = fixture_tree(True)
        projected, evidence = self.project(tree)
        self.assertEqual(evidence['projected_lru_versions'], list(provenance.BACKPORTS))
        raw = tree.read('quickwit/Cargo.lock')
        for version, (checksum, _, _) in provenance.BACKPORTS.items():
            insertion = f'source = "{provenance.REGISTRY}"\nchecksum = "{checksum}"\n'.encode()
            self.assertEqual(projected.count(insertion), 1)
            projected = projected.replace(insertion, b'', 1)
        self.assertEqual(projected, raw)
        self.assertEqual(evidence['manifest_sha256'], provenance.MANIFEST_SHA256)

    def test_vendor_file_mutation_addition_removal_and_nonregular_file_fail(self):
        path = 'quickwit/vendor/lru-0.16.4/src/lib.rs'
        for change in ('mutate', 'add', 'remove', 'nonregular'):
            tree = fixture_tree(True)
            if change == 'mutate':
                tree.files[path] += b'// changed\n'
            elif change == 'add':
                tree.files[path + '.extra'] = b'extra'
            elif change == 'remove':
                del tree.files[path]
            else:
                tree.files[path] = None
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.project(tree)

    def test_self_edited_manifest_cannot_bless_changed_files(self):
        tree = fixture_tree(True)
        source = 'quickwit/vendor/lru-0.16.4/src/lib.rs'
        tree.files[source] += b'// changed\n'
        manifest = json.loads(tree.files[provenance.MANIFEST])
        manifest['packages'][0]['files']['src/lib.rs'] = provenance.sha256(tree.files[source])
        tree.files[provenance.MANIFEST] = json.dumps(manifest).encode()
        with self.assertRaisesRegex(ValueError, 'independently pinned'):
            self.project(tree)

    def test_manifest_original_registry_identity_is_independently_pinned(self):
        tree = fixture_tree(True)
        manifest = json.loads(tree.files[provenance.MANIFEST])
        manifest['packages'][0]['checksum'] = 'f' * 64
        tree.files[provenance.MANIFEST] = json.dumps(manifest).encode()
        # Even an intentional manifest repin cannot silently change the original registry identity.
        with patch.object(provenance, 'MANIFEST_SHA256', provenance.sha256(tree.files[provenance.MANIFEST])), \
             self.assertRaisesRegex(ValueError, 'registry identity'):
            self.project(tree)

    def test_missing_provenance_and_unknown_local_or_git_lru_fail(self):
        for change in ('manifest', 'source-less', 'new-version', 'git', 'direct-current'):
            tree = fixture_tree(True)
            lock = tree.files['quickwit/Cargo.lock']
            if change == 'manifest':
                del tree.files[provenance.MANIFEST]
            elif change == 'source-less':
                tree = fixture_tree()
                tree.files['quickwit/Cargo.lock'] = lock
            elif change == 'new-version':
                tree.files['quickwit/Cargo.lock'] = lock.replace(b'0.16.4', b'0.16.5')
            elif change == 'git':
                tree.files['quickwit/Cargo.lock'] = lock.replace(
                    b'version = "0.16.4"', b'version = "0.16.4"\nsource = "git+https://example.test/lru"')
            else:
                tree.files['quickwit/Cargo.lock'] = lock.replace(b'0.16.4', b'0.18.5')
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.project(tree)

    def test_unknown_patch_direct_dependency_and_config_overrides_fail(self):
        cases = [
            ('quickwit/Cargo.toml', b'[workspace]\n[patch.crates-io]\nlru = { path = "elsewhere" }\n'),
            ('quickwit/member/Cargo.toml', b'[dependencies]\nlru = { path = "../elsewhere" }\n'),
            ('quickwit/member/Cargo.toml', b'[dependencies]\ncache = { package = "lru", git = "https://example.test" }\n'),
            ('quickwit/member/Cargo.toml', b'[package]\nname = "lru"\nversion = "0.16.4"\n'),
            ('.cargo/config.toml', b'paths = ["elsewhere"]\n'),
            ('.cargo/config.toml', b'[source.crates-io]\nreplace-with = "vendored"\n'),
            ('.cargo/config.toml', b'[patch.crates-io]\nlru = { path = "elsewhere" }\n'),
            ('.cargo/config.toml', b'[replace]\n"lru:0.16.4" = { path = "elsewhere" }\n'),
        ]
        for path, replacement in cases:
            tree = fixture_tree(True)
            tree.files[path] = replacement
            with self.subTest(path=path, replacement=replacement), self.assertRaises(ValueError):
                self.project(tree)

    def test_duplicate_identity_dependency_and_checksum_mutations_fail(self):
        for change in ('duplicate', 'dependencies', 'checksum'):
            tree = fixture_tree(change != 'checksum')
            lock = tree.files['quickwit/Cargo.lock']
            if change == 'duplicate':
                lock += (f'\n[[package]]\nname = "lru"\nversion = "0.16.4"\nsource = "{provenance.REGISTRY}"\n'
                         f'checksum = "{provenance.BACKPORTS["0.16.4"][0]}"\ndependencies = ["hashbrown 0.16.1"]\n').encode()
            elif change == 'dependencies':
                lock = lock.replace(b'hashbrown 0.16.1', b'hashbrown 0.17.1')
            else:
                lock = lock.replace(provenance.BACKPORTS['0.16.4'][0].encode(), b'f' * 64)
            tree.files['quickwit/Cargo.lock'] = lock
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.project(tree)

    def test_verified_patch_cannot_be_unused_or_missing_from_lock(self):
        for change in ('registry', 'missing'):
            tree = fixture_tree(True)
            lock = tree.files['quickwit/Cargo.lock']
            if change == 'registry':
                insertion = (f'version = "0.16.4"\nsource = "{provenance.REGISTRY}"\n'
                             f'checksum = "{provenance.BACKPORTS["0.16.4"][0]}"').encode()
                lock = lock.replace(b'version = "0.16.4"', insertion)
            else:
                lock = lock.replace(b'name = "lru"\nversion = "0.16.4"',
                                    b'name = "renamed"\nversion = "0.16.4"')
            tree.files['quickwit/Cargo.lock'] = lock
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'must resolve both'):
                self.project(tree)

    def test_each_revision_uses_its_own_vendor_files_and_lock(self):
        base, head = fixture_tree(True), fixture_tree(True)
        self.assertEqual(self.project(base)[0], self.project(head)[0])
        base.files['quickwit/vendor/lru-0.16.4/src/lib.rs'] += b'// changed base\n'
        with self.assertRaises(ValueError):
            self.project(base)
        self.project(head)
        with self.assertRaisesRegex(ValueError, 'does not match'):
            provenance.validate_and_project(head, fixture_tree().read('quickwit/Cargo.lock'))

    def test_git_reader_uses_commit_bytes_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'quickwit').mkdir()
            lock = root / 'quickwit/Cargo.lock'
            lock.write_text('version = 4\n')
            (root / 'quickwit/Cargo.toml').symlink_to('Cargo.lock')
            commands = [('init', '--quiet'), ('add', 'quickwit'),
                        ('-c', 'user.name=Test', '-c', 'user.email=test@example.test',
                         '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'fixture')]
            for command in commands:
                subprocess.run(['git', '-C', str(root), *command], check=True, capture_output=True)
            tree = provenance.GitTree(root, 'HEAD')
            lock.write_text('uncommitted change')
            self.assertEqual(tree.read('quickwit/Cargo.lock'), b'version = 4\n')
            with self.assertRaisesRegex(ValueError, 'not a regular tracked file'):
                tree.read('quickwit/Cargo.toml')


if __name__ == '__main__':
    unittest.main()
