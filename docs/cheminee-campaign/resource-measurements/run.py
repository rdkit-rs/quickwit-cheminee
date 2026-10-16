#!/usr/bin/env python3
"""Admit an already-running, verified local runtime before disposable smoke."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
SMOKE = ROOT / 'distribution/cheminee-local/smoke.py'


def inspect_container(name):
    return json.loads(subprocess.check_output(
        ['docker', 'inspect', name], text=True, timeout=5))[0]


def check_container(info, image):
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise ValueError('expected image must be a complete immutable local image ID')
    if info['Image'] != image:
        raise ValueError('container image identity mismatch')
    state = info['State']
    if (not state.get('Running') or state.get('OOMKilled') is not False
            or state.get('Health', {}).get('Status') != 'healthy'):
        raise ValueError('container must already be running and healthy without OOMKilled')
    limits = info['HostConfig']
    if limits.get('Memory', 0) <= 0 or limits.get('NanoCpus', 0) <= 0:
        raise ValueError('explicit container memory and CPU limits required')
    return {'id': info['Id'], 'image': image, 'memory_limit_bytes': limits['Memory'],
            'cpu_limit': limits['NanoCpus'] / 1e9}


def require_local_docker():
    # DOCKER_CONTEXT overrides DOCKER_HOST. Resolve the effective endpoint.
    if os.environ.get('DOCKER_CONTEXT') or not os.environ.get('DOCKER_HOST'):
        context = json.loads(subprocess.check_output(
            ['docker', 'context', 'inspect'], text=True, timeout=5))[0]
        endpoint = context['Endpoints']['docker']['Host']
    else:
        endpoint = os.environ['DOCKER_HOST']
    if not endpoint.startswith('unix:///'):
        raise ValueError('only a local Unix-socket Docker endpoint is supported')
    return endpoint


def positive(value):
    value = int(value)
    if value <= 0:
        raise argparse.ArgumentTypeError('must be positive')
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--container', default='cheminee-local-cheminee-1')
    p.add_argument('--image', required=True)
    p.add_argument('--elasticsearch-container')
    p.add_argument('--elasticsearch-image')
    p.add_argument('--storage-path', type=Path, required=True,
                   help='existing path on the Docker data filesystem, not an unrelated workspace mount')
    p.add_argument('--min-free-bytes', type=positive, required=True)
    p.add_argument('--memory-budget-bytes', type=positive, required=True)
    p.add_argument('--cpu-budget', type=positive, required=True)
    p.add_argument('--runtime-provenance', type=Path, required=True)
    p.add_argument('--runtime-provenance-sha256', required=True)
    p.add_argument('--execute', action='store_true', help='owner-authorized disposable import and graceful restart')
    a = p.parse_args()
    if bool(a.elasticsearch_container) != bool(a.elasticsearch_image):
        p.error('Elasticsearch container and image must be supplied together')
    # A new private directory prevents report overwrite and separates each run.
    a.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    a.output = a.output.resolve()
    report = {'status': 'failed', 'live_measurements': 'pending', 'started_unix': time.time(),
              'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'readiness_sha256': hashlib.sha256(SMOKE.with_name('readiness.py').read_bytes()).hexdigest(),
              'smoke_sha256': hashlib.sha256(SMOKE.read_bytes()).hexdigest(),
              'coexistence': 'idle neighbor only' if a.elasticsearch_container else 'none'}
    try:
        provenance = a.runtime_provenance.read_bytes()
        digest = hashlib.sha256(provenance).hexdigest()
        if digest != a.runtime_provenance_sha256:
            raise ValueError('runtime provenance checksum mismatch')
        evidence = json.loads(provenance)
        if evidence.get('image_id') != a.image:
            raise ValueError('provenance image_id must match admitted primary image')
        if evidence.get('source_commit') != 'a90687162c9037e159781b76e97ec43e0bb3a436':
            raise ValueError('provenance must attribute the exact v5 source commit')
        if not re.fullmatch(r'[0-9a-f]{64}', evidence.get('binary_sha256', '')):
            raise ValueError('provenance binary_sha256 is required')
        report['provenance_sha256'] = digest
        report['docker_endpoint'] = require_local_docker()
        docker_root = subprocess.check_output(['docker', 'info', '--format', '{{.DockerRootDir}}'],
                                              text=True, timeout=5).strip()
        if os.stat(docker_root).st_dev != os.stat(a.storage_path).st_dev:
            raise ValueError('storage-path must be on the Docker data filesystem')
        report['docker_root'] = docker_root
        report['storage_path'] = str(a.storage_path.resolve(strict=True))
        report['free_bytes_before'] = shutil.disk_usage(a.storage_path).free
        if report['free_bytes_before'] < a.min_free_bytes:
            raise ValueError('insufficient disk admission headroom')
        pairs = [(a.container, a.image)]
        if a.elasticsearch_container:
            pairs.append((a.elasticsearch_container, a.elasticsearch_image))
        infos = [inspect_container(name) for name, _ in pairs]
        for info in infos:
            for mount in info.get('Mounts', []):
                if mount.get('RW') and mount.get('Type') in ('bind', 'volume'):
                    if os.stat(mount['Source']).st_dev != os.stat(a.storage_path).st_dev:
                        raise ValueError('writable data mounts require admission on the same filesystem')
        bindings = infos[0].get('NetworkSettings', {}).get('Ports', {}).get('7280/tcp') or []
        if bindings != [{'HostIp': '127.0.0.1', 'HostPort': '7280'}]:
            raise ValueError('primary must bind only 127.0.0.1:7280 for smoke endpoint identity')
        containers = [check_container(info, image) for info, (_, image) in zip(infos, pairs)]
        if len({item['id'] for item in containers}) != len(containers):
            raise ValueError('primary and observed containers must be distinct')
        report['containers'] = containers
        if sum(c['memory_limit_bytes'] for c in containers) > a.memory_budget_bytes:
            raise ValueError('container ceilings exceed admitted memory budget')
        if sum(c['cpu_limit'] for c in containers) > a.cpu_budget:
            raise ValueError('container ceilings exceed admitted CPU budget')
        report['admission'] = {'min_free_bytes': a.min_free_bytes,
                               'memory_budget_bytes': a.memory_budget_bytes,
                               'cpu_budget': a.cpu_budget}
        if a.execute:
            command = [sys.executable, str(SMOKE), '--container', containers[0]['id'],
                       '--output', str(a.output / 'smoke.json')]
            if a.elasticsearch_container:
                command += ['--observe-container', containers[1]['id']]
            # Smoke owns cleanup and per-operation deadlines. Do not kill it mid-cleanup.
            result = subprocess.run(command, cwd=ROOT, check=False)
            report['smoke_exit_code'] = result.returncode
            smoke = json.loads((a.output / 'smoke.json').read_text())
            if result.returncode or smoke.get('status') != 'passed':
                raise RuntimeError('smoke failed; inspect retained smoke report')
            report['live_measurements'] = 'completed bounded synthetic smoke only'
        report['status'] = 'passed' if a.execute else 'admitted_not_executed'
    except Exception as error:
        report['error_type'] = type(error).__name__
        report['error'] = str(error) if isinstance(error, (ValueError, RuntimeError)) else 'preflight or execution failed'
    finally:
        if a.storage_path.exists():
            report['free_bytes_after'] = shutil.disk_usage(a.storage_path).free
        (a.output / 'admission.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'live_measurements': report['live_measurements']}))
    return 1 if report['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
