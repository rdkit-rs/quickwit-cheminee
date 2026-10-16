#!/usr/bin/env python3
"""Cheap, offline dependency checks; does not invoke Cargo or create containers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shlex
import shutil
import time

if not __debug__:
    raise SystemExit('dependency assertions require unoptimized Python')


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--tensorflow-pc', type=Path, required=True)
    p.add_argument('--tensorflow-library', type=Path, action='append', required=True)
    a=p.parse_args()
    if a.output.exists(): p.error('fresh output required')
    cwd=Path.cwd()
    r={'created_unix':time.time(), 'cwd':str(cwd), 'status':'failed',
       'scope':'offline dependency readiness, not build/test success or complete Cargo cache proof',
       'environment':{k:os.environ.get(k) for k in ('PKG_CONFIG_PATH','QW_KRB5_CRATE')},
       'file_hashes':{}, 'network_required_for_selected_native_dependencies':False}
    try:
        unsupported=[k for k in os.environ if ('PKG_CONFIG' in k and k!='PKG_CONFIG_PATH') or 'TENSORFLOW' in k or k.startswith('TF_RUST_') or k=='CARGO_BUILD_TARGET']
        assert not unsupported, 'unsupported dependency overrides: '+','.join(sorted(unsupported))
        crate=Path(os.environ['QW_KRB5_CRATE']).resolve()
        expected='a04b2f0dfefd7b54af22d22768dc3ab1ed5e55e6d5ff6af3f619069aa17c0ba4'
        assert digest(crate)==expected, 'cached Kerberos crate checksum mismatch'
        lock=(cwd/'Cargo.lock').read_text()
        assert 'name = "krb5-src"\nversion = "0.3.4"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\nchecksum = "'+expected+'"' in lock
        pc=a.tensorflow_pc.resolve()
        actual_pc=Path(subprocess.check_output(['pkg-config','--variable=pcfiledir','tensorflow'],text=True,timeout=5).strip())/'tensorflow.pc'
        assert actual_pc.resolve()==pc, 'pkg-config resolves another TensorFlow recipe'
        version=subprocess.check_output(['pkg-config','--modversion','tensorflow'],text=True,timeout=5).strip()
        flags=shlex.split(subprocess.check_output(['pkg-config','--libs','tensorflow'],text=True,timeout=5))
        directories=[Path(x[2:]) for x in flags if x.startswith('-L')]
        names=[x[2:] for x in flags if x.startswith('-l')]
        assert len(directories)==1 and set(names)=={'tensorflow_cc','tensorflow_framework'} and len(flags)==3, 'unsupported TensorFlow link recipe'
        links=[directories[0]/('lib'+name+'.so') for name in names]
        selected=[x.resolve(strict=True) for x in links]
        libraries=[x.resolve(strict=True) for x in a.tensorflow_library]
        assert len(libraries)==len(set(libraries))==2 and set(libraries)==set(selected), 'supplied libraries differ from actual pkg-config selection'
        pkg_config=Path(shutil.which('pkg-config')).resolve(strict=True)
        files=[cwd/'Cargo.lock',cwd/'scripts/ci/with-krb5-c23.sh',cwd/'scripts/ci/krb5-c23.patch',crate,pc,pkg_config,*libraries]
        r['file_hashes']={str(x):digest(x) for x in files}
        r.update(status='passed',tensorflow_version=version,tensorflow_pc=str(pc),tensorflow_libraries=[str(x) for x in libraries],kerberos_crate=str(crate),pkg_config_executable=str(pkg_config),tensorflow_link_flags=flags,tensorflow_link_paths={str(p):str(p.resolve()) for p in links})
    except Exception as error:
        r['error_type']=type(error).__name__;r['reason']=str(error)
        r['next_action']='Resolve dependency preparation separately; do not launch a large build to discover it.'
    a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:r[k] for k in ('status','scope')}))
    return 0 if r['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
