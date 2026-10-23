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

"""Reproduce Ubuntu usrmerge staging with tiny temporary files, without Docker."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from prepare_runtime import USR_MERGE_ALIASES, copy_runtime_libraries, library_destination


class RuntimeLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.filesystem = Path(self.temporary.name) / "builder"
        self.filesystem.mkdir()
        self.root = Path(self.temporary.name) / "runtime"
        self.root.mkdir()
        for name, target in USR_MERGE_ALIASES.items():
            (self.filesystem / target).mkdir(parents=True, exist_ok=True)
            (self.filesystem / name).symlink_to(target, target_is_directory=True)

    def test_resolves_all_expected_directory_aliases(self):
        for name, target in USR_MERGE_ALIASES.items():
            with self.subTest(name=name):
                self.assertEqual(Path(target) / "loader.so.2",
                                 library_destination(Path("/") / name / "loader.so.2", self.filesystem))

    def test_loader_and_soname_names_survive_final_file_symlinks(self):
        libraries = self.filesystem / "usr/lib/x86_64-linux-gnu"
        libraries.mkdir()
        (libraries / "ld-linux-x86-64.so.2").write_bytes(b"loader")
        (self.filesystem / "usr/lib64/ld-linux-x86-64.so.2").symlink_to("../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2")
        (libraries / "libexample.so.1.2.3").write_bytes(b"library")
        (libraries / "libexample.so.1").symlink_to("libexample.so.1.2.3")
        manifest = copy_runtime_libraries({"/lib64/ld-linux-x86-64.so.2", "/lib/x86_64-linux-gnu/libexample.so.1"},
                                         self.root, self.filesystem)
        self.assertEqual(b"loader", (self.root / "usr/lib64/ld-linux-x86-64.so.2").read_bytes())
        self.assertEqual(b"library", (self.root / "usr/lib/x86_64-linux-gnu/libexample.so.1").read_bytes())
        self.assertFalse((self.root / "lib64").exists())
        self.assertFalse((self.root / "lib").exists())
        self.assertFalse((self.root / "usr/lib/x86_64-linux-gnu/libexample.so.1.2.3").exists())
        self.assertEqual("/usr/lib/x86_64-linux-gnu/libexample.so.1.2.3",
                         manifest["/lib/x86_64-linux-gnu/libexample.so.1"]["resolved_source"])

    def test_alias_and_canonical_paths_deduplicate_identical_bytes(self):
        (self.filesystem / "usr/lib/example.so.1").write_bytes(b"same")
        manifest = copy_runtime_libraries({"/lib/example.so.1", "/usr/lib/example.so.1"}, self.root, self.filesystem)
        self.assertEqual(2, len(manifest))
        self.assertEqual(1, len(list(self.root.rglob("*.so.1"))))

    def test_unknown_directory_alias_and_wrong_usrmerge_target_fail(self):
        (self.filesystem / "unexpected").symlink_to("usr/lib", target_is_directory=True)
        with self.assertRaises(ValueError):
            library_destination(Path("/unexpected/library.so.1"), self.filesystem)
        (self.filesystem / "lib64").unlink()
        (self.filesystem / "lib64").symlink_to("usr/lib", target_is_directory=True)
        with self.assertRaises(ValueError):
            library_destination(Path("/lib64/loader.so.2"), self.filesystem)

    def test_differing_bytes_at_a_canonical_destination_fail_before_copy(self):
        (self.filesystem / "usr/lib/first.so.1").write_bytes(b"first")
        (self.filesystem / "usr/lib/second.so.1").write_bytes(b"second")
        with patch("prepare_runtime.library_destination", return_value=Path("usr/lib/collision.so.1")):
            with self.assertRaisesRegex(ValueError, "conflicting runtime libraries"):
                copy_runtime_libraries({"/usr/lib/first.so.1", "/usr/lib/second.so.1"}, self.root, self.filesystem)
        self.assertEqual([], list(self.root.iterdir()))

    def test_existing_destination_is_never_overwritten(self):
        (self.filesystem / "usr/lib/example.so.1").write_bytes(b"library")
        target = self.root / "usr/lib/example.so.1"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"retain")
        with self.assertRaisesRegex(ValueError, "already exists"):
            copy_runtime_libraries({"/lib/example.so.1"}, self.root, self.filesystem)
        self.assertEqual(b"retain", target.read_bytes())

    def test_relative_and_traversing_paths_are_rejected(self):
        for name in ("lib/example.so.1", "/lib/../example.so.1", "/"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                library_destination(Path(name), self.filesystem)


if __name__ == "__main__":
    unittest.main()
