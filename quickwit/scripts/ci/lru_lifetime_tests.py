#!/usr/bin/env python3
"""Compile-only regressions for the separately backported LRU lifetime repair."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

CASES = {
    "escape": ("E0515", '''use lru::LruCache;
fn escape() -> &'static mut u32 {
    let mut cache = LruCache::<String, u32>::unbounded();
    cache.get_or_insert_mut_ref("key", || 1)
}
fn main() { let _ = escape; }
'''),
    "alias": ("E0499", '''use lru::LruCache;
fn main() {
    let mut cache = LruCache::<String, u32>::unbounded();
    let first = cache.get_or_insert_mut_ref("first", || 1);
    let second = cache.get_or_insert_mut_ref("first", || 2);
    *first += *second;
}
'''),
    "valid_temporary_key": (None, '''use lru::LruCache;
fn lookup(cache: &mut LruCache<String, u32>) -> &mut u32 {
    let temporary_key = String::from("key");
    cache.get_or_insert_mut_ref(temporary_key.as_str(), || 1)
}
fn main() {
    let mut cache = LruCache::<String, u32>::unbounded();
    *lookup(&mut cache) = 2;
    let value = cache.get_or_insert_mut_ref("key", || 3);
    *value += 1;
}
'''),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cargo", default="cargo")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.output).free < 512 * 1024**2:
        raise SystemExit("Compiler probe requires a 512 MiB free-space reserve")
    scripts = Path(__file__).resolve().parent
    quickwit = scripts.parents[1]
    results = []
    for version in ("0.16.4", "0.17.0"):
        vendor = quickwit / f"vendor/lru-{version}"
        for mode in ("std", "default"):
            harness = args.output / f"{version}-{mode}"
            if harness.exists():
                raise SystemExit(f"Use a fresh output directory: {harness}")
            (harness / "src").mkdir(parents=True)
            (harness / "Cargo.toml").write_text(
                '[package]\nname="lru-backport-probe"\nversion="0.0.0"\nedition="2021"\n'
                '[workspace]\n[dependencies]\n'
                f'lru={{path={json.dumps(str(vendor))}, default-features={str(mode == "default").lower()}}}\n'
            )
            shutil.copyfile(scripts / f"lru-backport-locks/{version}-{mode}-probe.lock",
                            harness / "Cargo.lock")
            for name, (expected, source) in CASES.items():
                (harness / "src/main.rs").write_text(source)
                command = [args.cargo, "check", "--locked", "--offline", "--message-format=json",
                           "--manifest-path", str(harness / "Cargo.toml"),
                           "--target-dir", str(args.output / "target"), "-j", "1"]
                run = subprocess.run(command, capture_output=True, text=True, timeout=120)
                (harness / f"{name}.jsonl").write_text(run.stdout)
                (harness / f"{name}.stderr").write_text(run.stderr)
                errors = []
                for line in run.stdout.splitlines():
                    message = json.loads(line)
                    if message.get("reason") == "compiler-message" and message["message"]["level"] == "error":
                        code = message["message"].get("code")
                        errors.append(code["code"] if code else None)
                passed = (run.returncode == 0 and not errors) if expected is None else (
                    run.returncode != 0 and errors == [expected])
                results.append({"version": version, "mode": mode, "case": name,
                                "expected_error": expected, "errors": errors,
                                "exit_code": run.returncode, "passed": passed,
                                "command": command,
                                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                                "vendor_source_sha256": hashlib.sha256((vendor / "src/lib.rs").read_bytes()).hexdigest(),
                                "lock_sha256": hashlib.sha256((harness / "Cargo.lock").read_bytes()).hexdigest()})
                (args.output / "results.json").write_text(json.dumps(results, indent=2)+"\n")
                if not passed:
                    raise SystemExit(f"Unexpected compiler outcome: {version}/{mode}/{name}\n" + run.stderr + run.stdout)
    print("12 compile-only checks passed; no negative fixture was executed.")


if __name__ == "__main__":
    main()
