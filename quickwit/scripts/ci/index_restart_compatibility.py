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
"""Qualify disposable file-backed Quickwit indexes through the real REST stack.

Baseline writes -> candidate reopens and appends -> candidate restarts -> baseline
reopens. This checks published indexes, not lost acknowledgements or WAL recovery.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

INDEX_ID = "restart-compatibility"
BASELINE_COUNT = 384
APPEND_COUNT = 96
FIRST_ID = 2**53 + 1
PAGE_SIZE = 37
BLOCK_SIZE = 16384
HTTP_TIMEOUT = 90
START_TIMEOUT = 90
STOP_TIMEOUT = 90


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def save_json(path, value):
    path.write_bytes(encoded(value) + b"\n")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def corpus(start, count):
    documents = []
    for ordinal in range(start, start + count):
        payload = hashlib.shake_256(f"public-synthetic-{ordinal}".encode()).hexdigest(2048)
        documents.append({"record_id": FIRST_ID + ordinal, "ordinal": ordinal,
                          "cohort": "selected" if ordinal % 7 == 0 else "ordinary",
                          "message": f"public synthetic record {ordinal}", "payload": payload})
    return documents


def index_config():
    return {"version": "0.8", "index_id": INDEX_ID,
            "doc_mapping": {"mode": "strict", "store_source": True, "field_mappings": [
                {"name": "record_id", "type": "u64", "fast": True},
                {"name": "ordinal", "type": "u64"},
                {"name": "cohort", "type": "text", "tokenizer": "raw"},
                {"name": "message", "type": "text"},
                {"name": "payload", "type": "text", "indexed": False}]},
            "indexing_settings": {"commit_timeout_secs": 10, "docstore_blocksize": BLOCK_SIZE,
                                  "merge_policy": {"type": "no_merge"}}}


def node_config(root, port):
    return {"version": "0.8", "cluster_id": "index-probe-" + uuid.uuid4().hex,
            "node_id": "index-probe-" + uuid.uuid4().hex, "listen_address": "127.0.0.1",
            "advertise_address": "127.0.0.1", "rest": {"listen_port": port},
            "grpc_listen_port": port + 1, "gossip_listen_port": port + 2, "peer_seeds": [],
            "data_dir": str(root / "data"), "metastore_uri": (root / "indexes").as_uri(),
            "default_index_root_uri": (root / "indexes").as_uri(),
            "indexer": {"enable_otlp_endpoint": False}, "jaeger": {"enable_endpoint": False}}


def child_environment(root):
    # Do not inherit QW configuration, cloud credentials, telemetry or proxy endpoints.
    environment = {key: os.environ[key] for key in ("PATH", "LD_LIBRARY_PATH") if key in os.environ}
    environment.update({"HOME": str(root), "TMPDIR": str(root / "tmp"), "NO_COLOR": "1",
                        "RUST_LOG": "info", "NO_PROXY": "*", "no_proxy": "*",
                        "QW_DISABLE_TELEMETRY": "1",
                        "AWS_EC2_METADATA_DISABLED": "true"})
    return environment


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


class RestError(RuntimeError):
    def __init__(self, status, payload):
        super().__init__(f"REST request failed with status {status}")
        self.status, self.payload = status, payload


class RestClient:
    def __init__(self, port, evidence):
        self.base = f"http://127.0.0.1:{port}"
        self.evidence = evidence
        self.sequence = 0
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, method, path, label, body=None, content_type="application/json"):
        self.sequence += 1
        stem = self.evidence / f"{self.sequence:04d}-{label}"
        save_json(stem.with_suffix(".request.json"),
                  {"method": method, "url": self.base + path, "content_type": content_type,
                   "body_sha256": hashlib.sha256(body or b"").hexdigest(),
                   "json": json.loads(body) if body and content_type == "application/json" else None})
        request = urllib.request.Request(self.base + path, data=body, method=method,
                                         headers={"Content-Type": content_type})
        # A failed write has an uncertain outcome: never retry it.
        try:
            with self.opener.open(request, timeout=HTTP_TIMEOUT) as response:
                payload = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            failure = error.read()
            stem.with_suffix(".response.json").write_bytes(failure)
            save_json(stem.with_suffix(".status.json"), {"status": error.code})
            raise RestError(error.code, failure) from error
        stem.with_suffix(".response.json").write_bytes(payload)
        save_json(stem.with_suffix(".status.json"), {"status": status})
        require(200 <= status < 300, f"unexpected HTTP status {status}")
        return json.loads(payload)

    def search(self, query, label, size, after=None):
        body = {"query": query, "size": size, "track_total_hits": True,
                "sort": [{"record_id": "asc"}]}
        if after is not None:
            body["search_after"] = after
        return self.request("POST", f"/api/v1/_elastic/{INDEX_ID}/_search"
                            "?allow_partial_search_results=false", label, encoded(body))


def search_envelope(response):
    require(isinstance(response, dict), "search response must be an object")
    require("error" not in response and not response.get("errors"), "search returned errors")
    require(response.get("timed_out") is False, "search timed out or omitted timeout status")
    terminated = response.get("terminated_early")
    require(terminated is None or terminated is False, "search terminated early")
    shards = response.get("_shards", {})
    for field in ("total", "successful", "failed", "skipped"):
        require(type(shards.get(field)) is int and shards[field] >= 0,
                f"invalid or missing shard count: {field}")
    require(shards["failed"] == 0 and not shards.get("failures"), "search has failed shards")
    require(shards["total"] == shards["successful"] and shards["skipped"] == 0,
            "inconsistent shard counts")
    hits_metadata = response.get("hits", {})
    total = hits_metadata.get("total", {})
    require(isinstance(total, dict) and type(total.get("value")) is int
            and total["value"] >= 0 and total.get("relation") == "eq", "inexact hit count")
    require(total["value"] == 0 or shards["successful"] > 0, "hits without successful shards")
    hits = hits_metadata.get("hits")
    require(isinstance(hits, list), "missing hits array")
    return total["value"], hits


def verify_page(response, expected, total):
    actual_total, hits = search_envelope(response)
    require(actual_total == total, f"wrong total: expected {total}, got {actual_total}")
    require(len(hits) == len(expected), "missing or extra documents in page")
    for hit, document in zip(hits, expected):
        require(isinstance(hit, dict), "hit must be an object")
        require(hit.get("_index") == INDEX_ID, "hit returned from wrong index")
        source = hit.get("_source")
        require(isinstance(source, dict) and type(source.get("record_id")) is int,
                "missing or noninteger record_id")
        # Quickwit's stored fields include the original document under `_source`
        # when store_source=true. Check both copies against the input oracle.
        expected_source = {**document, "_source": document}
        require(encoded(source) == encoded(expected_source), "missing, duplicate or changed document")
        require(encoded(hit.get("sort")) == encoded([document["record_id"]]),
                "wrong or imprecise numeric sort value")
    return hits[-1]["sort"] if hits else None


def verify_query(client, documents, query, label):
    expected = sorted(documents, key=lambda document: document["record_id"])
    require(len({document["record_id"] for document in expected}) == len(expected),
            "oracle contains duplicate record IDs")
    after = None
    pages = 0
    # Include a terminal empty page, even if the last nonempty page was short.
    for offset in range(0, len(expected) + PAGE_SIZE, PAGE_SIZE):
        response = client.search(query, f"{label}-{pages:03d}", PAGE_SIZE, after)
        after = verify_page(response, expected[offset:offset + PAGE_SIZE], len(expected))
        pages += 1
    return {"count": len(expected), "pages": pages,
            "documents_sha256": hashlib.sha256(encoded(expected)).hexdigest()}


def verify_index(client, documents, label):
    selected = [document for document in documents if document["cohort"] == "selected"]
    return {"all": verify_query(client, documents, {"match_all": {}}, label + "-all"),
            "selective": verify_query(client, selected, {"term": {"cohort": "selected"}},
                                      label + "-selective"),
            "empty": verify_query(client, [], {"term": {"cohort": "absent"}}, label + "-empty")}


def ingest_and_wait(client, documents, total, root, label):
    data = b"".join(encoded(document) + b"\n" for document in documents)
    (root / f"{label}.ndjson").write_bytes(data)
    result = client.request("POST", f"/api/v1/{INDEX_ID}/ingest?commit=force", label, data,
                            "application/x-ndjson")
    for field, expected in (("num_docs_for_processing", len(documents)),
                            ("num_ingested_docs", len(documents)), ("num_rejected_docs", 0)):
        require(type(result.get(field)) is int and result[field] == expected,
                f"ingest acceptance is incomplete or unknown: {field}")
    require(not result.get("parse_failures"), "ingest reported parse failures")
    deadline = time.monotonic() + START_TIMEOUT
    while True:
        count, hits = search_envelope(client.search({"match_all": {}}, label + "-published", 0))
        require(not hits and count <= total, "unexpected publication count or hits")
        if count == total:
            return
        require(time.monotonic() < deadline, "published document count did not become visible")
        time.sleep(0.25)


def check_ports(port):
    with ExitStack() as stack:
        for number, kind in ((port, socket.SOCK_STREAM), (port + 1, socket.SOCK_STREAM),
                             (port + 2, socket.SOCK_DGRAM)):
            connection = stack.enter_context(socket.socket(socket.AF_INET, kind))
            if kind == socket.SOCK_STREAM:
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            connection.bind(("127.0.0.1", number))


def cluster_ready(snapshot, config):
    require(snapshot.get("self_node_id") == config["node_id"]
            and snapshot.get("cluster_id") == config["cluster_id"], "wrong cluster identity")
    ready = snapshot.get("ready_nodes")
    require(isinstance(ready, list) and len(ready) <= 1, "unexpected ready node set")
    if not ready:
        return False
    require(ready[0].get("node_id") == config["node_id"], "unexpected ready node identity")
    states = snapshot.get("chitchat_state_snapshot", {}).get("node_states", [])
    own_states = [state for state in states if state.get("chitchat_id") == ready[0]]
    require(len(own_states) == 1, "missing current node state")
    values = own_states[0].get("key_values", {})
    services = set(values.get("enabled_services", {}).get("value", "").split(","))
    require({"searcher", "indexer", "metastore", "control-plane"} <= services,
            "required services missing from ready node")
    return values.get("readiness", {}).get("value") == "READY"


class Server:
    def __init__(self, root, config, client, events, environment):
        self.root, self.config, self.client = root, config, client
        self.events, self.environment = events, environment
        self.process = None
        self.log = None

    def start(self, binary, revision, label, rehearsal, has_index=False):
        require(self.process is None, "previous server was not stopped")
        check_ports(self.config["rest"]["listen_port"])
        self.log = (self.root / f"{label}.log").open("wb")
        command = [str(binary), "run", "--config", str(self.root / "node.json")]
        self.process = subprocess.Popen(command, cwd=self.root, env=self.environment,
                                        stdout=self.log, stderr=subprocess.STDOUT,
                                        start_new_session=True)
        self.events.append({"event": "start", "label": label, "pid": self.process.pid,
                            "command": command})
        self.wait_ready()
        actual_config = self.client.request("GET", "/api/v1/config", label + "-config")
        require(actual_config.get("node_id") == self.config["node_id"], "wrong server identity")
        version = self.client.request("GET", "/api/v1/version", label + "-version")
        embedded = version.get("build", {}).get("commit_hash")
        if not rehearsal:
            require(embedded == revision, "binary embedded revision differs from declared revision")
        self.wait_cluster(label)
        if has_index:
            self.wait_searcher(label)
        self.events.append({"event": "ready", "label": label, "embedded_revision": embedded})

    def wait_ready(self):
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            require(self.process.poll() is None, "server exited before readiness")
            try:
                with self.client.opener.open(self.client.base + "/health/readyz", timeout=1) as reply:
                    if reply.status == 200:
                        return
            except (urllib.error.URLError, TimeoutError):
                pass
            time.sleep(0.25)
        raise TimeoutError("server did not become ready")

    def wait_cluster(self, label):
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            require(self.process.poll() is None, "server exited during cluster readiness")
            snapshot = self.client.request("GET", "/api/v1/cluster", label + "-cluster")
            if cluster_ready(snapshot, self.config):
                return
            time.sleep(0.25)
        raise TimeoutError("local services did not become cluster-ready")

    def wait_searcher(self, label):
        deadline = time.monotonic() + START_TIMEOUT
        expected_reason = ("internal error: `failed to assign search jobs: there are no available "
                           "searcher nodes in the cluster`")
        while time.monotonic() < deadline:
            require(self.process.poll() is None, "server exited during search readiness")
            try:
                response = self.client.search({"match_all": {}}, label + "-search-ready", 0)
            except RestError as error:
                reason = json.loads(error.payload).get("error", {}).get("reason")
                if error.status != 500 or reason != expected_reason:
                    raise
                time.sleep(0.25)
                continue
            _, hits = search_envelope(response)
            require(not hits, "readiness count query unexpectedly returned hits")
            return
        raise TimeoutError("local searcher pool did not become ready")

    def stop(self, required=True):
        if self.process is None:
            if self.log is not None:
                self.log.close()
                self.log = None
            return
        process = self.process
        already_exited = process.poll() is not None
        forced = False
        try:
            if not already_exited:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=STOP_TIMEOUT)
                except subprocess.TimeoutExpired:
                    forced = True
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
            self.events.append({"event": "stop", "pid": process.pid,
                                "returncode": process.returncode, "forced": forced,
                                "already_exited": already_exited})
            if required:
                require(not already_exited and not forced and process.returncode == 0,
                        "server did not complete the required graceful shutdown")
        finally:
            if process.poll() is not None:
                self.process = None
                self.log.close()
                self.log = None


def binary_info(path, revision):
    require(path.is_absolute(), "binary paths must be absolute")
    resolved = path.resolve(strict=True)
    require(resolved.is_file() and os.access(resolved, os.X_OK), "binary must be executable")
    return {"path": str(path), "resolved_path": str(resolved), "declared_revision": revision,
            "sha256": sha256_file(resolved), "bytes": resolved.stat().st_size}


def run(args):
    baseline = binary_info(args.baseline_binary, args.baseline_revision)
    candidate = binary_info(args.candidate_binary, args.candidate_revision)
    rehearsal = baseline["sha256"] == candidate["sha256"]
    if rehearsal:
        require(args.baseline_revision == args.candidate_revision,
                "same-binary rehearsal must use identical revision labels")
    else:
        for revision in (args.baseline_revision, args.candidate_revision):
            require(re.fullmatch(r"[0-9a-f]{40}", revision), "revision must be a full git SHA")
        require(args.baseline_revision != args.candidate_revision, "qualification needs two revisions")
    require(args.work_dir.is_absolute(), "work directory must be absolute and fresh")
    require(1024 <= args.port <= 65533, "port must be between 1024 and 65533")
    args.work_dir.mkdir(mode=0o700, exist_ok=False)
    root = args.work_dir.resolve(strict=True)
    for name in ("tmp", "http", "data", "indexes"):
        (root / name).mkdir()
    configuration = node_config(root, args.port)
    environment = child_environment(root)
    save_json(root / "node.json", configuration)
    save_json(root / "index.json", index_config())
    original = corpus(0, BASELINE_COUNT)
    appended = corpus(BASELINE_COUNT, APPEND_COUNT)
    save_json(root / "oracle.json", {"baseline": original, "append": appended})
    evidence = {"status": "running", "mode": "same-binary-rehearsal" if rehearsal else "qualification",
                "scope": "published local file-backed indexes through Quickwit REST",
                "benchmark_trials": 0, "baseline": baseline, "candidate": candidate,
                "environment": environment, "events": [], "checks": {},
                "corpus_sha256": sha256_file(root / "oracle.json"),
                "script_sha256": sha256_file(Path(__file__)), "docstore_blocksize": BLOCK_SIZE}
    client = RestClient(args.port, root / "http")
    server = Server(root, configuration, client, evidence["events"], environment)
    try:
        server.start(args.baseline_binary, args.baseline_revision, "baseline-write", rehearsal)
        client.request("POST", "/api/v1/indexes", "create-index", encoded(index_config()))
        ingest_and_wait(client, original, len(original), root, "baseline-ingest")
        evidence["checks"]["baseline-written"] = verify_index(client, original, "baseline-written")
        server.stop()
        server.start(args.candidate_binary, args.candidate_revision, "candidate-open", rehearsal, True)
        evidence["checks"]["candidate-open"] = verify_index(client, original, "candidate-open")
        ingest_and_wait(client, appended, len(original + appended), root, "candidate-ingest")
        evidence["checks"]["candidate-written"] = verify_index(client, original + appended,
                                                               "candidate-written")
        server.stop()
        server.start(args.candidate_binary, args.candidate_revision, "candidate-restart", rehearsal, True)
        evidence["checks"]["candidate-restart"] = verify_index(client, original + appended,
                                                               "candidate-restart")
        server.stop()
        server.start(args.baseline_binary, args.baseline_revision, "baseline-reopen", rehearsal, True)
        evidence["checks"]["baseline-reopen"] = verify_index(client, original + appended,
                                                             "baseline-reopen")
        server.stop()
        for information in (baseline, candidate):
            require(sha256_file(Path(information["path"])) == information["sha256"],
                    "binary changed during probe")
        evidence["status"] = "passed"
    except BaseException as error:
        evidence["status"] = "failed"
        evidence["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        try:
            server.stop(required=False)
        finally:
            save_json(root / "result.json", evidence)
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("baseline", "candidate"):
        parser.add_argument(f"--{label}-binary", type=Path, required=True)
        parser.add_argument(f"--{label}-revision", required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True,
                        help="localhost REST port; also reserves TCP port+1 and UDP port+2")
    args = parser.parse_args()
    def interrupt(signum, frame):
        raise KeyboardInterrupt(f"received signal {signum}")
    signal.signal(signal.SIGTERM, interrupt)
    try:
        evidence = run(args)
    except (Exception, KeyboardInterrupt) as error:
        print(f"index restart probe failed: {error}", file=sys.stderr)
        return 1
    print(f"{evidence['mode']} passed; evidence: {args.work_dir / 'result.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
