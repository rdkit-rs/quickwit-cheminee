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

"""Exercises original/patched Chitchat peers through real loopback UDP sockets."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import subprocess
import time


def digest_file(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def compact(snapshot):
    nodes = []
    for node in snapshot["nodes"]:
        values = json.dumps(node["values"], sort_keys=True).encode()
        nodes.append({
            key: value for key, value in node.items() if key != "values"
        } | {"values_sha256": hashlib.sha256(values).hexdigest()})
    return dict(snapshot, nodes=nodes)


def node_state(snapshot, name, generation=1):
    for node in snapshot["nodes"]:
        identity = node["id"]
        if identity["node_id"] == name and identity["generation_id"] == generation:
            return node
    return None


def contains_identity(identities, name, generation=1):
    return any(identity["node_id"] == name and identity["generation_id"] == generation
               for identity in identities)


class Guard:
    def __init__(self, args):
        self.args = args
        self.deadline = time.monotonic() + args.max_seconds
        self.peers = []
        self.peak_rss = 0
        self.min_workspace_free = None
        self.min_tmp_free = None

    def check(self):
        require(time.monotonic() < self.deadline, "overall deadline exceeded")
        for path, floor, attr in (
            (self.args.workspace, 671_088_640, "min_workspace_free"),
            (self.args.evidence, 536_870_912, "min_tmp_free"),
        ):
            stat = os.statvfs(path)
            free = stat.f_bavail * stat.f_frsize
            previous = getattr(self, attr)
            setattr(self, attr, free if previous is None else min(previous, free))
            require(free >= floor, f"disk floor reached: {path}")
        rss_total = 0
        for peer in self.peers:
            if peer.process.poll() is not None:
                continue
            try:
                status = Path(f"/proc/{peer.process.pid}/status").read_text()
            except FileNotFoundError:
                require(peer.process.poll() is not None, "live peer status disappeared")
                continue
            for line in status.splitlines():
                if line.startswith("VmRSS:"):
                    rss_total += int(line.split()[1]) * 1024
        self.peak_rss = max(self.peak_rss, rss_total)
        require(rss_total <= 2_147_483_648, "peer aggregate RSS exceeds 2 GiB")
        artifact_bytes = sum(path.stat().st_size for path in self.args.evidence.rglob("*")
                             if path.is_file())
        require(artifact_bytes <= 33_554_432, "evidence exceeds 32 MiB")


class Peer:
    def __init__(self, binary, name, generation, port, seeds, cluster, guard, directory):
        self.name = name
        self.address = f"127.0.0.1:{port}"
        self.guard = guard
        self.paused = False
        self.closed = False
        self.buffer = b""
        self.stderr = (directory / f"{name}-{generation}.stderr").open("xb")
        command = [str(binary), name, str(generation), self.address, seeds, cluster]
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=self.stderr, bufsize=0)
        except BaseException:
            self.stderr.close()
            raise
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        os.set_blocking(self.process.stdin.fileno(), False)
        self.writer = selectors.DefaultSelector()
        self.writer.register(self.process.stdin, selectors.EVENT_WRITE)
        guard.peers.append(self)
        try:
            self.ready = self.read()
            require(self.ready.get("ready") == {
                "node_id": name, "generation_id": generation,
                "gossip_advertise_addr": self.address,
            }, "peer identity mismatch")
        except BaseException as error:
            cleanup_errors = self.close()
            if cleanup_errors:
                raise RuntimeError(f"{error}; cleanup: {'; '.join(cleanup_errors)}") from error
            raise

    def write(self, payload, check_guard=True):
        deadline = time.monotonic() + 5
        remaining = memoryview(payload)
        while remaining:
            if check_guard:
                self.guard.check()
            require(time.monotonic() < deadline, f"control write timeout: {self.name}")
            require(self.process.poll() is None, f"peer exited: {self.name}")
            if not self.writer.select(0.1):
                continue
            try:
                count = os.write(self.process.stdin.fileno(), remaining)
            except BlockingIOError:
                continue
            require(count > 0, f"control pipe closed: {self.name}")
            remaining = remaining[count:]

    def read(self):
        deadline = time.monotonic() + 5
        while b"\n" not in self.buffer:
            self.guard.check()
            require(time.monotonic() < deadline, f"control timeout: {self.name}")
            require(self.process.poll() is None, f"peer exited: {self.name}")
            if not self.selector.select(0.1):
                continue
            chunk = os.read(self.process.stdout.fileno(), 65_536)
            require(bool(chunk), f"peer closed stdout: {self.name}")
            self.buffer += chunk
            require(len(self.buffer) <= 2_097_152, "peer response exceeds 2 MiB")
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)

    def request(self, operation, **parameters):
        self.guard.check()
        require(not self.paused, f"control request to paused peer: {self.name}")
        payload = json.dumps(dict(op=operation, **parameters)).encode() + b"\n"
        self.write(payload)
        response = self.read()
        if operation in ("set", "delete", "gossip"):
            require(response == {"ok": True}, f"command rejected: {self.name}")
        return response

    def pause(self):
        self.process.send_signal(signal.SIGSTOP)
        self.paused = True
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            self.guard.check()
            status = Path(f"/proc/{self.process.pid}/status").read_text()
            if any(line.startswith("State:") and line.split()[1] == "T"
                   for line in status.splitlines()):
                return
            time.sleep(0.01)
        raise RuntimeError(f"peer did not stop: {self.name}")

    def resume(self):
        self.process.send_signal(signal.SIGCONT)
        self.paused = False

    def close(self):
        if self.closed:
            return []
        errors = []
        try:
            if self.paused and self.process.poll() is None:
                self.resume()
            if self.process.poll() is None:
                # Cleanup must still work after a resource guard or deadline failure.
                self.write(b'{"op":"shutdown"}\n', check_guard=False)
                self.process.wait(timeout=5)
            require(self.process.returncode == 0, f"peer exit code {self.process.returncode}")
        except (BrokenPipeError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            errors.append(f"{self.name}: {error}")
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
        finally:
            self.selector.close()
            self.writer.close()
            self.process.stdin.close()
            self.process.stdout.close()
            self.stderr.close()
            self.closed = True
        return errors


class Scenario:
    def __init__(self, name, binaries, guard, evidence):
        self.name = name
        self.binaries = binaries
        self.guard = guard
        self.directory = evidence / name
        self.directory.mkdir()
        self.log = (self.directory / "events.jsonl").open("x")
        self.peers = []
        self.expected = {"a": {}, "b": {}, "c": {}}

    def event(self, stage, **details):
        self.log.write(json.dumps(dict(stage=stage, **details), sort_keys=True) + "\n")
        self.log.flush()

    def wait(self, stage, peers, predicate, timeout=15):
        start = time.monotonic()
        snapshots = []
        while time.monotonic() - start < timeout:
            self.guard.check()
            snapshots = [peer.request("snapshot") for peer in peers]
            if predicate(snapshots):
                self.event(stage, elapsed_seconds=time.monotonic() - start,
                           snapshots=[compact(snapshot) for snapshot in snapshots])
                return snapshots
            time.sleep(0.1)
        self.event(stage + "-timeout", snapshots=[compact(item) for item in snapshots])
        raise RuntimeError(f"{self.name}: did not reach {stage}")

    def converged(self, snapshots, generations=None):
        generations = generations or {"a": 1, "b": 1, "c": 1}
        for snapshot in snapshots:
            for name, values in self.expected.items():
                generation = generations[name]
                node = node_state(snapshot, name, generation)
                if node is None or node["values"] != values:
                    return False
                if not contains_identity(snapshot["live"], name, generation):
                    return False
        return True

    def run(self):
        reservations = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(3)]
        try:
            for reservation in reservations:
                reservation.bind(("127.0.0.1", 0))
            ports = [reservation.getsockname()[1] for reservation in reservations]
        finally:
            for reservation in reservations:
                reservation.close()
        # Port occupation races fail the harness; they never silently change the peer set.
        seeds = ",".join(f"127.0.0.1:{port}" for port in ports)
        for index, name in enumerate(("a", "b", "c")):
            binary = self.binaries[0] if name == "a" else self.binaries[1]
            self.peers.append(Peer(binary, name, 1, ports[index], seeds, self.name,
                                   self.guard, self.directory))
        self.event("started", configurations=[peer.ready for peer in self.peers])
        self.populate()
        self.pause_and_recover()
        original_b = self.peers[1]
        require(not original_b.close(), "first-generation peer shutdown failed")
        self.expected["b"] = {"restart": "generation-2"}
        replacement = Peer(self.binaries[1], "b", 2, ports[1], seeds, self.name,
                           self.guard, self.directory)
        self.peers[1] = replacement
        replacement.request("set", values=self.expected["b"])
        generations = {"a": 1, "b": 2, "c": 1}
        self.wait("new-generation-convergence", self.peers,
                  lambda items: self.converged(items, generations))
        self.wait("old-generation-garbage-collected", self.peers,
                  lambda items: all(node_state(item, "b") is None for item in items))

    def populate(self):
        for peer in self.peers:
            # More than 65,507 uncompressed bytes requires bounded delta exchange.
            values = {f"payload-{index:02}": hashlib.sha256(
                f"{peer.name}-{index}".encode()).hexdigest() for index in range(40)}
            for key, value in values.items():
                values[key] = "".join(hashlib.sha256(f"{value}-{part}".encode()).hexdigest()
                                      for part in range(40))
            values.update(mutable=f"{peer.name}-initial", removed="before-delete", unicode="é 水")
            self.expected[peer.name] = values
            peer.request("set", values=values)
        self.wait("initial-convergence", self.peers, self.converged)
        for peer in self.peers:
            self.expected[peer.name]["mutable"] = f"{peer.name}-updated"
            peer.request("set", values={"mutable": self.expected[peer.name]["mutable"]})
            peer.request("delete", key="removed")
            del self.expected[peer.name]["removed"]
        self.wait("updates-and-deletes", self.peers, self.converged)
        self.wait("tombstones-garbage-collected", self.peers,
                  lambda items: all("removed" not in node["all_keys"]
                                    for item in items for node in item["nodes"]))

    def pause_and_recover(self):
        observer, subject, stale = self.peers
        observer.request("set", values={"offline-delete": "must-not-return"})
        self.expected["a"]["offline-delete"] = "must-not-return"
        self.wait("before-pause", self.peers, self.converged)
        subject.pause()
        aligned = self.wait("stale-heartbeat-aligned", [observer, stale],
                            lambda items: node_state(items[0], "b") is not None
                            and node_state(items[1], "b") is not None
                            and contains_identity(items[0]["live"], "b")
                            and contains_identity(items[1]["live"], "b")
                            and node_state(items[0], "b")["heartbeat"]
                            == node_state(items[1], "b")["heartbeat"], timeout=2)
        frozen_heartbeat = node_state(aligned[0], "b")["heartbeat"]
        stale.pause()
        observer.request("delete", key="offline-delete")
        del self.expected["a"]["offline-delete"]
        self.wait("subject-dead", [observer],
                  lambda items: contains_identity(items[0]["dead"], "b"))
        self.wait("paused-peers-garbage-collected", [observer],
                  lambda items: node_state(items[0], "b") is None
                  and node_state(items[0], "c") is None
                  and "offline-delete" not in node_state(items[0], "a")["all_keys"])
        prior_messages = observer.request("snapshot")["wire"]["received_messages"]
        stale.resume()
        replay_source = node_state(stale.request("snapshot"), "b")
        require(replay_source is not None, "stale peer lost the replay source")
        require(replay_source["heartbeat"] == frozen_heartbeat, "stale heartbeat changed")
        stale.request("gossip", address=observer.address)
        self.wait("stale-subject-digest-received", [observer],
                  lambda items: stale_digest_received(items[0], stale.address,
                                                      prior_messages, frozen_heartbeat))
        self.wait("stale-peer-recreated", [observer],
                  lambda items: contains_identity(items[0]["live"], "c"))
        start = time.monotonic()
        while time.monotonic() - start < 1:
            snapshot = observer.request("snapshot")
            require(node_state(snapshot, "b") is None, "stale gossip resurrected subject")
            time.sleep(0.1)
        self.event("stale-subject-suppressed", frozen_heartbeat=frozen_heartbeat)
        subject.resume()
        self.wait("same-identity-recreated-and-offline-delete-preserved", self.peers,
                  self.converged)

    def close(self):
        errors = []
        for peer in reversed(self.peers):
            errors.extend(peer.close())
        self.log.close()
        return errors


def stale_digest_received(snapshot, address, prior_messages, heartbeat):
    received = snapshot["wire"]["received_syn"].get(address)
    if received is None or received["sequence"] <= prior_messages:
        return False
    return any(node["id"]["node_id"] == "b" and node["id"]["generation_id"] == 1
               and node["heartbeat"] == heartbeat for node in received["nodes"])


def interrupted(signal_number, _frame):
    raise InterruptedError(f"runner received signal {signal_number}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--max-seconds", type=float, default=180)
    args = parser.parse_args()
    args.baseline = args.baseline.resolve(strict=True)
    args.candidate = args.candidate.resolve(strict=True)
    args.evidence.mkdir(parents=True, exist_ok=False)
    args.evidence = args.evidence.resolve(strict=True)
    guard = Guard(args)
    signal.signal(signal.SIGTERM, interrupted)
    report = {
        "passed": False,
        "baseline_sha256": digest_file(args.baseline),
        "candidate_sha256": digest_file(args.candidate),
        "runner_sha256": digest_file(Path(__file__)),
        "parent_version": "0.11.1",
        "scope": "real UDP parent compatibility with accelerated test timing",
        "quickwit_http_or_grpc_qualification": False,
        "results": [],
    }
    start = time.monotonic()
    try:
        guard.check()
        require(report["baseline_sha256"] != report["candidate_sha256"],
                "baseline and candidate binaries must be distinct builds")
        for label, binaries in (
            ("baseline-baseline", (args.baseline, args.baseline)),
            ("candidate-candidate", (args.candidate, args.candidate)),
            ("baseline-candidate", (args.baseline, args.candidate)),
            ("candidate-baseline", (args.candidate, args.baseline)),
        ):
            scenario = Scenario(label, binaries, guard, args.evidence)
            try:
                scenario.run()
                report["results"].append({"scenario": label, "passed": True})
            finally:
                cleanup_errors = scenario.close()
                require(not cleanup_errors, "; ".join(cleanup_errors))
        report["passed"] = True
    except BaseException as error:
        report["passed"] = False
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        # A second interruption must not skip the bounded child cleanup below.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        final_cleanup_errors = []
        for peer in reversed(guard.peers):
            final_cleanup_errors.extend(peer.close())
        if final_cleanup_errors:
            report["passed"] = False
            report["cleanup_errors"] = final_cleanup_errors
        report.update(elapsed_seconds=time.monotonic() - start,
                      sampled_peak_aggregate_rss_bytes=guard.peak_rss,
                      min_workspace_free_bytes=guard.min_workspace_free,
                      min_tmp_free_bytes=guard.min_tmp_free)
        (args.evidence / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, sort_keys=True))
    require(report["passed"], report.get("error", "peer cleanup failed"))


if __name__ == "__main__":
    main()
