#!/usr/bin/env python3
"""Package a trusted, locally built native executable inside its Linux builder.

Run inside the same amd64 Ubuntu builder that compiled the executable. This copies
runtime dependencies, not a compiler. It does not establish reproducible builds or
license clearance for distribution. Never run ldd on untrusted executables.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--binary', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--source-commit', required=True)
a = p.parse_args()
if platform.machine() != 'x86_64':
    p.error('only the measured amd64 builder is supported')
if a.output.exists():
    p.error('output must be a fresh directory')
if not re.fullmatch('[0-9a-f]{40}', a.source_commit):
    p.error('source commit must be a full Git SHA')
a.output.mkdir(parents=True)
root = a.output / 'root'
(root / 'usr/local/bin').mkdir(parents=True)
subprocess.run(['strip', '-o', str(root / 'usr/local/bin/quickwit'), str(a.binary)], check=True)
shutil.copy2('/usr/bin/curl', root / 'usr/local/bin/curl')
libs = set()
for binary in (a.binary, Path('/usr/bin/curl')):
    result = subprocess.run(['ldd', str(binary)], check=True, text=True, capture_output=True).stdout
    if 'not found' in result:
        raise RuntimeError('unresolved runtime dependency')
    libs.update(re.findall(r'(/[^\s]+)', result))
for name in sorted(libs):
    src = Path(name)
    dst = root / src.relative_to('/')
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst, follow_symlinks=True)
# Local-only artifact: do not inject the builder's private proxy trust store.
manifest = {'source_commit': a.source_commit, 'architecture': platform.machine(),
            'original_binary_sha256': hashlib.sha256(a.binary.read_bytes()).hexdigest(),
            'files': {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest()
                      for f in sorted(root.rglob('*')) if f.is_file()},
            'scope': 'local runtime experiment; redistribution and reproducible builds unqualified'}
(a.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
shutil.copy2(Path(__file__).with_name('Dockerfile.runtime'), a.output / 'Dockerfile')
for f in a.output.rglob('*'):
    f.chmod(0o755 if f.is_dir() or bool(f.stat().st_mode & 0o111) else 0o644)
a.output.chmod(0o755)
print(json.dumps({'output': str(a.output), 'files': len(manifest['files'])}))
