#!/usr/bin/env python3
"""Install an existing Python test lock into a fresh venv without pip or Pipenv.

This does not resolve dependencies or build source distributions. It checks the
Pipfile hash, selects compatible wheels whose hashes are already in the lock,
and verifies their dependency metadata before calling PyPA installer.
"""
import argparse
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
import urllib.parse
import urllib.request
import venv
import zipfile


# Pure Python wheels with no runtime dependencies. Keep their complete graphs
# and bundled code in the dependency preflight, not just the package names.
BOOTSTRAP = {
    "installer": (
        "https://files.pythonhosted.org/packages/e5/ca/1172b6638d52f2d6caa2dd262ec4c811ba59eee96d54a7701930726bce18/installer-0.7.0-py3-none-any.whl",
        "05d1933f0a5ba7d8d6296bb6d5018e7c94fa473ceb10cf198a92ccea19c27b53",
    ),
    "packaging": (
        "https://files.pythonhosted.org/packages/20/12/38679034af332785aac8774540895e234f4d07f7545804097de4b666afd8/packaging-25.0-py3-none-any.whl",
        "29572ef2b1f17581046b3a2227d5c611fb25ec70ca1ba8554b24b0e69331a484",
    ),
}


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def read_lock(path):
    lock = json.loads(path.read_text())
    pipfile = tomllib.loads(path.with_name("Pipfile").read_text())
    if set(pipfile) - {"source", "requires", "packages", "dev-packages"}:
        raise ValueError("unsupported Pipfile sections; update the lock installer explicitly")
    hashed = {
        "_meta": {"sources": pipfile["source"], "requires": pipfile.get("requires", {})},
        "default": pipfile.get("packages", {}),
        "develop": pipfile.get("dev-packages", {}),
    }
    digest = sha256(json.dumps(hashed, sort_keys=True, separators=(",", ":")).encode())
    if lock["_meta"]["hash"]["sha256"] != digest:
        raise ValueError("Pipfile.lock is stale relative to Pipfile")
    expected_source = [{"name": "pypi", "url": "https://pypi.org/simple", "verify_ssl": True}]
    if lock["_meta"]["sources"] != expected_source or pipfile["source"] != expected_source:
        raise ValueError("only the verified PyPI source is supported")
    required = lock["_meta"].get("requires", {})
    if required != pipfile.get("requires", {}) or required.get("python_version") != f"{sys.version_info.major}.{sys.version_info.minor}":
        raise ValueError("run this installer with the Python version named in Pipfile.lock")
    if lock.get("develop") or pipfile.get("dev-packages"):
        raise ValueError("development dependency groups need an explicit installation policy")
    for name, spec in lock["default"].items():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
            raise ValueError(f"invalid package name: {name}")
        if set(spec) - {"version", "hashes", "markers", "index"}:
            raise ValueError(f"unsupported lock entry for {name}")
        if not re.fullmatch(r"==[A-Za-z0-9][A-Za-z0-9.!+_-]*", spec.get("version", "")):
            raise ValueError(f"{name} is not exactly pinned")
        if not spec.get("hashes") or any(not re.fullmatch(r"sha256:[0-9a-f]{64}", h) for h in spec["hashes"]):
            raise ValueError(f"{name} needs SHA-256 distribution hashes")
        if spec.get("index", "pypi") != "pypi":
            raise ValueError(f"unsupported package index for {name}")
    return lock, pipfile


def download(url, digest, directory):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org":
        raise ValueError("wheel downloads must use files.pythonhosted.org over HTTPS")
    path = directory / Path(parsed.path).name
    if not path.name.endswith(".whl"):
        raise ValueError("source distributions are not installed")
    with urllib.request.urlopen(url, timeout=30) as response:
        raw = response.read()
    if sha256(raw) != digest:
        raise ValueError(f"SHA-256 mismatch for {path.name}")
    path.write_bytes(raw)
    return path


def wheel_metadata(path):
    with zipfile.ZipFile(path) as wheel:
        names = [n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ValueError(f"expected one wheel METADATA file in {path.name}")
        return BytesParser().parsebytes(wheel.read(names[0]))


def select_wheel(name, spec, release, supported_tags):
    from packaging.utils import canonicalize_name, parse_wheel_filename
    from packaging.version import Version

    candidates = []
    for item in release["urls"]:
        if item.get("packagetype") != "bdist_wheel" or item.get("yanked"):
            continue
        digest = item["digests"]["sha256"]
        if "sha256:" + digest not in spec["hashes"]:
            continue
        wheel_name, version, _, tags = parse_wheel_filename(item["filename"])
        if wheel_name != canonicalize_name(name) or version != Version(spec["version"][2:]):
            continue
        ranks = [supported_tags[tag] for tag in tags if tag in supported_tags]
        if ranks:
            candidates.append((min(ranks), item["filename"], item))
    if not candidates:
        raise ValueError(f"no compatible hash-locked wheel for {name}{spec['version']}")
    return min(candidates, key=lambda candidate: candidate[:2])[2]


def verify_closure(selected, metadata, direct):
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.utils import canonicalize_name
    from packaging.version import Version

    versions = {canonicalize_name(n): Version(s["version"][2:]) for n, s in selected.items()}
    for name, constraint in direct.items():
        if not isinstance(constraint, str):
            raise ValueError(f"unsupported direct requirement for {name}")
        version = versions.get(canonicalize_name(name))
        if version is None or version not in SpecifierSet("" if constraint == "*" else constraint):
            raise ValueError(f"direct requirement missing or incompatible: {name} {constraint}")
    for name, meta in metadata.items():
        if canonicalize_name(meta["Name"]) != canonicalize_name(name) or Version(meta["Version"]) != versions[canonicalize_name(name)]:
            raise ValueError(f"wheel metadata identity mismatch for {name}")
        if meta.get("Requires-Python") and Version(".".join(map(str, sys.version_info[:3]))) not in SpecifierSet(meta["Requires-Python"]):
            raise ValueError(f"unsupported Python interpreter for {name}")
        for raw in meta.get_all("Requires-Dist", []):
            requirement = Requirement(raw)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            if requirement.url or requirement.extras:
                raise ValueError(f"dependency needs an explicit URL/extra policy: {name} -> {raw}")
            version = versions.get(canonicalize_name(requirement.name))
            if version is None or version not in requirement.specifier:
                raise ValueError(f"incomplete or incompatible lock: {name} -> {raw}")


def install(lock_path, destination):
    lock, pipfile = read_lock(lock_path)
    if destination.exists():
        raise ValueError("the virtual environment destination must not exist")
    with tempfile.TemporaryDirectory(prefix="quickwit-python-wheels-") as temporary:
        directory = Path(temporary)
        bootstrap = {name: download(url, digest, directory) for name, (url, digest) in BOOTSTRAP.items()}
        for path in bootstrap.values():
            if wheel_metadata(path).get_all("Requires-Dist", []):
                raise ValueError("bootstrap wheels must have no dependencies")
        sys.path.insert(0, str(bootstrap["packaging"]))
        from packaging.markers import Marker
        from packaging.tags import sys_tags

        supported = {tag: rank for rank, tag in enumerate(sys_tags())}
        selected = {name: spec for name, spec in lock["default"].items()
                    if not spec.get("markers") or Marker(spec["markers"]).evaluate()}
        wheels, metadata, evidence = {}, {}, {}
        for name, spec in sorted(selected.items()):
            url = f"https://pypi.org/pypi/{name}/{spec['version'][2:]}/json"
            with urllib.request.urlopen(url, timeout=30) as response:
                release = json.load(response)
            item = select_wheel(name, spec, release, supported)
            digest = item["digests"]["sha256"]
            wheels[name] = download(item["url"], digest, directory)
            metadata[name] = wheel_metadata(wheels[name])
            evidence[name] = {"version": spec["version"][2:], "wheel": item["filename"], "sha256": digest}
        verify_closure(selected, metadata, pipfile.get("packages", {}))
        venv.EnvBuilder(with_pip=False).create(destination)
        python = destination / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        entry = "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('installer',run_name='__main__')"
        for wheel in wheels.values():
            subprocess.run([str(python), "-I", "-c", entry, str(bootstrap["installer"]), "--no-compile-bytecode", str(wheel)], check=True)
        manifest = {"lock_sha256": sha256(lock_path.read_bytes()), "python": sys.version,
                    "bootstrap": {name: {"wheel": Path(url).name, "sha256": digest} for name, (url, digest) in BOOTSTRAP.items()},
                    "packages": evidence}
        (destination / "install-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps({"python": str(python), "packages": len(wheels), "manifest": str(destination / "install-manifest.json")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--venv", type=Path, required=True)
    args = parser.parse_args()
    try:
        install(args.lock.resolve(), args.venv.resolve())
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Python test environment failed: {error}\n")


if __name__ == "__main__":
    main()
