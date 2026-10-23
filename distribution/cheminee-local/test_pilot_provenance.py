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

"""Small provenance/lifecycle guard tests; no native build or Docker execution."""
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import pilot_provenance as provenance
from finalize_pilot import verify_acceptance, verify_archive, verify_gem
from prepare_runtime import stop_probe
from readiness import checked_restart

REVISION = "a" * 40
BUILD = {"commit_hash": REVISION, "build_target": "x86_64-unknown-linux-gnu", "cargo_pkg_version": "0.9.1"}
VERSION = "0.9.1.pre.pilot.g" + REVISION


def add_file(archive, name, data):
    entry = tarfile.TarInfo(name)
    entry.size = len(data)
    archive.addfile(entry, io.BytesIO(data))


class ProvenanceTests(unittest.TestCase):
    def test_final_manifest_requires_restore_and_catalog_acceptance_gates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("data", "journal"):
                provenance.write_json(root / f"{name}-inventory.json", {"retained": name})
            runtime = {"source_commit": REVISION, "candidate_version": VERSION}
            image = {"Id": "sha256:" + "b" * 64}
            accepted = {"status": "passed", "image_id": image["Id"], **runtime,
                        "catalog_create": {"status": "passed", "rollback_verified": True},
                        "catalog_verify_after_restart": {"status": "passed", "retained_active_verified": True},
                        "catalog_after_restore": {"status": "passed", "restored_rollback_verified": True},
                        "restore": {"empty_target_verified": True, "source_stopped_during_backup": True,
                                    "source_container_id": "old", "restored_container_id": "new",
                                    "source_volume": "old-volume", "restored_volume": "new-volume",
                                    "source_journal": "old-journal", "restored_journal": "new-journal",
                                    "data_inventory_sha256": provenance.digest(root / "data-inventory.json"),
                                    "journal_inventory_sha256": provenance.digest(root / "journal-inventory.json")}}
            verify_acceptance(accepted, image, runtime, root)
            missing = copy.deepcopy(accepted)
            del missing["catalog_after_restore"]
            with self.assertRaises(ValueError):
                verify_acceptance(missing, image, runtime, root)
            shared = copy.deepcopy(accepted)
            shared["restore"]["restored_volume"] = "old-volume"
            with self.assertRaises(ValueError):
                verify_acceptance(shared, image, runtime, root)
            (root / "data-inventory.json").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                verify_acceptance(accepted, image, runtime, root)

    def test_embedded_revision_and_platform_must_match_exactly(self):
        self.assertEqual(VERSION, provenance.verify_build({"build": BUILD}, REVISION))
        for field, value in [("commit_hash", "unknown"), ("commit_hash", REVISION[:7]),
                             ("commit_hash", "b" * 40), ("build_target", "aarch64-unknown-linux-gnu")]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                provenance.verify_build({"build": dict(BUILD, **{field: value})}, REVISION)

    def test_model_pins_equal_native_loader_and_installer(self):
        repository = Path(__file__).resolve().parents[2]
        loader = (repository / "quickwit/tantivy-rdkit-mapper/src/cluster.rs").read_text()
        installer = (repository / "quickwit/tantivy-rdkit-mapper/ci/install-descriptor-model.sh").read_text()
        for name, checksum in provenance.MODEL_FILES.items():
            self.assertIn(f'"{name}"', loader)
            self.assertIn(f'"{checksum}"', loader)
        self.assertIn(provenance.MODEL_ARCHIVE["sha256"], installer)
        self.assertIn(provenance.MODEL_ARCHIVE["url"], installer)

    def test_missing_corrupt_and_escaping_model_assets_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            good = hashlib.sha256(b"model").hexdigest()
            with patch.object(provenance, "MODEL_FILES", {"model": good}):
                with self.assertRaises(ValueError):
                    provenance.verify_models(root)
                (root / "model").write_bytes(b"model")
                provenance.verify_models(root)
                (root / "model").write_bytes(b"corrupt")
                with self.assertRaises(ValueError):
                    provenance.verify_models(root)
                (root / "model").unlink()
                (root / "model").symlink_to("/etc/hostname")
                with self.assertRaises(ValueError):
                    provenance.verify_models(root)

    def test_sdk_must_match_revision_version_generator_and_actual_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw, projected = Path(temporary) / "server.json", Path(temporary) / "sdk.json"
            raw.write_bytes(b"actual raw schema")
            projected.write_bytes(b"actual projection")
            runtime = {"source_commit": REVISION, "server_build": BUILD, "candidate_version": VERSION,
                       "server_openapi_sha256": provenance.digest(raw),
                       "model_assets": {"files": provenance.MODEL_FILES}}
            sdk = {"server_revision": REVISION, "gem_version": VERSION,
                   "server_version": "0.9.1", "generator_version": "7.11.0",
                   "generator_sha256": provenance.GENERATOR_SHA256, "publication_authorized": False,
                   "combined_schema_sha256": provenance.digest(raw), "sdk_schema_sha256": provenance.digest(projected)}
            provenance.verify_pair(runtime, sdk, raw, projected)
            for field, value in [("server_revision", "b" * 40), ("gem_version", "0.9.1"),
                                 ("generator_sha256", "0" * 64), ("publication_authorized", 0)]:
                with self.subTest(field=field), self.assertRaises(ValueError):
                    provenance.verify_pair(runtime, dict(sdk, **{field: value}), raw, projected)
            raw.write_bytes(b"other server")
            with self.assertRaises(ValueError):
                provenance.verify_pair(runtime, sdk, raw, projected)

    def test_image_labels_user_and_asset_configuration_are_checked(self):
        runtime = {"candidate_version": VERSION, "source_commit": REVISION}
        image = {"Id": "sha256:" + "b" * 64, "Architecture": "amd64", "Os": "linux",
                 "Config": {"User": "10001:10001", "Env": [f"QW_CHEMINEE_MODEL_ASSETS={provenance.MODEL_DIRECTORY}"],
                            "Labels": {"org.opencontainers.image.title": "Cheminee",
                                       "org.opencontainers.image.version": VERSION,
                                       "org.opencontainers.image.revision": REVISION,
                                       "org.opencontainers.image.base.name": provenance.BASE_IMAGE,
                                       "io.cheminee.publication-authorized": "false"}}}
        provenance.verify_image(image, runtime)
        for field, value in [("User", "root"), ("Env", [])]:
            wrong = copy.deepcopy(image)
            wrong["Config"][field] = value
            with self.assertRaises(ValueError):
                provenance.verify_image(wrong, runtime)
        image["Config"]["Labels"]["org.opencontainers.image.revision"] = "b" * 40
        with self.assertRaises(ValueError):
            provenance.verify_image(image, runtime)

    def test_image_archive_rejects_changed_config_or_layer_bytes(self):
        layer = b"tiny layer bytes"
        config = json.dumps({"rootfs": {"diff_ids": ["sha256:" + hashlib.sha256(layer).hexdigest()]}}).encode()
        image_id = "sha256:" + hashlib.sha256(config).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "image.tar"
            for data in (layer, b"tampered layer"):
                with tarfile.open(target, "w") as archive:
                    add_file(archive, "manifest.json", json.dumps([{"Config": "config.json", "Layers": ["layer.tar"]}]).encode())
                    add_file(archive, "config.json", config)
                    add_file(archive, "layer.tar", data)
                if data == layer:
                    verify_archive(target, image_id)
                    with self.assertRaises(ValueError):
                        verify_archive(target, "sha256:" + "0" * 64)
                else:
                    with self.assertRaises(ValueError):
                        verify_archive(target, image_id)

    def test_gem_archive_must_contain_matching_provenance_schema_and_version(self):
        sdk = {"gem_version": VERSION}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schema = root / "openapi.json"
            schema.write_bytes(b"projected schema")
            for version in (VERSION, "0.0.0"):
                data = io.BytesIO()
                with tarfile.open(fileobj=data, mode="w:gz") as contents:
                    add_file(contents, "provenance.json", json.dumps(sdk).encode())
                    add_file(contents, "openapi.json", schema.read_bytes())
                    add_file(contents, "lib/quickwit-cheminee/version.rb", f"VERSION = '{version}'".encode())
                candidate = root / "candidate.gem"
                with tarfile.open(candidate, "w") as package:
                    add_file(package, "data.tar.gz", data.getvalue())
                if version == VERSION:
                    verify_gem(candidate, sdk, schema)
                else:
                    with self.assertRaises(ValueError):
                        verify_gem(candidate, sdk, schema)
            with self.assertRaises(FileNotFoundError):
                verify_gem(root / "absent.gem", sdk, schema)


class LifecycleTests(unittest.TestCase):
    def test_probe_requires_observed_clean_requested_termination(self):
        command = "import signal,sys; signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); print('ready', flush=True); signal.pause()"
        process = subprocess.Popen([sys.executable, "-c", command], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual("ready\n", process.stdout.readline())
            stop_probe(process)
            self.assertEqual(0, process.returncode)
            with self.assertRaises(RuntimeError):
                stop_probe(process)
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

    def test_restart_timeout_does_not_start_or_force_kill(self):
        info = {"Id": "owned", "RestartCount": 0, "HostConfig": {"RestartPolicy": {"Name": "no"}},
                "State": {"Running": True, "OOMKilled": False, "ExitCode": 0, "StartedAt": "one"}}
        calls = []
        def command(argv, timeout):
            calls.append(argv)
            if argv[1] == "wait":
                raise subprocess.TimeoutExpired(argv, timeout)
            return ""
        expected = {"id": "owned", "restart_count": 0, "started_at": "one"}
        with self.assertRaises(subprocess.TimeoutExpired):
            checked_restart("owned", expected, lambda _: info, {}, command)
        self.assertEqual(["kill", "wait"], [argv[1] for argv in calls])
        self.assertIn("--signal=TERM", calls[0])


if __name__ == "__main__":
    unittest.main()
