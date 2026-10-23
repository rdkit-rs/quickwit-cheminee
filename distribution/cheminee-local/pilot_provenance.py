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

"""Fail-closed identities shared by private pilot packaging and acceptance."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.request

BASE_IMAGE = "ubuntu@sha256:f144425ff09be612d6d9ad965196e9cdc23dae1f42110a8a11a3e9a8198759f7"
CA_BUNDLE_PATH = "/etc/ssl/certs/ca-certificates.crt"
MODEL_DIRECTORY = "/opt/cheminee-model/assets"
MODEL_ARCHIVE = {
    "url": "https://cheminee-models.s3.eu-central-1.amazonaws.com/similarity/similarity-0.1.0.tar.gz",
    "sha256": "264d7b3af776382dc98e12b1e7c111e76b99a3714ca71acf427bfe63536b26d5",
}
# These are the files verified by tantivy-rdkit-mapper/src/cluster.rs at load time.
MODEL_FILES = {
    "lf_kmeans_10k_centroids_20241111.csv": "5cf1ede6d2193dccd6b552dcce51b49c12cf69b28589e9f98c18311230edec65",
    "vae_encoder/saved_model.pb": "658f9912c06760343341b98ac8659527159a20aec51656574bde6328cc9b294b",
    "vae_encoder/variables/variables.data-00000-of-00001": "9d60970837b9398e6920eb96f61444919426b2f1d3d04f8377c0fc712f6e734f",
    "vae_encoder/variables/variables.index": "886d87f6ec11c70ffc7af7e76bf96699ebc9fa2c4e59f69d74bdbb2a29f33307",
}
GENERATOR_SHA256 = "113c25df5a781d5a1fc2b883f12fe8f263db285ab12e15854d5b15306e1bf7fc"


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def write_json(path, value):
    with path.open("xb") as output:
        output.write(canonical(value))


def digest(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def verify_source(repository, revision):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("source revision must be a full Git SHA")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository,
                                   text=True, timeout=10).strip()
    if head != revision:
        raise ValueError("checked-out source revision differs from expected revision")
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--"], cwd=repository,
                   check=True, stdout=subprocess.DEVNULL, timeout=10)


def verify_build(version, revision):
    build = version["build"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or build.get("commit_hash") != revision:
        raise ValueError("embedded server revision differs from checked-out source")
    if build.get("build_target") != "x86_64-unknown-linux-gnu":
        raise ValueError("only native Linux amd64 is qualified for this recipe")
    engine_version = build.get("cargo_pkg_version", "")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", engine_version):
        raise ValueError("unexpected embedded engine package version")
    # A source-addressed prerelease identity, not a release number or published tag.
    return f"{engine_version}.pre.pilot.g{revision}"


def verify_models(directory):
    for relative, expected in MODEL_FILES.items():
        path = directory / relative
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError(f"model asset is not a regular contained file: {relative}")
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"model asset checksum mismatch: {relative}")


def request_json(base, path, timeout=3):
    # Local probes must not inherit a builder's HTTP proxy configuration.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(base + path, timeout=timeout) as response:
        return json.load(response)


def capture_server(base, revision, node_id):
    version = request_json(base, "/api/v1/version")
    candidate = verify_build(version, revision)
    if request_json(base, "/api/v1/config").get("node_id") != node_id:
        raise ValueError("probe reached a different server instance")
    schema = request_json(base, "/openapi.json")
    if schema["info"]["version"] != version["build"]["cargo_pkg_version"]:
        raise ValueError("served schema and embedded engine versions differ")
    if request_json(base, "/api/v1/version")["build"] != version["build"]:
        raise ValueError("server build changed during schema capture")
    return {"candidate_version": candidate, "build": version["build"], "schema": schema}


def verify_pair(runtime, sdk, raw_schema, sdk_schema):
    revision = runtime["source_commit"]
    candidate = verify_build({"build": runtime["server_build"]}, revision)
    if runtime["candidate_version"] != candidate:
        raise ValueError("runtime candidate version differs from embedded build")
    expected = {
        "server_revision": revision, "gem_version": candidate,
        "combined_schema_sha256": digest(raw_schema), "sdk_schema_sha256": digest(sdk_schema),
        "generator_version": "7.11.0", "generator_sha256": GENERATOR_SHA256,
        "publication_authorized": False,
        "server_version": runtime["server_build"]["cargo_pkg_version"],
    }
    for key, value in expected.items():
        if type(sdk.get(key)) is not type(value) or sdk.get(key) != value:
            raise ValueError(f"SDK/runtime provenance mismatch: {key}")
    if runtime["server_openapi_sha256"] != digest(raw_schema):
        raise ValueError("SDK input is not the captured runtime schema")
    if runtime["model_assets"]["files"] != MODEL_FILES:
        raise ValueError("runtime model asset manifest differs from pinned files")


def verify_image(info, runtime):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", info.get("Id", "")):
        raise ValueError("image must have an immutable local config digest")
    if info.get("Architecture") != "amd64" or info.get("Os") != "linux":
        raise ValueError("image platform is not Linux amd64")
    config = info["Config"]
    labels = config.get("Labels", {})
    required = {
        "org.opencontainers.image.title": "Cheminee",
        "org.opencontainers.image.version": runtime["candidate_version"],
        "org.opencontainers.image.revision": runtime["source_commit"],
        "org.opencontainers.image.base.name": BASE_IMAGE,
        "io.cheminee.publication-authorized": "false",
    }
    if any(labels.get(key) != value for key, value in required.items()):
        raise ValueError("image OCI labels differ from runtime provenance")
    if config.get("User") != "10001:10001":
        raise ValueError("image must run as the non-root pilot user")
    if f"QW_CHEMINEE_MODEL_ASSETS={MODEL_DIRECTORY}" not in config.get("Env", []):
        raise ValueError("image does not configure pinned descriptor model assets")
    if f"SSL_CERT_FILE={CA_BUNDLE_PATH}" not in config.get("Env", []):
        raise ValueError("image does not configure its packaged native CA roots")
