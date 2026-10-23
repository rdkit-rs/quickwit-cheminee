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

"""Exercise native S3 client initialization in an actual private pilot image.

For admitted disposable Linux Docker hosts only. A local HTTP fixture answers
HEAD with 200 and GET with a controlled S3 AccessDenied error. The packaged
binary must reach and parse that error with its normal native trust store. A
fresh process with explicit empty root paths must reproduce the TrustStore
panic in the current debug-profile pilot. This is neither a TLS handshake test
nor object-store qualification; PR7 owns the real corpus/object-store gate.
"""
import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import threading
import uuid

from pilot_provenance import digest, verify_image, write_json


CA_PATH = "/etc/ssl/certs/ca-certificates.crt"
BINARY_PATH = "/usr/local/bin/quickwit"
FIXTURE_PATH = "/etc/cheminee/s3-smoke"
ACCESS_KEY = "cheminee-smoke-only"
SECRET_KEY = "synthetic-smoke-value-not-a-secret"
TRUSTSTORE_PANIC = "TrustStore configured to enable native roots but no valid root certificates parsed!"
MAX_LOG_BYTES = 128 * 1024


def expected_target(method, target, path):
    # AWS SDK appends this operation marker to GetObject; keep all other query
    # strings rejected and preserve the complete observed target in the receipt.
    return target == path or (method == "GET" and target == path + "?x-id=GetObject")


def docker(arguments, timeout=20):
    return subprocess.check_output(["docker", *arguments], text=True,
                                   stderr=subprocess.STDOUT, timeout=timeout).strip()


class FixtureServer(HTTPServer):
    # A stalled connection cannot hold fixture shutdown indefinitely.
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(3)
        return connection, address


@contextmanager
def s3_fixture(address, path, marker):
    records = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never collect Authorization headers or host credentials.

        def respond(self):
            authorization = self.headers.get("Authorization", "")
            signed = bool(re.fullmatch(
                rf"AWS4-HMAC-SHA256 Credential={ACCESS_KEY}/[0-9]{{8}}/us-east-1/s3/aws4_request, "
                r"SignedHeaders=[a-z0-9;-]+, Signature=[0-9a-f]{64}", authorization))
            expected = expected_target(self.command, self.path, path) and signed and self.command in ("HEAD", "GET")
            status = 200 if expected and self.command == "HEAD" else 403 if expected else 400
            # A HEAD success makes FileBackedMetastore fetch its manifest. A
            # nonretryable GET failure proves the SDK decoded an S3 response.
            body = (f'<?xml version="1.0" encoding="UTF-8"?>\n<Error><Code>AccessDenied</Code>'
                    f'<Message>{marker}</Message><RequestId>{marker}</RequestId></Error>').encode()
            records.append({"method": self.command, "path": self.path,
                            "signed_with_synthetic_key": signed, "status": status})
            self.send_response(status)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(0 if self.command == "HEAD" else len(body)))
            self.send_header("x-amz-request-id", marker)
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        do_HEAD = do_GET = do_PUT = do_POST = do_DELETE = respond

    with FixtureServer((address, 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        thread.start()
        try:
            yield f"http://{address}:{server.server_port}", records
        finally:
            server.shutdown()
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError("local S3 fixture did not stop within its deadline")


def node_config(endpoint, nonce):
    return {"version": "0.8", "cluster_id": "s3-initialization-smoke", "node_id": nonce,
            "listen_address": "127.0.0.1", "data_dir": "/tmp",
            "metastore_uri": f"s3://cheminee-smoke/{nonce}",
            "default_index_root_uri": f"s3://cheminee-smoke/{nonce}",
            "storage": {"s3": {"endpoint": endpoint, "region": "us-east-1",
                               "access_key_id": ACCESS_KEY, "secret_access_key": SECRET_KEY,
                               "force_path_style_access": True}},
            "indexer": {"enable_otlp_endpoint": False}}


def create_arguments(name, image, network, fixture, negative):
    # Explicit synthetic values prevent AWS credential/region discovery before
    # the S3-specific configuration is applied. No host env or home is mounted.
    environment = {"AWS_ACCESS_KEY_ID": ACCESS_KEY, "AWS_SECRET_ACCESS_KEY": SECRET_KEY,
                   "AWS_REGION": "us-east-1", "AWS_DEFAULT_REGION": "us-east-1",
                   "AWS_EC2_METADATA_DISABLED": "true", "AWS_SHARED_CREDENTIALS_FILE": "/dev/null",
                   "AWS_CONFIG_FILE": "/dev/null", "QW_DISABLE_TELEMETRY": "1", "RUST_BACKTRACE": "0",
                   "TF_NUM_INTRAOP_THREADS": "1", "TF_NUM_INTEROP_THREADS": "1", "OMP_NUM_THREADS": "1",
                   "HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": "", "NO_PROXY": "*",
                   "http_proxy": "", "https_proxy": "", "all_proxy": "", "no_proxy": "*"}
    if negative:
        # rustls-native-certs must not fall back to another system root location.
        environment.update(SSL_CERT_FILE=f"{FIXTURE_PATH}/empty.pem",
                           SSL_CERT_DIR=f"{FIXTURE_PATH}/empty-roots")
    command = ["create", "--name", name, "--network", network, "--restart=no", "--read-only",
               "--cpus=1", "--memory=2g", "--memory-swap=2g", "--pids-limit=128",
               "--cap-drop=ALL", "--security-opt=no-new-privileges:true", "--ulimit=core=0",
               "--tmpfs=/tmp:rw,size=16m,mode=1777", "--log-driver=json-file",
               "--log-opt=max-size=1m", "--log-opt=max-file=1",
               "--mount", f"type=bind,src={fixture},dst={FIXTURE_PATH},readonly",
               "--entrypoint=/bin/sh"]
    command.extend(f"--env={key}={value}" for key, value in environment.items())
    # Hash the actual image files before exec, without a builder filesystem or
    # host certificates mounted. Retain these checks even for the empty-root control.
    command.extend([image, "-ec", f"sha256sum {BINARY_PATH} {CA_PATH}; "
                    f"exec {BINARY_PATH} tool local-search --config {FIXTURE_PATH}/node.json "
                    "--index smoke --query '*' "])
    return command


def validate_probe(observation, log, runtime, path, marker, negative=False):
    if (observation.get("running") is not False or observation.get("oom_killed") is not False
            or observation.get("restart_count") != 0 or observation.get("log_truncated") is not False):
        raise ValueError("S3 probe did not finish cleanly within bounded diagnostics")
    for filename, expected in ((BINARY_PATH, runtime["runtime_binary_sha256"]),
                               (CA_PATH, runtime["ca_bundle"]["sha256"])):
        if re.findall(rf"^([0-9a-f]{{64}})  {re.escape(filename)}$", log, re.MULTILINE) != [expected]:
            raise ValueError(f"S3 probe image bytes differ from runtime manifest: {filename}")
    requests = observation["requests"]
    observation["request_count"] = len(requests)
    if negative:
        if observation["exit_code"] != 101 or TRUSTSTORE_PANIC not in log or requests:
            raise ValueError("empty-root control did not reproduce the native TrustStore panic before HTTP")
        observation["missing_roots_rejected"] = True
    else:
        expected = [{"method": method, "path": path, "signed_with_synthetic_key": True, "status": status}
                    for method, status in (("HEAD", 200), ("GET", 403))]
        if len(requests) == 2 and expected_target("GET", requests[1].get("path"), path):
            expected[1]["path"] = requests[1]["path"]
        if (observation["exit_code"] != 1 or requests != expected or marker not in log
                or "AccessDenied" not in log or "panicked at" in log or TRUSTSTORE_PANIC in log
                or "no native root CA certificates found" in log):
            raise ValueError("packaged S3 client did not reach the controlled local S3 error")
        observation.update(request_observed=True, controlled_s3_error_observed=True)
    observation["status"] = "passed"


def run_probe(name, image, network, fixture, output, requests, observation, created, negative=False):
    start = len(requests)
    docker(create_arguments(name, image, network, fixture, negative))
    created.append(name)
    observation.update(status="failed", container=name)
    try:
        docker(["start", name])
        observation["exit_code"] = int(docker(["wait", name], timeout=45))
    finally:
        info = json.loads(docker(["inspect", name]))[0]
        observation.update(running=info["State"]["Running"], oom_killed=info["State"]["OOMKilled"],
                           restart_count=info["RestartCount"], requests=list(requests[start:]))
        log = docker(["logs", name]).encode()
        observation["log_truncated"] = len(log) > MAX_LOG_BYTES
        log_path = output / ("negative.log" if negative else "positive.log")
        log_path.write_bytes(log[-MAX_LOG_BYTES:])
        observation["log_sha256"] = digest(log_path)
        if info["Image"] != image:
            raise ValueError("S3 probe container uses another image")
    return log.decode(errors="replace")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Immutable local image ID")
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "failed", "scope": "packaged S3 client initialization over local HTTP; native CA loading; no object-store qualification",
              "unqualified": ["TLS handshake", "object storage", "100k diverse corpus"],
              "negative_control_scope": "current debug-profile pilot native-roots assertion",
              "script_sha256": digest(Path(__file__)), "positive": {}, "negative": {}}
    network, created = None, []
    try:
        runtime = json.loads((args.context / "manifest.json").read_bytes())
        image = json.loads(docker(["image", "inspect", args.image]))[0]
        verify_image(image, runtime)
        if image["Id"] != args.image:
            raise ValueError("image argument must be the exact local config digest")
        ca = runtime["ca_bundle"]
        if ca["path"] != CA_PATH or ca["sha256"] != runtime["files"][CA_PATH.lstrip("/")]:
            raise ValueError("runtime CA manifest is inconsistent")
        report.update(image_id=args.image, source_commit=runtime["source_commit"],
                      candidate_version=runtime["candidate_version"], ca_bundle_sha256=ca["sha256"],
                      runtime_binary_sha256=runtime["runtime_binary_sha256"])
        nonce = "s3-smoke-" + uuid.uuid4().hex
        network = docker(["network", "create", "--internal", "--driver=bridge", nonce])
        info = json.loads(docker(["network", "inspect", network]))[0]
        if info.get("Internal") is not True or info.get("Containers") or len(info["IPAM"]["Config"]) != 1:
            raise ValueError("S3 fixture requires a fresh internal Docker network")
        gateway = info["IPAM"]["Config"][0]["Gateway"]
        if not isinstance(ipaddress.ip_address(gateway), ipaddress.IPv4Address) or not ipaddress.ip_address(gateway).is_private:
            raise ValueError("S3 fixture requires a private IPv4 bridge gateway")
        # Bind only the fresh bridge's host gateway. The containers have no
        # external route and no published ports; no helper image is needed.
        path, marker = f"/cheminee-smoke/{nonce}/manifest.json", f"controlled-{nonce}"
        fixture = output / "fixture"
        fixture.mkdir(mode=0o755)
        (fixture / "empty.pem").write_bytes(b"")
        (fixture / "empty-roots").mkdir(mode=0o755)
        with s3_fixture(gateway, path, marker) as (endpoint, requests):
            write_json(fixture / "node.json", node_config(endpoint, nonce))
            for file in (fixture / "node.json", fixture / "empty.pem"):
                file.chmod(0o644)
            for phase in ("positive", "negative"):
                negative = phase == "negative"
                log = run_probe(f"{nonce}-{phase}", args.image, network, fixture, output,
                                requests, report[phase], created, negative)
                validate_probe(report[phase], log, runtime, path, marker, negative)
        report["status"] = "passed"
    except BaseException as error:
        report["failure"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        # Only remove our disposable stopped probes. A timeout gets TERM and a
        # bounded wait; never force-kill or erase a still-running failed probe.
        for name in created:
            try:
                state = json.loads(docker(["inspect", name]))[0]["State"]
                if state["Running"]:
                    docker(["kill", "--signal=TERM", name], timeout=5)
                    docker(["wait", name], timeout=10)
                docker(["rm", name])
            except Exception as error:
                report.setdefault("cleanup_errors", []).append(f"{name}: {type(error).__name__}: {error}")
        if network:
            try:
                docker(["network", "rm", network])
            except Exception as error:
                report.setdefault("cleanup_errors", []).append(f"network: {type(error).__name__}: {error}")
        if report.get("cleanup_errors"):
            report["status"] = "failed"
        write_json(output / "result.json", report)
    if report["status"] != "passed":
        raise RuntimeError("S3 initialization smoke cleanup failed; inspect result.json")
    print(json.dumps({key: report[key] for key in ("status", "image_id", "source_commit",
                     "ca_bundle_sha256", "runtime_binary_sha256", "positive", "negative")}, sort_keys=True))


if __name__ == "__main__":
    main()
