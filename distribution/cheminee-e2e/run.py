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

"""Real kind/SeaweedFS acceptance. All workloads and credentials are disposable."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError
from oracle import audit

ROOT = Path('.e2e').resolve()
EVIDENCE = ROOT / 'evidence'
KIND_IMAGE = 'kindest/node@sha256:ede5bb6984830375d264e41b7169d03643f586d3e35316bf5229eaeb12bb18e0'
WEED_IMAGE = 'chrislusf/seaweedfs@sha256:d67f9b5586f73b6623c143489849c958ae0ec36a698bf4243a19df07cfa28c22'
KUBECONFIG = ROOT / 'kubeconfig'
os.environ['KUBECONFIG'] = str(KUBECONFIG)
os.environ['AWS_EC2_METADATA_DISABLED'] = 'true'
FORWARDS = []
STOP = threading.Event()


def command(args, timeout=120, data=None):
    result = subprocess.run(args, input=data, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout)
    with (EVIDENCE / 'commands.log').open('a') as log:
        log.write(json.dumps({'argv': args, 'exit': result.returncode, 'output': result.stdout[-16000:]}) + '\n')
    if result.returncode:
        raise RuntimeError(f'command failed ({result.returncode}): {args[:3]}')
    return result.stdout


def kubectl(*args, **kwargs):
    return command(['kubectl', *args], **kwargs)


def apply(resource):
    name = resource['metadata']['name']
    (EVIDENCE / f'{resource["kind"]}-{name}.json').write_text(json.dumps(resource, indent=2))
    kubectl('apply', '-f', '-', data=json.dumps(resource))


def wait(predicate, timeout=120):
    deadline = time.monotonic() + timeout
    failures = []
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (urllib.error.URLError, ConnectionError, BotoCoreError, TimeoutError) as error:
            failures.append(str(error)[:250])
        time.sleep(2)
    raise TimeoutError('readiness timeout: ' + repr(failures[-5:]))


def forward(pod, local, remote):
    log = (EVIDENCE / f'forward-{pod}.log').open('w')
    process = subprocess.Popen(['kubectl', 'port-forward', '--address', '127.0.0.1', 'pod/' + pod,
                                f'{local}:{remote}'], stdout=log, stderr=subprocess.STDOUT)
    FORWARDS.append((process, log))
    return 'http://127.0.0.1:' + str(local)


def s3(port):
    return boto3.client('s3', endpoint_url=f'http://127.0.0.1:{port}', region_name='us-east-1',
        aws_access_key_id='local-acceptance', aws_secret_access_key='local-acceptance-only',
        config=Config(s3={'addressing_style': 'path'}, retries={'max_attempts': 0}, connect_timeout=5, read_timeout=60))


def weed(name, port):
    apply({'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': name, 'labels': {'app': name}},
        'spec': {'restartPolicy': 'Never', 'containers': [{'name': 'weed', 'image': WEED_IMAGE,
            'args': ['server', '-dir=/data', '-s3', '-ip=' + name, '-ip.bind=0.0.0.0',
                     '-volume.max=8', '-master.volumeSizeLimitMB=256'],
            'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'}, 'limits': {'cpu': '1', 'memory': '768Mi'}},
            'readinessProbe': {'tcpSocket': {'port': 8333}, 'periodSeconds': 2, 'failureThreshold': 90},
            'volumeMounts': [{'name': 'data', 'mountPath': '/data'}]}],
            'volumes': [{'name': 'data', 'emptyDir': {}}]}})
    apply({'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': name},
        'spec': {'selector': {'app': name}, 'ports': [{'name': 'p' + str(p), 'port': p} for p in (8333, 8888, 9333, 19333, 18080, 18888, 8080)]}})
    kubectl('wait', '--for=condition=Ready', 'pod/' + name, '--timeout=180s', timeout=190)
    forward(name, port, 8333)
    client = s3(port)
    wait(lambda: client.list_buckets() is not None)
    client.create_bucket(Bucket='catalog')
    return client


def quickwit(name, store, data_name, image):
    config = json.loads(json.dumps(BASE_CONFIG))
    config.update(cluster_id=name, node_id=name, metastore_uri='s3://catalog/metastore',
                  default_index_root_uri='s3://catalog/indexes', storage={'s3': {
                      'endpoint': f'http://{store}:8333', 'region': 'us-east-1', 'force_path_style_access': True}})
    apply({'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': name}, 'data': {'quickwit.json': json.dumps(config)}})
    apply({'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': name}, 'spec': {
        'restartPolicy': 'Never', 'terminationGracePeriodSeconds': 90,
        'initContainers': [{'name': 'permissions', 'image': image, 'imagePullPolicy': 'Never',
            'command': ['/bin/sh', '-c', 'chown 10001:10001 /var/lib/cheminee'],
            'securityContext': {'runAsUser': 0}, 'volumeMounts': [{'name': 'data', 'mountPath': '/var/lib/cheminee'}]}],
        'containers': [{'name': 'cheminee', 'image': image, 'imagePullPolicy': 'Never',
            'args': ['run', '--config', '/config/quickwit.json'],
            'readinessProbe': {'httpGet': {'path': '/health/readyz', 'port': 7280}, 'periodSeconds': 2, 'failureThreshold': 90},
            'env': [{'name': k, 'value': v} for k, v in {
                'QW_DISABLE_TELEMETRY': '1', 'AWS_ACCESS_KEY_ID': 'local-acceptance',
                'AWS_SECRET_ACCESS_KEY': 'local-acceptance-only', 'AWS_EC2_METADATA_DISABLED': 'true',
                'TF_NUM_INTRAOP_THREADS': '1', 'TF_NUM_INTEROP_THREADS': '1', 'OMP_NUM_THREADS': '1'}.items()],
            'resources': {'requests': {'cpu': '500m', 'memory': '1Gi'}, 'limits': {'cpu': '2', 'memory': '4Gi'}},
            'securityContext': {'allowPrivilegeEscalation': False, 'runAsUser': 10001},
            'volumeMounts': [{'name': 'data', 'mountPath': '/var/lib/cheminee'}, {'name': 'config', 'mountPath': '/config', 'readOnly': True}]}],
        'volumes': [{'name': 'data', 'hostPath': {'path': '/var/local/cheminee/' + data_name, 'type': 'DirectoryOrCreate'}},
                    {'name': 'config', 'configMap': {'name': name}}]}})
    kubectl('wait', '--for=condition=Ready', 'pod/' + name, '--timeout=180s', timeout=190)
    base = forward(name, 17280, 7280)
    def ready():
        with urllib.request.urlopen(base + '/health/readyz', timeout=3) as response:
            return response.status == 200
    wait(ready, timeout=120)
    with urllib.request.urlopen(base + '/api/v1/version', timeout=10) as response:
        version = json.load(response)
    expected = json.loads((ROOT / 'candidate/pilot-manifest.json').read_text())['source_commit']
    if version['build']['commit_hash'] != expected:
        raise ValueError('running native server is not the accepted source revision')
    (EVIDENCE / (name + '-version.json')).write_text(json.dumps(version, indent=2))
    return base


def clean_stop(name):
    before = json.loads(kubectl('get', 'pod', name, '-o', 'json'))
    status = before['status']['containerStatuses'][0]
    if status['restartCount'] != 0:
        raise ValueError('unexpected restart before clean stop')
    kubectl('exec', name, '--', '/bin/sh', '-c', 'kill -TERM 1')
    def stopped():
        pod = json.loads(kubectl('get', 'pod', name, '-o', 'json'))
        state = pod['status']['containerStatuses'][0]
        if state['containerID'] != status['containerID'] or state['restartCount'] != 0:
            raise ValueError('container incarnation changed during stop')
        end = state['state'].get('terminated')
        if not end:
            return False
        (EVIDENCE / (name + '-stopped.json')).write_text(json.dumps(pod, indent=2))
        if end['exitCode'] != 0 or end['reason'] == 'OOMKilled':
            raise ValueError('abnormal shutdown; no forced-kill fallback')
        return True
    wait(stopped, timeout=95)
    for process, log in FORWARDS:
        if process.poll() is None and '17280:7280' in process.args:
            process.terminate(); process.wait(timeout=10); log.close()


def snapshot(client, directory, restore=None):
    directory.mkdir(exist_ok=False)
    entries = []
    for page in client.get_paginator('list_objects_v2').paginate(Bucket='catalog'):
        for obj in page.get('Contents', []):
            if shutil.disk_usage(ROOT).free < 4 * 1024**3:
                raise RuntimeError('reserve violated during backup')
            key = obj['Key']
            path = directory / hashlib.sha256(key.encode()).hexdigest()
            digest = hashlib.sha256()
            with path.open('xb') as target:
                body = client.get_object(Bucket='catalog', Key=key)['Body']
                for part in body.iter_chunks(1024 * 1024):
                    target.write(part); digest.update(part)
                body.close()
            if path.stat().st_size != obj['Size']:
                raise ValueError('backup length mismatch')
            entries.append({'key': key, 'bytes': obj['Size'], 'sha256': digest.hexdigest()})
            if restore:
                with path.open('rb') as data:
                    restore.put_object(Bucket='catalog', Key=key, Body=data)
    if not entries or not any(e['key'].endswith('.split') for e in entries):
        raise ValueError('no real index splits found in S3')
    return sorted(entries, key=lambda e: e['key'])


def resource_monitor():
    while not STOP.is_set():
        row = {'time': time.time(), 'disk_free': shutil.disk_usage(ROOT).free}
        try:
            row['pods'] = json.loads(kubectl('get', 'pods', '-o', 'json'))
            row['docker_stats'] = command(['docker', 'stats', '--no-stream', '--format', '{{json .}}'], timeout=20)
            for pod in row['pods']['items']:
                if pod['metadata']['name'].startswith('cheminee-') and pod['status']['phase'] == 'Running':
                    row[pod['metadata']['name']] = kubectl('exec', pod['metadata']['name'], '--', '/bin/sh', '-c',
                        'cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.peak /sys/fs/cgroup/memory.events', timeout=15)
        except Exception as error:
            row['error'] = str(error)
        with (EVIDENCE / 'resources.ndjson').open('a') as log:
            log.write(json.dumps(row) + '\n')
        STOP.wait(20)


BASE_CONFIG = {'version': '0.8', 'listen_address': '0.0.0.0', 'data_dir': '/var/lib/cheminee',
    'rest': {'listen_port': 7280}, 'indexer': {'enable_otlp_endpoint': False,
        'split_store_max_num_bytes': '256MiB', 'merge_concurrency': 1},
    'searcher': {'fast_field_cache_capacity': '32MiB', 'split_footer_cache_capacity': '16MiB',
        'partial_request_cache_capacity': '8MiB', 'predicate_cache_capacity': '8MiB',
        'warmup_memory_budget': '128MiB', 'warmup_single_split_initial_allocation': '8MiB',
        'max_num_concurrent_split_searches': 2},
    'ingest_api': {'max_queue_memory_usage': '64MiB', 'max_queue_disk_usage': '512MiB'}}


def main():
    result = {'status': 'failed', 'phases': {}, 'started': time.time(),
              'scope': 'Cheminee facade, native chemistry, kind, real SeaweedFS, 100k distinct-input corpus',
              'not_proven': ['crash/WAL durability', 'HA', 'production throughput', 'online backup']}
    monitor = None
    try:
        sys.path.insert(0, str(ROOT / 'source/distribution/cheminee-local'))
        from pilot_storage import journal_inventory
        kind = ROOT / 'kind'
        urllib.request.urlretrieve('https://github.com/kubernetes-sigs/kind/releases/download/v0.30.0/kind-linux-amd64', kind)
        if hashlib.sha256(kind.read_bytes()).hexdigest() != '517ab7fc89ddeed5fa65abf71530d90648d9638ef0c4cde22c2c11f8097b8889':
            raise ValueError('kind checksum mismatch')
        kind.chmod(0o755)
        config = ROOT / 'kind.yaml'
        config.write_text('kind: Cluster\napiVersion: kind.x-k8s.io/v1alpha4\nnetworking:\n  ipFamily: ipv4\n  apiServerAddress: "127.0.0.1"\nnodes:\n- role: control-plane\n')
        command([str(kind), 'create', 'cluster', '--name', 'cheminee-e2e', '--image', KIND_IMAGE,
                 '--config', str(config), '--kubeconfig', str(KUBECONFIG), '--wait', '180s', '--retain'], timeout=420)
        command(['docker', 'load', '-i', str(ROOT / 'candidate/cheminee-image.tar')], timeout=300)
        pilot = json.loads((ROOT / 'candidate/pilot-manifest.json').read_text())
        image_id = pilot['image']['local_config_digest']
        command(['docker', 'tag', image_id, 'cheminee:acceptance'])
        command([str(kind), 'load', 'docker-image', '--name', 'cheminee-e2e', 'cheminee:acceptance'], timeout=300)
        source = weed('seaweed-source', 18333)
        monitor = threading.Thread(target=resource_monitor, daemon=True); monitor.start()
        base = quickwit('cheminee-source-a', 'seaweed-source', 'source', 'cheminee:acceptance')
        work = ROOT / 'catalog'; work.mkdir()
        env = dict(os.environ, PILOT_SOURCE=str(ROOT / 'source'), SDK_EXPECTED_VERSION=pilot['candidate_version'],
                   SDK_SMOKE_HOST=base.removeprefix('http://'), CATALOG_WORK=str(work),
                   CATALOG_CORPUS=str(ROOT / 'corpus/catalog-offers-100k.ndjson'),
                   CATALOG_NATIVE_ORACLE=str(ROOT / 'candidate/catalog-oracle.ndjson'))
        def phase(name):
            print(json.dumps({'event': 'phase_started', 'phase': name, 'time': time.time()}), flush=True)
            env['PHASE_RESULT'] = str(EVIDENCE / (name + '.json'))
            log_path = EVIDENCE / (name + '.log')
            with log_path.open('w') as log:
                subprocess.run(['ruby', 'distribution/cheminee-e2e/catalog.rb', name], env=env,
                    stdout=log, stderr=subprocess.STDOUT, check=True, timeout=2800)
            receipt = json.loads(Path(env['PHASE_RESULT']).read_text())
            result['phases'][name] = receipt
            print(json.dumps({'event': 'phase_completed', 'phase': name, 'receipt': receipt}), flush=True)
            return receipt
        first = phase('create')
        audit(work / 'initial.ndjson', base, first['pointer']['active'], EVIDENCE)
        second = phase('refresh')
        audit(work / 'refreshed.ndjson', base, second['pointer']['active'], EVIDENCE)
        clean_stop('cheminee-source-a')
        base = quickwit('cheminee-source-b', 'seaweed-source', 'source', 'cheminee:acceptance')
        phase('verify')
        clean_stop('cheminee-source-b')
        backup = snapshot(source, ROOT / 's3-backup')
        command(['docker', 'cp', 'cheminee-e2e-control-plane:/var/local/cheminee/source', str(ROOT / 'data-backup')])
        shutil.copytree(work, ROOT / 'journal-backup')
        local_data = journal_inventory(ROOT / 'data-backup')
        journal_data = journal_inventory(ROOT / 'journal-backup')
        if journal_data != journal_inventory(work):
            raise ValueError('backup journal differs')
        # Original S3 process is stopped before restore: no source read-through.
        clean_stop('seaweed-source')
        restored = weed('seaweed-restored', 18334)
        if restored.list_objects_v2(Bucket='catalog').get('KeyCount') != 0:
            raise ValueError('restore destination not empty')
        for item in backup:
            path = ROOT / 's3-backup' / hashlib.sha256(item['key'].encode()).hexdigest()
            with path.open('rb') as body:
                restored.put_object(Bucket='catalog', Key=item['key'], Body=body)
        actual = snapshot(restored, ROOT / 'restore-readback')
        if actual != backup:
            raise ValueError('restored object bytes differ')
        (EVIDENCE / 's3-object-inventory.json').write_text(json.dumps(backup, indent=2))
        command(['docker', 'exec', 'cheminee-e2e-control-plane', 'mkdir', '/var/local/cheminee/restored'])
        command(['docker', 'cp', str(ROOT / 'data-backup') + '/.', 'cheminee-e2e-control-plane:/var/local/cheminee/restored'])
        command(['docker', 'cp', 'cheminee-e2e-control-plane:/var/local/cheminee/restored', str(ROOT / 'data-readback')])
        if journal_inventory(ROOT / 'data-readback') != local_data:
            raise ValueError('restored local data bytes/permissions differ')
        restored_work = ROOT / 'restored-catalog'
        shutil.copytree(ROOT / 'journal-backup', restored_work)
        if journal_inventory(restored_work) != journal_data:
            raise ValueError('restored journal bytes/permissions differ')
        (EVIDENCE / 'local-backup-inventory.json').write_text(json.dumps({'data': local_data, 'journal': journal_data}, indent=2))
        base = quickwit('cheminee-restored', 'seaweed-restored', 'restored', 'cheminee:acceptance')
        env['CATALOG_WORK'] = str(restored_work)
        phase('restored')
        rollback = phase('rollback')
        audit(restored_work / 'rolled-back.ndjson', base, rollback['pointer']['active'], EVIDENCE)
        clean_stop('cheminee-restored')
        result.update(status='passed', object_count=len(backup), independent_restore_endpoint=True)
    except Exception as error:
        result['error'] = repr(error)
        raise
    finally:
        STOP.set()
        if monitor: monitor.join(timeout=45)
        result['finished'] = time.time()
        (EVIDENCE / 'result.json').write_text(json.dumps(result, indent=2))
        for process, log in FORWARDS:
            if process.poll() is None: process.terminate()
            if not log.closed: log.close()


if __name__ == '__main__':
    main()
