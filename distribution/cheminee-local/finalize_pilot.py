#!/usr/bin/env python3
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

"""Bind actual image-archive and gem bytes to passed private pilot evidence."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import tarfile

from pilot_provenance import digest, verify_image, verify_pair, write_json


def verify_archive(path, image_id):
    # Inspect without extracting an untrusted archive path onto the filesystem.
    with tarfile.open(path, "r") as archive:
        names = archive.getnames()
        if len(names) != len(set(names)):
            raise ValueError("image archive contains duplicate paths")
        manifests = json.load(archive.extractfile("manifest.json"))
        if len(manifests) != 1:
            raise ValueError("image archive must contain exactly one image")
        config = archive.extractfile(manifests[0]["Config"]).read()
        if "sha256:" + hashlib.sha256(config).hexdigest() != image_id:
            raise ValueError("exported archive does not contain the accepted image config")
        differences = json.loads(config)["rootfs"]["diff_ids"]
        layers = manifests[0]["Layers"]
        if len(layers) != len(differences):
            raise ValueError("image archive layer count differs from accepted config")
        for name, expected in zip(layers, differences):
            with archive.extractfile(name) as layer:
                signature = layer.read(2)
                layer.seek(0)
                stream = gzip.GzipFile(fileobj=layer) if signature == b"\x1f\x8b" else layer
                actual = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
                if actual != expected:
                    raise ValueError("image archive layer differs from accepted config")


def verify_gem(path, sdk, schema):
    with tarfile.open(path, "r") as package:
        with tarfile.open(fileobj=package.extractfile("data.tar.gz"), mode="r:gz") as data:
            if json.load(data.extractfile("provenance.json")) != sdk:
                raise ValueError("gem contains a different SDK provenance manifest")
            if data.extractfile("openapi.json").read() != schema.read_bytes():
                raise ValueError("gem contains a different projected OpenAPI")
            version = data.extractfile("lib/quickwit-cheminee/version.rb").read().decode()
            match = re.search(r"VERSION\s*=\s*['\"]([^'\"]+)['\"]", version)
            if match is None or match.group(1) != sdk["gem_version"]:
                raise ValueError("gem code version differs from runtime candidate")


def verify_acceptance(acceptance, image, runtime, root):
    if (acceptance.get("status") != "passed" or acceptance.get("image_id") != image["Id"]
            or acceptance.get("source_commit") != runtime["source_commit"]
            or acceptance.get("candidate_version") != runtime["candidate_version"]):
        raise ValueError("native image acceptance is missing or belongs to another candidate")
    required = [("catalog_create", "rollback_verified"),
                ("catalog_verify_after_restart", "retained_active_verified"),
                ("catalog_after_restore", "restored_rollback_verified")]
    for phase, gate in required:
        result = acceptance.get(phase, {})
        if result.get("status") != "passed" or result.get(gate) is not True:
            raise ValueError(f"native catalog acceptance gate is missing: {phase}")
    restore = acceptance["restore"]
    if restore.get("empty_target_verified") is not True or restore.get("source_stopped_during_backup") is not True:
        raise ValueError("fresh quiesced restore proof is missing")
    for source, restored in (("source_container_id", "restored_container_id"),
                             ("source_volume", "restored_volume"), ("source_journal", "restored_journal")):
        if not restore.get(source) or not restore.get(restored) or restore[source] == restore[restored]:
            raise ValueError("restore destination is not distinct from its source")
    for name in ("data", "journal"):
        if digest(root / f"{name}-inventory.json") != restore[f"{name}_inventory_sha256"]:
            raise ValueError("restore inventory differs from accepted bytes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    args = parser.parse_args()
    root = args.artifacts
    runtime = json.loads((root / "runtime-manifest.json").read_bytes())
    sdk = json.loads((root / "sdk-provenance.json").read_bytes())
    image = json.loads((root / "image-inspect.json").read_bytes())[0]
    acceptance = json.loads((root / "acceptance.json").read_bytes())
    verify_pair(runtime, sdk, root / "server-openapi.json", root / "sdk-openapi.json")
    verify_image(image, runtime)
    verify_acceptance(acceptance, image, runtime, root)
    verify_archive(root / "cheminee-image.tar", image["Id"])
    verify_gem(root / "quickwit-cheminee.gem", sdk, root / "sdk-openapi.json")
    if (acceptance.get("ruby_sdk", {}).get("gem_sha256") != digest(root / "quickwit-cheminee.gem")
            or acceptance["ruby_sdk"].get("version") != sdk["gem_version"]):
        raise ValueError("exported gem was not the archive exercised by native acceptance")
    manifest = {
        "format_version": 1, "product": "Cheminee", "engine": "Quickwit",
        "candidate_version": runtime["candidate_version"], "source_commit": runtime["source_commit"],
        "platform": "linux/amd64", "image": {"local_config_digest": image["Id"],
            "archive_format": "docker-archive", "archive": "cheminee-image.tar",
            "oci_labels": image["Config"]["Labels"], "registry_manifest_digest": None},
        "ruby_sdk": {"gem": "quickwit-cheminee.gem", "version": sdk["gem_version"],
                     "server_openapi_sha256": runtime["server_openapi_sha256"]},
        "model_assets": runtime["model_assets"],
        "files": {path.name: {"sha256": digest(path), "bytes": path.stat().st_size}
                  for path in sorted(root.iterdir()) if path.is_file()},
        "qualification": {"native_image_and_installed_gem": "passed on an admitted disposable host",
                          "scope": acceptance["scope"], "unqualified": acceptance["unqualified"]},
        "publication_authorized": False, "deployment_authorized": False,
        "security_hold": "PR3 dependency-security findings (including protobuf/ZIP) require review; this candidate is not release approval",
        "reproducible_builds_and_redistribution": "unqualified",
    }
    write_json(root / "pilot-manifest.json", manifest)


if __name__ == "__main__":
    main()
