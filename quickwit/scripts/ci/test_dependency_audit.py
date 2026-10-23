# Copyright 2021-Present Datadog, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http:#www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Security decisions, scanner failures and evidence retention."""
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import dependency_audit as audit


def report(unsound=False):
    row = {'advisory': {'id': 'RUSTSEC-TEST', 'title': 'test'},
           'package': {'name': 'example', 'version': '1.0.0', 'source': 'registry+test'}}
    return {'settings': {'ignore': [], 'target_arch': [], 'target_os': [], 'severity': None,
                         'informational_warnings': ['notice', 'unmaintained', 'unsound']},
            'lockfile': {'dependency-count': 1},
            'vulnerabilities': {'found': not unsound, 'count': 0 if unsound else 1,
                                'list': [] if unsound else [row]},
            'warnings': {'unsound': [row]} if unsound else {}}


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
                lock = root / 'Cargo.lock'
                lock.write_text('version = 4\n')
                args = SimpleNamespace(output=root, scanner=root / 'scanner', database=root,
                                       base_lock=lock, head_lock=lock)
                keys = audit.findings(report(), 1)
                with patch.object(audit.subprocess, 'check_output',
                                  side_effect=['cargo-audit 0.22.2', 'db-sha', 'db-sha']), \
                     patch.object(audit, 'scan', side_effect=[(report(), set() if introduced else keys),
                                                             (report(), keys)]):
                    self.assertEqual(audit.run(args), int(introduced))
                evidence = json.loads((root / 'comparison.json').read_text())
                self.assertEqual(len(evidence['current']), 1)
                self.assertEqual(len(evidence['introduced']), int(introduced))
                self.assertIn('not a clean full audit', (root / 'summary.md').read_text())

    def test_database_change_and_wrong_scanner_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(output=root, scanner=root, database=root,
                                   base_lock=root, head_lock=root)
            for versions in (['wrong'], ['cargo-audit 0.22.2', 'before', 'after']):
                with patch.object(audit.subprocess, 'check_output', side_effect=versions), \
                     patch.object(audit, 'scan', return_value=(report(), set())), \
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


if __name__ == '__main__':
    unittest.main()
