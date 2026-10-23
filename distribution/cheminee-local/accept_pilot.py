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

"""Run an installed Ruby gem against an isolated, bounded native pilot image.

For admitted disposable hosts only. Quiesced local file backups only; no registry,
credentials, infrastructure changes, forced kill or automatic restart.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from pilot_provenance import canonical, capture_server, digest, request_json, verify_image, write_json
from pilot_storage import require_stopped, resource_receipt, restore_offline
from readiness import (assert_container_state, assert_incarnation, checked_restart,
                       container_incarnation, wait_ready)


def docker(arguments, timeout=30):
    return subprocess.check_output(["docker", *arguments], text=True,
                                   stderr=subprocess.STDOUT, timeout=timeout).strip()


def inspect(container):
    return json.loads(docker(["inspect", container]))[0]


def stop_cleanly(container, expected, report):
    before = container_incarnation(inspect(container))
    assert_incarnation(expected, before)
    docker(["kill", "--signal=TERM", container], timeout=5)
    exit_code = docker(["wait", container], timeout=60)
    stopped = inspect(container)
    report["final_stopped_state"] = stopped["State"]
    assert_incarnation(before, container_incarnation(stopped, stopped=True))
    if exit_code != "0":
        raise RuntimeError("pilot container did not shut down cleanly")


def run_catalog(repository, output, phase, host, journal):
    environment = dict(os.environ, SDK_SMOKE_HOST=host,
                       CATALOG_NATIVE_PHASE=phase,
                       CATALOG_NATIVE_STATE=str(journal))
    log_path = output / f"catalog-{phase}.log"
    with log_path.open("xb") as log:
        subprocess.run(["ruby", str(repository / "sdk/ruby/examples/catalog_native_smoke.rb")],
                       cwd=output, env=environment, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=600)
    result = json.loads(log_path.read_text().splitlines()[-1])
    if result.get("status") != "passed":
        raise ValueError("installed-gem catalog acceptance did not report success")
    return result


def create_container(name, image, output):
    volume = f"{name}-data"
    if volume in docker(["volume", "ls", "--format", "{{.Name}}"]).splitlines():
        raise ValueError("pilot data volume already exists")
    node = (Path(__file__).with_name("quickwit.yaml")).read_text()
    if node.count("node_id: local\n") != 1:
        raise ValueError("pilot node configuration changed; review acceptance configuration")
    config = output / f"{name}.yaml"
    config.write_text(node.replace("node_id: local\n", f"node_id: {name}\n"))
    config.chmod(0o644)
    docker(["create", "--name", name, "--restart=no", "--read-only",
            "--cpus=2", "--memory=4g", "--memory-swap=4g", "--pids-limit=512",
            "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
            "--tmpfs=/tmp:rw,size=64m,mode=1777", "--publish=127.0.0.1::7280",
            "--mount", f"type=bind,src={config},dst=/etc/cheminee/quickwit.yaml,readonly",
            "--mount", f"type=volume,src={volume},dst=/var/lib/cheminee",
            "--env=QW_DISABLE_PER_INDEX_METRICS=true", "--env=TF_NUM_INTRAOP_THREADS=1",
            "--env=TF_NUM_INTEROP_THREADS=1", "--env=OMP_NUM_THREADS=1",
            "--health-cmd=curl --fail --silent http://127.0.0.1:7280/health/readyz",
            "--health-interval=2s", "--health-timeout=2s", "--health-retries=45",
            "--log-driver=json-file", "--log-opt=max-size=10m", "--log-opt=max-file=2",
            image, "run", "--config", "/etc/cheminee/quickwit.yaml"], timeout=60)


def verify_running(name, image, runtime, context):
    initial = inspect(name)
    if initial["Image"] != image:
        raise ValueError("container uses a different image")
    ports = initial["NetworkSettings"]["Ports"]["7280/tcp"]
    if len(ports) != 1 or ports[0]["HostIp"] != "127.0.0.1":
        raise ValueError("pilot REST listener is not isolated to host loopback")
    host = f"127.0.0.1:{ports[0]['HostPort']}"
    base = f"http://{host}"

    def ready(timeout):
        state = inspect(name)["State"]
        if not state["Running"] or state["OOMKilled"]:
            raise RuntimeError("pilot exited or was OOM-killed during readiness")
        return state.get("Health", {}).get("Status") == "healthy" and request_json(base, "/health/readyz", timeout)

    wait_ready(ready, timeout=90)
    current = inspect(name)
    assert_container_state(current["State"])
    observed = capture_server(base, runtime["source_commit"], name)
    if observed["build"] != runtime["server_build"]:
        raise ValueError("image server build differs from packaged executable")
    if canonical(observed["schema"]) != (context / "server-openapi.json").read_bytes():
        raise ValueError("image serves a different OpenAPI from SDK input")
    embedded = json.loads(docker(["exec", name, "/usr/local/bin/curl", "--fail", "--silent",
                                 "file:///opt/cheminee-runtime-manifest.json"]))
    if embedded != runtime:
        raise ValueError("image runtime manifest differs from packaging evidence")
    return host, container_incarnation(current)


def measured_catalog(repository, output, phase, host, journal, container, report):
    observation = {"phase": phase, "before_incarnation": container_incarnation(inspect(container)),
                   "before": resource_receipt(container, docker)}
    report.setdefault("resources", []).append(observation)
    started_at = time.monotonic()
    try:
        return run_catalog(repository, output, phase, host, journal)
    except BaseException as error:
        observation["failure"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        observation["elapsed_seconds"] = time.monotonic() - started_at
        observation["after"] = resource_receipt(container, docker)
        observation["after_incarnation"] = container_incarnation(inspect(container))
        assert_incarnation(observation["before_incarnation"], observation["after_incarnation"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Immutable local image ID")
    parser.add_argument("--gem", required=True, type=Path, help="Exact local archive installed for acceptance")
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    runtime = json.loads((args.context / "manifest.json").read_bytes())
    image = json.loads(docker(["image", "inspect", args.image]))[0]
    verify_image(image, runtime)
    if image["Id"] != args.image:
        parser.error("image argument must be the exact local config digest")
    if os.environ.get("SDK_EXPECTED_VERSION") != runtime["candidate_version"]:
        parser.error("installed-gem version differs from runtime candidate")
    if not Path(os.environ["CATALOG_NATIVE_ORACLE"]).is_file():
        parser.error("catalog native oracle is missing")
    repository = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    name = f"cheminee-pilot-{uuid.uuid4().hex}"
    report = {"status": "failed", "image_id": image["Id"], "source_commit": runtime["source_commit"],
              "candidate_version": runtime["candidate_version"], "container": name,
              "scope": "native installed-gem synthetic catalog import/refresh/rollback, clean restart and quiesced fresh restore/rollback; local file storage",
              "unqualified": ["100k diverse corpus", "kind", "object storage", "online backups",
                              "forced replacement", "HA", "capacity sizing", "release security approval"]}
    created = []
    try:
        proof = subprocess.check_output(
            ["ruby", str(Path(__file__).with_name("verify_installed_gem.rb")),
             str(args.gem.resolve()), runtime["candidate_version"], os.environ["SDK_INSTALL_ROOT"]],
            cwd=output, text=True, timeout=60)
        report["ruby_sdk"] = json.loads(proof)
        if report["ruby_sdk"]["gem_sha256"] != digest(args.gem):
            raise ValueError("installed-gem proof differs from candidate archive")
        create_container(name, args.image, output)
        created.append(name)
        docker(["start", name])
        host, identity = verify_running(name, args.image, runtime, args.context)
        journal = output / "catalog-state"
        report["initial_incarnation"] = identity
        report["catalog_create"] = measured_catalog(repository, output, "create", host, journal, name, report)
        assert_incarnation(identity, container_incarnation(inspect(name)))
        report["restart"] = {}
        restarted = checked_restart(name, identity, inspect, report["restart"])
        host, verified_restart = verify_running(name, args.image, runtime, args.context)
        assert_incarnation(restarted, verified_restart)
        report["catalog_verify_after_restart"] = measured_catalog(repository, output, "verify", host, journal, name, report)
        assert_incarnation(restarted, container_incarnation(inspect(name)))
        report["source_shutdown"] = {}
        stop_cleanly(name, restarted, report["source_shutdown"])
        restored_name = f"cheminee-pilot-{uuid.uuid4().hex}"
        create_container(restored_name, args.image, output)
        created.append(restored_name)
        backup_started = time.monotonic()
        restored_journal, restore_proof = restore_offline(
            name, restored_name, restarted, inspect, output / "restore", journal)
        report["restore"] = restore_proof
        report["restore"]["copy_and_hash_elapsed_seconds"] = time.monotonic() - backup_started
        docker(["start", restored_name])
        restored_host, restored_identity = verify_running(restored_name, args.image, runtime, args.context)
        report["restored_incarnation"] = restored_identity
        report["catalog_after_restore"] = measured_catalog(
            repository, output, "restored", restored_host, restored_journal, restored_name, report)
        assert_incarnation(restored_identity, container_incarnation(inspect(restored_name)))
        require_stopped(name, restarted, inspect)
        report["restored_shutdown"] = {}
        stop_cleanly(restored_name, restored_identity, report["restored_shutdown"])
        if report["ruby_sdk"]["gem_sha256"] != digest(args.gem):
            raise ValueError("candidate gem changed during live acceptance")
        report["status"] = "passed"
    except BaseException as error:
        report["failure"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        # Preserve failed/stopped containers and their volumes for the disposable
        # host's owner. Never reset evidence with restart, rm -f or volume pruning.
        report["final_containers"] = {}
        for container in created:
            try:
                report["final_containers"][container] = inspect(container)
                (output / f"{container}.log").write_text(docker(["logs", container]))
            except (subprocess.SubprocessError, OSError) as error:
                report["diagnostic_failure"] = str(error)
                report["status"] = "failed"
        write_json(output / "result.json", report)
    if report["status"] != "passed":
        raise RuntimeError("pilot diagnostics failed")


if __name__ == "__main__":
    main()
