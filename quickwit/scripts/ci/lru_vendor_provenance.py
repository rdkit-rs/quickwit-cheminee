"""Verify reviewed LRU vendor bytes before constructing an advisory-identity input.

The projected lock is not a build lock or evidence that upstream advisories are fixed.
It restores the original crates.io identities so path patches cannot hide findings.
"""
import copy
import hashlib
import json
from pathlib import PurePosixPath
import re
import subprocess
import tomllib


REGISTRY = 'registry+https://github.com/rust-lang/crates.io-index'
MANIFEST = 'quickwit/vendor/lru-provenance.json'
MANIFEST_SHA256 = '2eb2d29502ea9bbd17959e2eb4631272fa610089abc0792380d81bb01cdbaa6a'
# The earlier reviewed tree remains auditable as history, but cannot be a new head.
HISTORICAL_MANIFEST_SHA256 = 'd0e37c16e82b5d5ec57d235b1f18f999f8b74d14f8265c1d2cbafca9aef62488'
CURRENT_PROFILE = 'pop-and-mutable-borrow-lifetime'
HISTORICAL_PROFILE = 'pop-only'
# These independently pinned identities are from the original Cargo.lock/crate archives.
BACKPORTS = {
    '0.16.4': ('7f66e8d5d03f609abc3a39e6f08e4164ebf1447a732906d39eb9b99b7919ef39',
               ['hashbrown 0.16.1'], 'lru_016'),
    '0.17.0': ('0e0b564323a0fb6d54b864f625ae139de9612e27edb944dda37c109f05aac531',
               ['hashbrown 0.17.1'], 'lru_017'),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class GitTree:
    """Read each revision's tracked audit inputs without checking out/building it."""

    def __init__(self, repository, revision):
        self.command = ['git', '--no-replace-objects', '-C', str(repository)]
        self.revision = self.git('rev-parse', '--verify', '--end-of-options',
                                 f'{revision}^{{commit}}').decode().strip()
        self.files = {}
        for entry in self.git('ls-tree', '-r', '-z', '--full-tree', self.revision,
                              '--', 'quickwit', '.cargo').split(b'\0'):
            if entry:
                metadata, path = entry.split(b'\t', 1)
                mode, kind, oid = metadata.decode().split()
                self.files[path.decode()] = (mode, kind, oid)

    def git(self, *arguments):
        return subprocess.check_output(self.command + list(arguments), timeout=15)

    def read(self, path):
        if path not in self.files:
            raise ValueError(f'missing revision input: {path}')
        mode, kind, oid = self.files[path]
        if mode not in ('100644', '100755') or kind != 'blob':
            raise ValueError(f'audit input is not a regular tracked file: {path}')
        if int(self.git('cat-file', '-s', oid)) > 4 * 1024 * 1024:
            raise ValueError(f'audit input exceeds 4 MiB: {path}')
        return self.git('cat-file', 'blob', oid)


def lru_entry(name, value):
    return name == 'lru' or isinstance(value, dict) and value.get('package') == 'lru'


def validate_overrides(tree, vendored):
    expected = {alias: {'package': 'lru', 'path': f'vendor/lru-{version}'}
                for version, (_, _, alias) in BACKPORTS.items()} if vendored else {}
    root_patches = {}
    input_hashes = {}
    for path in tree.files:
        parts = PurePosixPath(path).parts
        is_manifest = parts[-1] == 'Cargo.toml'
        is_config = len(parts) >= 2 and parts[-2] == '.cargo' and parts[-1] in ('config', 'config.toml')
        if path in ('.cargo', 'quickwit/.cargo'):
            raise ValueError(f'Cargo config directory is not a tracked directory: {path}')
        if not (is_manifest or is_config):
            continue
        content = tree.read(path)
        document = tomllib.loads(content.decode())
        input_hashes[path] = sha256(content)
        if is_config and any(key in document for key in ('paths', 'source', 'include')):
            raise ValueError(f'unverified Cargo source/path/include override: {path}')
        package = document.get('package', {})
        if package.get('name') == 'lru':
            version = package.get('version')
            if not vendored or version not in BACKPORTS or path != f'quickwit/vendor/lru-{version}/Cargo.toml':
                raise ValueError(f'unregistered local LRU package: {path}')
        for registry, patches in document.get('patch', {}).items():
            for name, value in patches.items():
                if lru_entry(name, value):
                    if path != 'quickwit/Cargo.toml' or registry != 'crates-io':
                        raise ValueError(f'unverified LRU patch: {path}')
                    root_patches[name] = value
        for name, value in document.get('replace', {}).items():
            if name.split(':', 1)[0] == 'lru' or lru_entry(name, value):
                raise ValueError(f'unverified LRU replacement: {path}')

        def dependencies(table):
            for name, value in table.items():
                if name in ('dependencies', 'dev-dependencies', 'build-dependencies'):
                    for dependency, specification in value.items():
                        if lru_entry(dependency, specification) and isinstance(specification, dict):
                            if set(specification) & {'path', 'git', 'registry', 'registry-index'}:
                                raise ValueError(f'unverified direct LRU source: {path}')
                elif isinstance(value, dict):
                    dependencies(value)

        dependencies(document)
    if 'quickwit/Cargo.toml' not in input_hashes or root_patches != expected:
        raise ValueError('Cargo.toml LRU patches do not match verified vendor provenance')
    return input_hashes


def validate_vendor(tree, *, role):
    if role not in ('base', 'head'):
        raise ValueError('explicit base or head role is required for LRU validation')
    if MANIFEST not in tree.files:
        if any(path.startswith('quickwit/vendor/lru-') for path in tree.files):
            raise ValueError('LRU vendor tree is missing its pinned provenance manifest')
        return [], None, None
    manifest = tree.read(MANIFEST)
    digest = sha256(manifest)
    if digest == MANIFEST_SHA256:
        profile = CURRENT_PROFILE
    elif digest == HISTORICAL_MANIFEST_SHA256:
        if role != 'base':
            raise ValueError('historical pop-only LRU provenance is permitted only for the base')
        profile = HISTORICAL_PROFILE
    else:
        raise ValueError('LRU provenance manifest differs from independently pinned SHA256')
    document = json.loads(manifest)
    if set(document) != {'schema_version', 'packages'} or document['schema_version'] != 1:
        raise ValueError('unsupported LRU provenance schema')
    packages = document['packages']
    if len(packages) != len(BACKPORTS) or {row['version'] for row in packages} != set(BACKPORTS):
        raise ValueError('unexpected LRU provenance versions')
    for package in packages:
        version = package['version']
        expected = {'name': 'lru', 'version': version, 'source': REGISTRY,
                    'checksum': BACKPORTS[version][0], 'path': f'vendor/lru-{version}'}
        if {key: value for key, value in package.items() if key != 'files'} != expected:
            raise ValueError('LRU provenance registry identity does not match pinned original')
        prefix = f"quickwit/{package['path']}/"
        actual_files = {path[len(prefix):] for path in tree.files if path.startswith(prefix)}
        if actual_files != set(package['files']):
            raise ValueError(f'LRU vendor file inventory differs: {version}')
        for path, file_digest in package['files'].items():
            relative = PurePosixPath(path)
            if relative.is_absolute() or '..' in relative.parts or relative.as_posix() != path:
                raise ValueError('invalid LRU provenance file path')
            if sha256(tree.read(prefix + path)) != file_digest:
                raise ValueError(f'LRU vendor file hash differs: {version}/{path}')
    return packages, digest, profile


def validate_and_project(tree, raw, *, role):
    if role not in ('base', 'head'):
        raise ValueError('explicit base or head role is required for LRU validation')
    if raw != tree.read('quickwit/Cargo.lock'):
        raise ValueError('supplied lockfile does not match its audited Git revision')
    packages, manifest_digest, profile = validate_vendor(tree, role=role)
    inputs = validate_overrides(tree, bool(packages))
    document = tomllib.loads(raw.decode())
    projected_document = copy.deepcopy(document)
    versions = set()
    projected_versions = []
    for package, projected in zip(document.get('package', []), projected_document.get('package', [])):
        if package['name'] != 'lru':
            continue
        version = package['version']
        if version in versions:
            raise ValueError(f'duplicate LRU version/source identities: {version}')
        versions.add(version)
        source = package.get('source')
        if source is not None and source != REGISTRY:
            raise ValueError(f'unregistered LRU source: {version}')
        if version in BACKPORTS:
            if role == 'head' and source == REGISTRY:
                raise ValueError(f'head cannot restore unpatched registry LRU: {version}')
            checksum, dependencies, _ = BACKPORTS[version]
            if package.get('dependencies', []) != dependencies:
                raise ValueError(f'LRU dependencies differ from pinned original: {version}')
            if source == REGISTRY and package.get('checksum') != checksum:
                raise ValueError(f'LRU registry checksum differs from pinned original: {version}')
        if source is None:
            if version not in BACKPORTS or not packages:
                raise ValueError(f'unregistered source-less LRU package: {version}')
            if set(package) != {'name', 'version', 'dependencies'}:
                raise ValueError(f'unexpected local LRU lock fields: {version}')
            projected.update(source=REGISTRY, checksum=BACKPORTS[version][0])
            projected_versions.append(version)
    if packages and set(projected_versions) != set(BACKPORTS):
        raise ValueError('verified LRU patches must resolve both original versions as local packages')
    # Insert identity fields only; preserve every existing byte, including unrelated packages.
    blocks = re.split(rb'(?m)(?=^\[\[package\]\]\r?$)', raw)
    if len(blocks) - 1 != len(document.get('package', [])):
        raise ValueError('unsupported Cargo.lock package-table formatting')
    for index, package in enumerate(document.get('package', []), 1):
        if package['name'] == 'lru' and package['version'] in projected_versions:
            newline = b'\r\n' if blocks[index].startswith(b'[[package]]\r\n') else b'\n'
            identity = (f'source = "{REGISTRY}"\nchecksum = "{BACKPORTS[package["version"]][0]}"\n')
            position = blocks[index].index(newline) + len(newline)
            blocks[index] = blocks[index][:position] + identity.encode().replace(b'\n', newline) + blocks[index][position:]
    projected = b''.join(blocks)
    if tomllib.loads(projected.decode()) != projected_document:
        raise ValueError('projection changed fields other than verified registry identities')
    return projected, {'revision': tree.revision, 'role': role, 'manifest_sha256': manifest_digest,
                       'vendor_profile': profile,
                       'verified_vendor_packages': packages, 'cargo_input_sha256': inputs,
                       'projected_lru_versions': projected_versions}
