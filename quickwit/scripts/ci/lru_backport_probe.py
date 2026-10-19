#!/usr/bin/env python3
"""Build an isolated, exact LRU pop backport from checksum-verified cached crates.

Does not modify the workspace dependency graph or claim advisory clearance.
Run with an offline Cargo cache and a work directory on a spacious filesystem.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

HASHES = {
    "0.16.4": "7f66e8d5d03f609abc3a39e6f08e4164ebf1447a732906d39eb9b99b7919ef39",
    "0.17.0": "0e0b564323a0fb6d54b864f625ae139de9612e27edb944dda37c109f05aac531",
}
OLD = """                let mut old_node = unsafe {
                    let mut old_node = *Box::from_raw(old_node.as_ptr());
                    ptr::drop_in_place(old_node.key.as_mut_ptr());

                    old_node
                };

                self.detach(&mut old_node);"""
NEW = """                let node_ptr: *mut LruEntry<K, V> = old_node.as_ptr();

                // Detach before freeing the node or running the key destructor:
                // unwinding must not leave dangling links (RUSTSEC-2026-0253).
                self.detach(node_ptr);

                let mut old_node = unsafe { *Box::from_raw(node_ptr) };
                unsafe {
                    ptr::drop_in_place(old_node.key.as_mut_ptr());
                }"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--cargo", required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.work).free < 1024**3:
        raise SystemExit("Probe requires a 1 GiB free-space admission reserve")
    rustc = shutil.which("rustc")
    if rustc is None:
        raise SystemExit("rustc must be available on PATH")
    provenance = {
        "cargo": subprocess.check_output([args.cargo, "--version"], text=True).strip(),
        "rustc": subprocess.check_output([rustc, "-vV"], text=True).strip(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256(
            Path(__file__).with_name("lru_backport_regression.rs").read_bytes()).hexdigest(),
        "scope": "Exact-source backport probe; initial resolution uses the offline cache. "
                 "Retain generated Cargo.lock files for locked replay; not parent integration.",
    }
    (args.work / "provenance.json").write_text(json.dumps(provenance, indent=2)+"\n")
    results = []
    for version, expected in HASHES.items():
        archive = args.cache / f"lru-{version}.crate"
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"Archive checksum mismatch: {archive}")
        destination = args.work / f"lru-{version}"
        if destination.exists():
            raise SystemExit(f"Use a fresh work directory: {destination}")
        # Extract only the three known regular files needed by the dependent crate.
        with tarfile.open(archive) as tf:
            for name in ("Cargo.toml", "src/lib.rs", "LICENSE"):
                member = tf.getmember(f"lru-{version}/{name}")
                if not member.isfile() or member.size > 1024**2:
                    raise SystemExit(f"Unexpected archive member: {member.name}")
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tf.extractfile(member).read())
        source = destination / "src/lib.rs"
        original = source.read_text()
        if original.count(OLD) != 1:
            raise SystemExit("Expected exactly one upstream pop implementation")
        source.write_text(original.replace(OLD, NEW))
        record = {"version": version, "archive_sha256": actual,
                  "original_source_sha256": hashlib.sha256(original.encode()).hexdigest(),
                  "patched_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                  "advisory": "RUSTSEC-2026-0253", "runs": []}
        for default in (False, True):
            label = "default" if default else "std"
            harness = args.work / f"probe-{version}-{label}"
            (harness / "tests").mkdir(parents=True)
            (harness / "Cargo.toml").write_text(
                '[package]\nname="lru-backport-probe"\nversion="0.0.0"\nedition="2021"\n'
                '[workspace]\n[dependencies]\n'
                f'lru={{path="../lru-{version}", default-features={str(default).lower()}}}\n'
            )
            shutil.copyfile(Path(__file__).with_name("lru_backport_regression.rs"),
                            harness / "tests/regression.rs")
            command = [args.cargo, "test", "--offline", "--manifest-path",
                       str(harness / "Cargo.toml"), "--target-dir", str(args.work / "target"),
                       "--test", "regression", "-j", "1"]
            run = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, timeout=180)
            (harness / "test.log").write_text(run.stdout)
            record["runs"].append({"mode": label, "exit_code": run.returncode,
                                   "command": command,
                                   "log": str(harness / "test.log"),
                                   "log_sha256": hashlib.sha256(run.stdout.encode()).hexdigest(),
                                   "manifest_sha256": hashlib.sha256(
                                       (harness / "Cargo.toml").read_bytes()).hexdigest(),
                                   "lock_sha256": hashlib.sha256(
                                       (harness / "Cargo.lock").read_bytes()).hexdigest()
                                   if (harness / "Cargo.lock").exists() else None})
            if run.returncode:
                (args.work / "failed-run.json").write_text(json.dumps(record, indent=2)+"\n")
                raise SystemExit(run.stdout)
        results.append(record)
    (args.work / "results.json").write_text(json.dumps(results, indent=2)+"\n")
    print("Both versions passed two scoped tests in each feature mode; no parent integration claim.")


if __name__ == "__main__":
    main()
