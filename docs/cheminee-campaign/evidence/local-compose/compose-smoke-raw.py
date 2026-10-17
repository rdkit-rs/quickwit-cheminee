#!/usr/bin/env python3
"""Disposable Compose import/query/graceful-restart smoke. No chemistry benchmark."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--container', default='cheminee-local-cheminee-1')
p.add_argument('--url', default='http://127.0.0.1:7280')
a = p.parse_args()
if a.output.exists():
    p.error('choose a fresh output path')
http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
report = {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'scope': '1000 synthetic raw offers; single node, no Elasticsearch; graceful restart only',
          'stages': [], 'memory_samples': [], 'status': 'running'}
report['image'] = subprocess.check_output(['docker', 'inspect', a.container, '--format', '{{.Image}}'], text=True).strip()
report['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
phase = 'idle'
stop = threading.Event()
def sample():
    while not stop.is_set():
        try:
            values = subprocess.check_output(['docker', 'exec', a.container, 'sh', '-c',
                'cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.peak'], text=True, stderr=subprocess.DEVNULL).splitlines()
            report['memory_samples'].append({'phase': phase, 'monotonic': time.monotonic(),
                'cgroup_current_bytes': int(values[0]), 'cgroup_peak_bytes': int(values[1])})
        except (subprocess.CalledProcessError, ValueError, IndexError):
            pass # Restart temporarily has no running container.
        stop.wait(.5)
def request(method, path, body=None, content_type='application/json'):
    if isinstance(body, dict): body = json.dumps(body).encode()
    req = urllib.request.Request(a.url + path, data=body, method=method,
                                 headers={'Content-Type': content_type})
    start = time.monotonic()
    with http.open(req, timeout=90) as r:
        data = r.read()
        result = json.loads(data) if data else None
    report['stages'].append({'phase': phase, 'method': method, 'elapsed_seconds': time.monotonic() - start})
    return result
index = 'compose-smoke-' + uuid.uuid4().hex[:12]
created = False
thread = threading.Thread(target=sample, daemon=True)
thread.start()
try:
    assert request('GET', '/health/readyz') is True
    stop.wait(3)
    phase = 'create'
    request('POST', '/api/v1/indexes', {'version': '0.9', 'index_id': index,
        'doc_mapping': {'field_mappings': [
            {'name': 'record_id', 'type': 'u64', 'fast': True},
            {'name': 'supplier', 'type': 'text', 'tokenizer': 'raw'},
            {'name': 'smiles', 'type': 'text', 'tokenizer': 'raw'}]},
        'indexing_settings': {'commit_timeout_secs': 1, 'resources': {'heap_size': '32MiB'}}})
    created = True
    phase = 'import'
    data = b''.join((json.dumps({'record_id': n, 'supplier': 'Acme' if n % 2 else 'Beta',
                                'smiles': 'C[C@H](O)Cl'}) + '\n').encode() for n in range(1000))
    result = request('POST', '/api/v1/' + index + '/ingest?commit=wait_for&detailed_response=true',
                     data, 'application/x-ndjson')
    assert result.get('num_ingested_docs') == 1000 and result.get('num_rejected_docs') == 0, result
    def search():
        result = request('POST', '/api/v1/_elastic/' + index + '/_search?allow_partial_search_results=false',
                         {'query': {'term': {'supplier': 'Acme'}}, 'size': 10, 'track_total_hits': True,
                          'sort': [{'record_id': 'asc'}]})
        assert result['hits']['total'] == {'value': 500, 'relation': 'eq'}, result
        assert [h['_source']['record_id'] for h in result['hits']['hits']] == list(range(1,20,2))
        assert result['_shards']['failed'] == 0 and not result['timed_out']
    phase = 'query'
    for _ in range(20): search()
    phase = 'restart'
    subprocess.run(['docker', 'restart', '--time', '60', a.container], check=True, capture_output=True)
    deadline = time.monotonic() + 90
    while True:
        try:
            if request('GET', '/health/readyz') is True: break
        except (urllib.error.URLError, ConnectionError): pass
        if time.monotonic() > deadline: raise TimeoutError('readiness after restart')
        stop.wait(.25)
    phase = 'query_after_restart'
    # Node readiness precedes searcher membership propagation. Retry only this
    # known read-only startup error, never an ingest or mismatched result.
    while True:
        try:
            search()
            break
        except urllib.error.HTTPError as e:
            body = e.read()
            if e.code != 500 or b'no available searcher nodes' not in body:
                raise
            report.setdefault('startup_read_errors', []).append({'status': 500, 'reason': 'searcher_membership_pending'})
        if time.monotonic() > deadline: raise TimeoutError('searcher membership after restart')
        stop.wait(.25)
    report['status'] = 'passed'
    report['accepted'] = 1000
    report['filtered_count_before_and_after_restart'] = 500
except BaseException as e:
    report['error'] = type(e).__name__ + ': ' + str(e)
    report['status'] = 'failed'
    raise
finally:
    phase = 'cleanup'
    if created:
        try: request('DELETE', '/api/v1/indexes/' + index)
        except Exception as e: report['cleanup_error'] = type(e).__name__
    stop.set()
    thread.join(timeout=3)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:report[k] for k in ('status','scope')}))
