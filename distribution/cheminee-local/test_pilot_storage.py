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

"""Exercise backup failure guards using tiny local files, never Docker."""
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import pilot_storage as storage


def state(name, *, started):
    return {"Id": name, "RestartCount": 0, "HostConfig": {"RestartPolicy": {"Name": "no"}},
            "State": {"Running": False, "OOMKilled": False, "ExitCode": 0,
                      "StartedAt": "one" if started else "0001-01-01T00:00:00Z"},
            "Mounts": [{"Type": "volume", "Name": name + "-data", "Destination": "/var/lib/cheminee"}]}


class StorageTests(unittest.TestCase):
    def test_hardlinks_preserve_bytes_permissions_and_groups_across_representatives(self):
        inventories = []
        with tempfile.TemporaryDirectory() as temporary:
            for original, alias in (("cache/a", "indexes/b"), ("indexes/b", "cache/a")):
                path = Path(temporary) / "hardlinks.tar"
                with tarfile.open(path, "w") as archive:
                    link = tarfile.TarInfo(alias)
                    link.type, link.linkname = tarfile.LNKTYPE, "./" + original
                    link.uid, link.gid, link.mode = 10001, 10001, 0o600
                    archive.addfile(link)  # A forward reference is valid tar input.
                    source = tarfile.TarInfo(original)
                    source.size, source.uid, source.gid, source.mode = 4, 10001, 10001, 0o600
                    archive.addfile(source, io.BytesIO(b"data"))
                inventories.append(storage.archive_inventory(path))
            self.assertEqual(inventories[0], inventories[1])
            self.assertEqual(["cache/a", "indexes/b"], inventories[0]["cache/a"]["hardlink_group"])

    def test_hardlinks_reject_missing_cyclic_directory_and_escaping_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            for target in ("missing", "link", "directory", "../outside", "/absolute"):
                with self.subTest(target=target):
                    path = Path(temporary) / "bad-link.tar"
                    with tarfile.open(path, "w") as archive:
                        directory = tarfile.TarInfo("directory")
                        directory.type = tarfile.DIRTYPE
                        archive.addfile(directory)
                        link = tarfile.TarInfo("link")
                        link.type, link.linkname = tarfile.LNKTYPE, target
                        archive.addfile(link)
                    with self.assertRaises(ValueError):
                        storage.archive_inventory(path)

    def test_archive_inventory_hashes_bytes_and_ownership_without_extracting(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "backup.tar"
            with tarfile.open(path, "w") as archive:
                member = tarfile.TarInfo("./indexes/index.json")
                member.mode, member.uid, member.gid, member.size = 0o600, 10001, 10001, 4
                archive.addfile(member, io.BytesIO(b"data"))
            actual = storage.archive_inventory(path)["indexes/index.json"]
            self.assertEqual((0o600, 10001, 10001, 4), tuple(actual[key] for key in ("mode", "uid", "gid", "bytes")))
            self.assertEqual(64, len(actual["sha256"]))

    def test_archive_inventory_rejects_links_escape_and_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "backup.tar"
            for name, kind, duplicate in [("../outside", tarfile.REGTYPE, False),
                                           ("/absolute", tarfile.REGTYPE, False),
                                           ("link", tarfile.SYMTYPE, False),
                                           ("same", tarfile.REGTYPE, True)]:
                with self.subTest(name=name):
                    with tarfile.open(path, "w") as archive:
                        member = tarfile.TarInfo(name)
                        member.type, member.linkname = kind, "/etc/hostname"
                        archive.addfile(member)
                        if duplicate:
                            archive.addfile(member)
                    with self.assertRaises(ValueError):
                        storage.archive_inventory(path)

    def exercise_restore(self, mutate=None, corrupt=False, nonempty=False, journal_changes=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = root / "original-journal"
            journal.mkdir()
            (journal / "active.json").write_text('{"active":"generation-a"}')
            states = {"original": state("original", started=True), "restored": state("restored", started=False)}
            if mutate:
                mutate(states)
            expected = {"id": "original", "restart_count": 0, "started_at": "one"}
            fixture = {"index.json": {"kind": "file", "bytes": 4, "sha256": "a" * 64}}
            def export(container, path):
                path.write_bytes(b"tiny test archive")
                if path.name == "empty-target.tar":
                    return fixture if nonempty else {}
                if path.name == "restored-data.tar" and corrupt:
                    return {"changed": {"kind": "file", "bytes": 1, "sha256": "b" * 64}}
                return fixture
            def copy_command(*args, **kwargs):
                if journal_changes:
                    (journal / "active.json").write_text("changed")
            with patch.object(storage, "export_data", side_effect=export), patch.object(storage.subprocess, "run", side_effect=copy_command):
                result, proof = storage.restore_offline("original", "restored", expected,
                                                       states.__getitem__, root / "restore", journal)
            self.assertNotEqual(journal, result)
            self.assertEqual(storage.journal_inventory(journal), storage.journal_inventory(result))
            self.assertTrue(proof["empty_target_verified"])
            self.assertNotEqual(proof["source_volume"], proof["restored_volume"])

    def test_restore_keeps_journal_and_volume_destinations_distinct(self):
        self.exercise_restore()

    def test_restore_refuses_live_source_or_previously_started_target(self):
        for change in (lambda states: states["original"]["State"].update(Running=True),
                       lambda states: states["restored"]["State"].update(StartedAt="previously-started"),
                       lambda states: states["restored"].update(Id="original"),
                       lambda states: states["restored"]["Mounts"][0].update(Name="original-data")):
            with self.subTest(change=change), self.assertRaises((ValueError, RuntimeError)):
                self.exercise_restore(mutate=change)

    def test_nonempty_target_corrupt_data_or_changed_journal_fail(self):
        for options in ({"nonempty": True}, {"corrupt": True}, {"journal_changes": True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.exercise_restore(**options)

    def test_journal_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "active.json").symlink_to("/etc/hostname")
            with self.assertRaises(ValueError):
                storage.journal_inventory(directory)

    def test_resource_receipt_keeps_lifetime_scope_and_rejects_oom(self):
        values = {"memory.current": "100", "memory.peak": "200", "memory.max": "4294967296",
                  "memory.events": "oom 0\noom_kill 0", "cpu.max": "200000 100000"}
        def docker(arguments):
            return "42 /var/lib/cheminee" if "du" in arguments else values[Path(arguments[-1]).name]
        receipt = storage.resource_receipt("owned", docker)
        self.assertEqual(42, receipt["data_directory_bytes"])
        self.assertIn("may reset on restart", receipt["note"])
        values["memory.events"] = "oom 1\noom_kill 0"
        with self.assertRaises(RuntimeError):
            storage.resource_receipt("owned", docker)


if __name__ == "__main__":
    unittest.main()
