#!/usr/bin/env python3
"""PR lockfile advisory delta; full reports remain visible, inherited debt is not a clean audit."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def findings(report, returncode):
    """Reject incomplete/filtered reports and distinguish findings from scanner errors."""
    settings = report['settings']
    if (settings['ignore'] or settings['target_arch'] or settings['target_os']
            or settings['severity'] is not None
            or set(settings['informational_warnings']) != {'unmaintained', 'unsound', 'notice'}):
        raise ValueError('scanner filters or ignored advisories are not permitted')
    dependencies = report['lockfile']['dependency-count']
    if type(dependencies) is not int or dependencies < 0:
        raise ValueError('invalid dependency count')
    vulnerabilities = report['vulnerabilities']
    rows = vulnerabilities['list']
    if (not isinstance(rows, list) or type(vulnerabilities['count']) is not int
            or vulnerabilities['count'] != len(rows)
            or vulnerabilities['found'] is not bool(rows)):
        raise ValueError('inconsistent vulnerability report')
    warnings = report['warnings']
    if not isinstance(warnings, dict) or set(warnings) - {'unmaintained', 'unsound', 'notice'}:
        raise ValueError('unexpected warning categories')
    for category_rows in warnings.values():
        if not isinstance(category_rows, list):
            raise ValueError('invalid warning list')
    blocking = rows + warnings.get('unsound', [])
    if returncode != (1 if blocking else 0):
        raise ValueError(f'scanner exit {returncode} is inconsistent with findings')
    keys = set()
    for row in blocking:
        key = (row['advisory']['id'], row['package']['name'],
               row['package']['version'], row['package']['source'])
        if not all(isinstance(value, str) and value for value in key):
            raise ValueError('incomplete advisory/package identity')
        keys.add(key)
    return keys


def scan(scanner, database, lockfile, output, label):
    if not lockfile.is_file():
        raise ValueError(f'missing {label} lockfile')
    result = subprocess.run(
        [str(scanner), 'audit', '--file', str(lockfile), '--db', str(database),
         '--no-fetch', '--no-yanked', '--deny', 'unsound', '--json'],
        cwd=output, capture_output=True, text=True, timeout=120)
    (output / f'{label}.json').write_text(result.stdout)
    (output / f'{label}.stderr').write_text(result.stderr)
    report = json.loads(result.stdout)
    return report, findings(report, result.returncode)


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    scanner, database = args.scanner.resolve(), args.database.resolve()
    version = subprocess.check_output([str(scanner), '--version'], text=True, timeout=10).strip()
    if version != 'cargo-audit 0.22.2':
        raise ValueError(f'unexpected scanner version: {version}')
    revision = subprocess.check_output(
        ['git', '-C', str(database), 'rev-parse', 'HEAD'], text=True, timeout=10).strip()
    base, base_keys = scan(scanner, database, args.base_lock.resolve(), output, 'base')
    head, head_keys = scan(scanner, database, args.head_lock.resolve(), output, 'head')
    after = subprocess.check_output(
        ['git', '-C', str(database), 'rev-parse', 'HEAD'], text=True, timeout=10).strip()
    if revision != after:
        raise ValueError('advisory database changed between scans')
    introduced = sorted(head_keys - base_keys)
    evidence = {'scanner': version, 'database_commit': revision,
                'base_lock_sha256': hashlib.sha256(args.base_lock.read_bytes()).hexdigest(),
                'head_lock_sha256': hashlib.sha256(args.head_lock.read_bytes()).hexdigest(),
                'introduced': introduced, 'current': sorted(head_keys),
                'no_longer_reported': sorted(base_keys - head_keys)}
    (output / 'comparison.json').write_text(json.dumps(evidence, indent=2) + '\n')
    lines = ['# Rust dependency changes', '',
             f'Scanner: `{version}`; RustSec database: `{revision}`.', '',
             f'New blocking matches: **{len(introduced)}**. '
             f'All current vulnerability/unsoundness matches: **{len(head_keys)}**.', '',
             'This PR-delta verdict is **not a clean full audit**. Unchanged findings remain security debt.',
             'New matches fail; no advisory exclusions, target filters or severity threshold are used.',
             'Reports cover RustSec-matched Cargo.lock packages, not new feature/exposure paths, '
             'Git forks of crates.io packages, native libraries, Ruby/npm, or GHSA-only advisories.', '',
             '## Complete current blocking findings', '']
    for advisory, name, version, source in sorted(head_keys):
        marker = 'NEW' if (advisory, name, version, source) in introduced else 'unchanged'
        lines.append(f'- {marker}: {advisory}, {name} {version}, {source}')
    lines.extend(['', '## Informational notices and maintenance warnings', ''])
    for category in ('notice', 'unmaintained'):
        for row in head['warnings'].get(category, []):
            lines.append(f"- {category}: {row['advisory']['id']}, "
                         f"{row['package']['name']} {row['package']['version']}")
    summary = '\n'.join(lines) + '\n'
    (output / 'summary.md').write_text(summary)
    print(summary)
    return 1 if introduced else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('scanner', 'database', 'base-lock', 'head-lock', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f'Dependency audit could not establish a verdict: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
