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

"""Package a trusted native descriptor-v1 build inside its Linux amd64 builder.

Runs the stripped executable briefly on loopback to check its full embedded Git
revision and capture its actual OpenAPI. Never run this or ldd on untrusted code.
This is private candidate preparation, not reproducible-build/release approval.
"""
import argparse
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import uuid

from pilot_provenance import (BASE_IMAGE, MODEL_ARCHIVE, MODEL_DIRECTORY, MODEL_FILES,
                              canonical, capture_server, digest, request_json,
                              verify_models, verify_source, write_json)
from readiness import wait_ready


def stop_probe(process):
    if process.poll() is not None:
        raise RuntimeError("probe server exited before requested shutdown")
    process.terminate()
    # No force-kill/restart fallback: retain the failed probe for diagnosis.
    if process.wait(timeout=60) != 0:
        raise RuntimeError("probe server did not shut down cleanly")


def capture_binary(binary, revision, work):
    work.mkdir()
    (work / "data").mkdir()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    if port >= 65535:
        raise ValueError("probe port leaves no adjacent gRPC port")
    node_id = f"pilot-probe-{uuid.uuid4().hex}"
    config = {"version": "0.8", "cluster_id": node_id, "node_id": node_id,
              "listen_address": "127.0.0.1", "rest": {"listen_port": port},
              "data_dir": str(work / "data"), "metastore_uri": (work / "indexes").as_uri(),
              "default_index_root_uri": (work / "indexes").as_uri(),
              "indexer": {"enable_otlp_endpoint": False}}
    write_json(work / "node.json", config)
    base = f"http://127.0.0.1:{port}"
    with (work / "server.log").open("xb") as log:
        process = subprocess.Popen([str(binary), "run", "--config", str(work / "node.json")],
                                   stdout=log, stderr=subprocess.STDOUT,
                                   env=dict(os.environ, QW_DISABLE_TELEMETRY="1"))
        try:
            def ready(timeout):
                if process.poll() is not None:
                    raise RuntimeError("probe server exited during startup; inspect server.log")
                return request_json(base, "/health/readyz", timeout)
            wait_ready(ready, timeout=90)
            observed = capture_server(base, revision, node_id)
            if process.poll() is not None:
                raise RuntimeError("probe server exited during schema capture")
        finally:
            stop_probe(process)
    return observed


def runtime_libraries(binary):
    libraries = set()
    for executable in (binary, Path("/usr/bin/curl")):
        result = subprocess.run(["ldd", str(executable)], check=True, text=True,
                                capture_output=True, timeout=30).stdout
        if "not found" in result:
            raise RuntimeError("unresolved runtime dependency")
        libraries.update(re.findall(r"(/[^\s]+)", result))
    for required in ("libRDKitGraphMol.so.2026.09", "libtensorflow_cc.so.2", "libtensorflow_framework.so.2"):
        if not any(Path(name).name == required for name in libraries):
            raise ValueError(f"descriptor-v1 native dependency is missing: {required}")
    return libraries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--model-assets", type=Path, required=True)
    args = parser.parse_args()
    if platform.machine() != "x86_64":
        parser.error("only the native amd64 builder is supported")
    verify_source(args.source_root, args.source_commit)
    verify_models(args.model_assets)
    libraries = runtime_libraries(args.binary)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    root = output / "root"
    (root / "usr/local/bin").mkdir(parents=True)
    packaged = root / "usr/local/bin/quickwit"
    subprocess.run(["strip", "-o", str(packaged), str(args.binary)], check=True, timeout=120)
    shutil.copy2("/usr/bin/curl", root / "usr/local/bin/curl")
    for name in sorted(libraries):
        destination = root / Path(name).relative_to("/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(name, destination, follow_symlinks=True)
    model_target = root / MODEL_DIRECTORY.lstrip("/")
    for relative in MODEL_FILES:
        target = model_target / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.model_assets / relative, target)
    verify_models(model_target)
    observed = capture_binary(packaged, args.source_commit, output / "probe")
    (output / "server-openapi.json").write_bytes(canonical(observed["schema"]))
    recipes = ["quickwit/Cargo.lock", "quickwit/tantivy-rdkit-mapper/ci/install-rdkit.sh",
               "quickwit/tantivy-rdkit-mapper/ci/install-tensorflow.py",
               "quickwit/tantivy-rdkit-mapper/ci/install-descriptor-model.sh",
               "quickwit/tantivy-rdkit-mapper/src/cluster.rs"]
    manifest = {
        "format_version": 1, "product": "Cheminee", "engine": "Quickwit",
        "source_commit": args.source_commit, "platform": "linux/amd64", "base_image": BASE_IMAGE,
        "candidate_version": observed["candidate_version"], "server_build": observed["build"],
        "original_binary_sha256": digest(args.binary), "runtime_binary_sha256": digest(packaged),
        "server_openapi_sha256": digest(output / "server-openapi.json"),
        "model_assets": {"directory": MODEL_DIRECTORY, "archive": MODEL_ARCHIVE, "files": MODEL_FILES},
        "recipe_sha256": {name: digest(args.source_root / name) for name in recipes},
        "files": {str(path.relative_to(root)): digest(path)
                  for path in sorted(root.rglob("*")) if path.is_file()},
        "publication_authorized": False,
        "scope": "private pilot candidate; native image/SDK acceptance must still pass in CI",
    }
    write_json(output / "manifest.json", manifest)
    shutil.copy2(Path(__file__).with_name("Dockerfile.runtime"), output / "Dockerfile")
    (output / ".dockerignore").write_text("*\n!root/\n!root/**\n!manifest.json\n!Dockerfile\n")
    for path in output.rglob("*"):
        path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
    output.chmod(0o755)
    print(observed["candidate_version"])


if __name__ == "__main__":
    main()
