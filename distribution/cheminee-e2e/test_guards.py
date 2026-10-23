# Copyright 2021-Present Datadog, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import io
import unittest
import zipfile
from acquire import safe_members


class ArchiveGuards(unittest.TestCase):
    def archive(self, names):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            for name in names:
                archive.writestr(name, 'data')
        buffer.seek(0)
        return zipfile.ZipFile(buffer)

    def test_flat_artifact(self):
        self.assertEqual(safe_members(self.archive(['pilot-manifest.json', 'cheminee-image.tar'])),
                         ['pilot-manifest.json', 'cheminee-image.tar'])

    def test_traversal_absolute_nested_and_duplicate_rejected(self):
        for names in (['../escape'], ['/absolute'], ['nested/file'], ['same', 'same'], []):
            with self.subTest(names=names), self.assertRaises(ValueError):
                safe_members(self.archive(names))


if __name__ == '__main__':
    unittest.main()
