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

"""Offline file-backend backup checks and phase-boundary resource receipts."""
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile

from pilot_provenance import canonical, digest, write_json
from readiness import assert_incarnation, container_incarnation


def archive_inventory(path):
    inventory = {}
    with tarfile.open(path, "r") as archive:
        for member in archive:
            relative = PurePosixPath(member.name)
            name = str(relative)
            if relative.is_absolute() or ".." in relative.parts or name in inventory:
                raise ValueError("backup contains an unsafe or duplicate path")
            if not (member.isfile() or member.isdir() or member.islnk()):
                raise ValueError("backup contains an unsupported file type")
            kind = "hardlink" if member.islnk() else "file" if member.isfile() else "directory"
            entry = {"kind": kind,
                     "mode": member.mode, "uid": member.uid, "gid": member.gid}
            if member.isfile():
                with archive.extractfile(member) as source:
                    entry.update(bytes=member.size, sha256=hashlib.file_digest(source, "sha256").hexdigest())
            if member.islnk():
                target = PurePosixPath(member.linkname)
                if target.is_absolute() or ".." in target.parts:
                    raise ValueError("backup hardlink escapes its archive")
                entry["target"] = str(target)
            inventory[name] = entry
    # Normalize each link group so re-export may choose a different first member.
    # Preserve group membership, bytes and inode metadata without extracting paths.
    groups = {}
    normalized = {}
    for name, entry in inventory.items():
        if entry["kind"] == "directory":
            normalized[name] = entry
            continue
        resolved, visited = name, set()
        while True:
            if resolved in visited or resolved not in inventory:
                raise ValueError("backup hardlink has a cycle or missing target")
            visited.add(resolved)
            target_entry = inventory[resolved]
            if target_entry["kind"] == "file":
                break
            if target_entry["kind"] != "hardlink":
                raise ValueError("backup hardlink target is not a regular file")
            resolved = target_entry["target"]
        if any(entry[key] != target_entry[key] for key in ("uid", "gid", "mode")):
            raise ValueError("backup hardlink inode metadata is inconsistent")
        normalized[name] = dict(target_entry)
        groups.setdefault(resolved, []).append(name)
    for members in groups.values():
        if len(members) > 1:
            for name in members:
                normalized[name]["hardlink_group"] = sorted(members)
    return normalized


def journal_inventory(directory):
    inventory = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError("journal contains an unsupported file type")
        entry = {"kind": "file" if path.is_file() else "directory", "mode": path.stat().st_mode & 0o777}
        if path.is_file():
            entry.update(bytes=path.stat().st_size, sha256=digest(path))
        inventory[str(path.relative_to(directory))] = entry
    return inventory


def export_data(container, archive):
    with archive.open("xb") as output:
        subprocess.run(["docker", "cp", "--archive", f"{container}:/var/lib/cheminee/.", "-"],
                       stdout=output, check=True, timeout=180)
    return archive_inventory(archive)


def require_stopped(container, expected, inspect):
    actual = container_incarnation(inspect(container), stopped=True)
    assert_incarnation(expected, actual)


def restore_offline(source, target, expected_source, inspect, work, journal):
    """Copy only quiesced state; refuse non-empty targets or overlapping writers."""
    if source == target:
        raise ValueError("restore requires a distinct container")
    require_stopped(source, expected_source, inspect)
    target_info = inspect(target)
    if target_info["Id"] == inspect(source)["Id"]:
        raise ValueError("restore requires a distinct container identity")
    if target_info["State"]["Running"] or target_info["State"]["StartedAt"] not in ("", "0001-01-01T00:00:00Z"):
        raise ValueError("restore target must never have been started")
    def volume(info):
        matches = [mount["Name"] for mount in info["Mounts"]
                   if mount["Destination"] == "/var/lib/cheminee" and mount["Type"] == "volume"]
        if len(matches) != 1:
            raise ValueError("pilot must own exactly one named data volume")
        return matches[0]
    original_volume, restored_volume = volume(inspect(source)), volume(target_info)
    if original_volume == restored_volume:
        raise ValueError("restore requires a fresh distinct data volume")
    work.mkdir()
    empty = export_data(target, work / "empty-target.tar")
    if any(name != "." for name in empty):
        raise ValueError("restore target data volume is not empty")
    source_inventory = export_data(source, work / "data.tar")
    if not any(entry["kind"] == "file" for entry in source_inventory.values()):
        raise ValueError("source backup contains no retained data")
    original_journal = journal_inventory(journal)
    backup_journal = work / "journal-backup"
    shutil.copytree(journal, backup_journal)
    restored_journal = work / "journal-restored"
    shutil.copytree(backup_journal, restored_journal)
    if (journal_inventory(backup_journal) != original_journal
            or journal_inventory(restored_journal) != original_journal):
        raise ValueError("restored journal differs from quiesced source")
    with (work / "data.tar").open("rb") as archive:
        subprocess.run(["docker", "cp", "--archive", "-", f"{target}:/var/lib/cheminee"],
                       stdin=archive, check=True, timeout=180)
    restored_inventory = export_data(target, work / "restored-data.tar")
    if restored_inventory != source_inventory:
        raise ValueError("restored file data or permissions differ from backup")
    require_stopped(source, expected_source, inspect)
    final_target = inspect(target)
    if (final_target["Id"] != target_info["Id"] or final_target["State"]["Running"]
            or final_target["State"]["StartedAt"] != target_info["State"]["StartedAt"]):
        raise ValueError("restore target changed before backup validation completed")
    if journal_inventory(journal) != original_journal:
        raise ValueError("source journal changed during backup")
    write_json(work / "data-inventory.json", source_inventory)
    write_json(work / "journal-inventory.json", original_journal)
    return restored_journal, {
        "source_container_id": inspect(source)["Id"], "restored_container_id": target_info["Id"],
        "source_volume": original_volume, "restored_volume": restored_volume,
        "source_journal": str(journal), "restored_journal": str(restored_journal),
        "empty_target_verified": True, "source_stopped_during_backup": True,
        "data_archive_sha256": digest(work / "data.tar"),
        "data_inventory_sha256": hashlib.sha256(canonical(source_inventory)).hexdigest(),
        "journal_inventory_sha256": hashlib.sha256(canonical(original_journal)).hexdigest(),
        "data_files": sum(entry["kind"] == "file" for entry in source_inventory.values()),
        "data_logical_bytes": sum(entry.get("bytes", 0) for entry in source_inventory.values()),
        "restore_method": "quiesced local file data and journal copied into fresh roots; no source replay",
    }


def resource_receipt(container, docker):
    observed = {}
    for name in ("memory.current", "memory.peak", "memory.max", "memory.events", "cpu.max"):
        observed[name] = docker(["exec", container, "cat", f"/sys/fs/cgroup/{name}"])
    events = dict(line.split() for line in observed["memory.events"].splitlines())
    if int(events["oom_kill"]) != 0 or int(events["oom"]) != 0:
        raise RuntimeError("pilot cgroup reports an OOM event")
    observed["data_directory_bytes"] = int(docker(["exec", container, "du", "-sb", "/var/lib/cheminee"]).split()[0])
    observed["note"] = "phase-boundary observation; peaks/events describe the observed cgroup/incarnation lifetime, may reset on restart, and are not isolated phase increments"
    return observed
