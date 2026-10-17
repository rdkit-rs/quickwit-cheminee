#!/usr/bin/env python3
"""Disposable Compose import/query/graceful-restart smoke. Native preparation and exact graph smoke; no benchmark."""
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
from readiness import wait_ready, assert_container_state, container_incarnation, assert_incarnation

if not __debug__:
    raise SystemExit('Run without Python optimization: correctness assertions are required')

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--container', default='cheminee-local-cheminee-1')
p.add_argument('--url', default='http://127.0.0.1:7280')
p.add_argument('--observe-container', action='append', default=[],
               help='Also sample a running local container; does not create load in it')
a = p.parse_args()
if a.container in a.observe_container:
    p.error('primary container cannot also be observed')
if len(a.observe_container)>3 or len(set(a.observe_container))!=len(a.observe_container):
    p.error('observe at most three distinct containers')
if a.output.exists():
    p.error('choose a fresh output path')
http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
report = {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'scope': '1000 synthetic offers, native preparation and exact identity; single node, no Elasticsearch; graceful restart only',
          'stages': [], 'memory_samples': [], 'status': 'running'}
report['image'] = subprocess.check_output(['docker', 'inspect', a.container, '--format', '{{.Image}}'], text=True, timeout=5).strip()
report['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
report['readiness_sha256'] = hashlib.sha256(Path(__file__).with_name('readiness.py').read_bytes()).hexdigest()
report['observed_containers'] = {}
for container in a.observe_container:
    report['observed_containers'][container] = {'image': subprocess.check_output(
        ['docker', 'inspect', container, '--format', '{{.Image}}'], text=True, timeout=5).strip(), 'samples': [], 'counter_scope': 'container lifetime; peaks and OOM counts are not run deltas'}
if a.observe_container:
    report['scope'] = '1000 synthetic offers with additional containers observed; no workload generated in observed containers; graceful restart only'
def inspect_incarnation(container):
    info = json.loads(subprocess.check_output(['docker', 'inspect', container], text=True, timeout=5))[0]
    return container_incarnation(info)

# Record identities before any import. Automatic restart must be disabled for
# the whole measurement, including the one explicitly requested restart window.
report['initial_incarnations'] = {name: inspect_incarnation(name) for name in [a.container, *a.observe_container]}
expected_incarnations = dict(report['initial_incarnations'])
phase = 'idle'
stop = threading.Event()
def sample_impl():
    while not stop.is_set():
        sample_phase, sample_start = phase, time.monotonic()
        try:
            values = subprocess.check_output(['docker', 'exec', a.container, 'cat', '/sys/fs/cgroup/memory.current', '/sys/fs/cgroup/memory.peak',
                '/proc/1/status', '/sys/fs/cgroup/memory.events'], text=True, stderr=subprocess.DEVNULL, timeout=3).splitlines()
            fields = {}
            for line in values[2:]:
                pair = line.split()
                if len(pair) >= 2 and pair[1].isdigit(): fields[pair[0].rstrip(':')] = int(pair[1])
            report['memory_samples'].append({'phase': sample_phase, 'stable_phase': phase == sample_phase, 'sample_start': sample_start, 'monotonic': time.monotonic(),
                'cgroup_current_bytes': int(values[0]), 'cgroup_peak_bytes': int(values[1]),
                'process_rss_bytes': fields['VmRSS'] * 1024, 'process_hwm_bytes': fields['VmHWM'] * 1024,
                'cgroup_oom_events': fields['oom'], 'cgroup_oom_kill_events': fields['oom_kill']})
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, IndexError, KeyError):
            report['memory_sample_failures'] = report.get('memory_sample_failures', 0) + 1
            report.setdefault('memory_sample_failure_phases', []).append(sample_phase)
            # Restart temporarily has no running container.
        for container, observation in report['observed_containers'].items():
            sample_phase, sample_start = phase, time.monotonic()
            try:
                values = subprocess.check_output(['docker', 'exec', container, 'cat',
                    '/sys/fs/cgroup/memory.current', '/sys/fs/cgroup/memory.peak',
                    '/sys/fs/cgroup/memory.events'], text=True, stderr=subprocess.DEVNULL, timeout=3).splitlines()
                events = dict(line.split() for line in values[2:])
                # Process names and RSS only: never collect arguments/environment.
                processes = subprocess.check_output(['docker', 'top', container, '-eo', 'comm,rss'],
                    text=True, stderr=subprocess.DEVNULL, timeout=3).splitlines()[1:]
                observation['samples'].append({'phase': sample_phase, 'stable_phase': phase == sample_phase, 'sample_start': sample_start, 'monotonic': time.monotonic(),
                    'cgroup_current_bytes': int(values[0]), 'cgroup_peak_bytes': int(values[1]),
                    'cgroup_oom_events': int(events['oom']), 'cgroup_oom_kill_events': int(events['oom_kill']),
                    'process_rss': [{'name': row.rsplit(None, 1)[0],
                                     'bytes': int(row.rsplit(None, 1)[1])*1024} for row in processes]})
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, IndexError, KeyError):
                observation['sample_failures'] = observation.get('sample_failures', 0) + 1
        stop.wait(.5)
def sample():
    try: sample_impl()
    except Exception as error: report['sampler_error']=type(error).__name__

def request(method, path, body=None, content_type='application/json', timeout=90):
    if isinstance(body, dict): body = json.dumps(body).encode()
    req = urllib.request.Request(a.url + path, data=body, method=method,
                                 headers={'Content-Type': content_type})
    start = time.monotonic()
    with http.open(req, timeout=timeout) as r:
        data = r.read()
        result = json.loads(data) if data else None
    report['stages'].append({'phase': phase, 'method': method, 'elapsed_seconds': time.monotonic() - start})
    return result
index = 'compose-smoke-' + uuid.uuid4().hex[:12]
created = False
thread = threading.Thread(target=sample, daemon=True)
thread.start()
try:
    wait_ready(lambda timeout: request('GET', '/health/readyz', timeout=timeout))
    stop.wait(3)
    phase = 'create'
    spec = {'format': 'morgan-r3-2048-lsb0-v1', 'rdkit_version': '2026.09.1', 'preparation_id': 'sanitize-only-v1'}
    fingerprint = 'morgan_' + hashlib.sha256(('morgan-r3-2048-lsb0-chiral0-features0-v1\0' + spec['rdkit_version'] + '\0' + spec['preparation_id']).encode()).hexdigest()
    request('POST', '/api/v1/indexes', {'version': '0.9', 'index_id': index,
        'doc_mapping': {'chemistry': {'spec': spec, 'smiles_field': 'smiles', 'prepared_smiles_field': 'prepared_smiles'}, 'field_mappings': [
            {'name': 'record_id', 'type': 'u64', 'fast': True},
            {'name': 'supplier', 'type': 'text', 'tokenizer': 'raw'},
            {'name': 'smiles', 'type': 'text', 'tokenizer': 'raw'},
            {'name': 'prepared_smiles', 'type': 'text', 'indexed': False, 'fast': True},
            {'name': fingerprint, 'type': 'bytes', 'fast': True, 'indexed': False, 'input_format': 'hex', 'output_format': 'hex'}]},
        'indexing_settings': {'commit_timeout_secs': 1, 'resources': {'heap_size': '32MiB'}}})
    created = True
    phase = 'import'
    data = b''.join((json.dumps({'record_id': n, 'supplier': 'Beta' if n % 4 == 3 else 'Acme',
                                'smiles': ['C[C@H](O)Cl', 'C[C@@H](O)Cl', 'CCO', 'C[C@H](O)Cl'][n % 4]}) + '\n').encode() for n in range(1000))
    result = request('POST', '/api/v1/' + index + '/ingest?commit=wait_for&detailed_response=true',
                     data, 'application/x-ndjson')
    assert result.get('num_ingested_docs') == 1000 and result.get('num_rejected_docs') == 0, result
    def search(chirality=True, supplier=True, timeout=90):
        graph = {'molecular_graph': {'spec': spec, 'prepared_field': 'prepared_smiles',
            'prepared_smiles': 'C[C@H](O)Cl', 'predicate': 'identity', 'ranking': 'best_match',
            'use_chirality': chirality, 'include_identity': True}}
        query = {'bool': {'filter': [{'term': {'supplier': 'Acme'}}, graph]}} if supplier else graph
        result = request('POST', '/api/v1/_elastic/' + index + '/_search?allow_partial_search_results=false',
                         {'query': query, 'size': 10, 'track_total_hits': True,
                          'sort': [{'record_id': 'asc'}]}, timeout=timeout)
        if not supplier:
            expected = [n for n in range(1000) if n % 4 in (0, 3)]
        elif not chirality:
            expected = [n for n in range(1000) if n % 4 in (0, 1)]
        else:
            expected = list(range(0, 1000, 4))
        assert result['hits']['total'] == {'value': len(expected), 'relation': 'eq'}, result
        assert [h['_source']['record_id'] for h in result['hits']['hits']] == expected[:10]
        assert result['_shards']['failed'] == 0 and not result['timed_out']
    phase = 'query'
    for _ in range(20): search()
    phase = 'query_controls'
    search(chirality=False)
    search(supplier=False)
    for name, expected in expected_incarnations.items():
        assert_incarnation(expected, inspect_incarnation(name))
    phase = 'restart'
    subprocess.run(['docker', 'restart', '--time', '60', a.container], check=True, capture_output=True, timeout=75)
    restarted = inspect_incarnation(a.container)
    assert_incarnation(expected_incarnations[a.container], restarted, explicit_restart=True)
    expected_incarnations[a.container] = restarted
    report['explicit_restart_incarnation'] = restarted
    wait_ready(lambda timeout: request('GET', '/health/readyz', timeout=timeout))
    deadline = time.monotonic() + 90
    phase = 'searcher_membership'
    # Node readiness precedes searcher membership propagation. Retry only this
    # known read-only startup error, never an ingest or mismatched result.
    while True:
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('searcher membership after restart')
            search(timeout=min(3, remaining))
            if time.monotonic() >= deadline:
                raise TimeoutError('searcher membership after restart')
            break
        except urllib.error.HTTPError as e:
            body = e.read()
            if e.code != 500 or b'no available searcher nodes' not in body:
                raise
            report.setdefault('startup_read_errors', []).append({'status': 500, 'reason': 'searcher_membership_pending'})
        if time.monotonic() > deadline: raise TimeoutError('searcher membership after restart')
        stop.wait(.25)
    phase = 'query_after_restart'
    for _ in range(20): search()
    search(chirality=False)
    search(supplier=False)
    phase = 'final_health'
    primary_state = {}
    def primary_health(timeout):
        global primary_state
        primary_state = json.loads(subprocess.check_output(['docker', 'inspect', a.container, '--format', '{{json .State}}'], text=True, timeout=timeout))
        if primary_state.get('Running') is not True or primary_state.get('OOMKilled') is not False:
            raise RuntimeError('primary stopped or OOM killed')
        return primary_state.get('Health', {}).get('Status') == 'healthy'
    wait_ready(primary_health, timeout=15)
    assert_container_state(primary_state)
    stop.set()
    thread.join(timeout=25)
    assert not thread.is_alive(), 'resource sampler did not stop within its deadline'
    assert 'sampler_error' not in report, 'resource sampler failed'
    report['primary_final_state'] = {k: primary_state.get(k) for k in ('Running', 'OOMKilled', 'ExitCode')}
    assert report['memory_samples'], 'cgroup v2 and process RSS measurement required'
    assert not any(s['cgroup_oom_kill_events'] for s in report['memory_samples']), 'OOM kill observed'
    assert all(p=='restart' for p in report.get('memory_sample_failure_phases', [])), 'primary measurement failed outside restart'
    required={'idle','import','query','query_after_restart'}
    report['missing_measurement_phases']=sorted(required-{s['phase'] for s in report['memory_samples'] if s['stable_phase']})
    assert not report['missing_measurement_phases'], 'primary phase sampling incomplete'
    assert time.monotonic()-report['memory_samples'][-1]['monotonic']<15, 'primary samples stale'
    for container, observation in report['observed_containers'].items():
        state=json.loads(subprocess.check_output(['docker','inspect',container,'--format','{{json .State}}'],text=True,timeout=5))
        observation['final_state']={k:state.get(k) for k in ['Running','OOMKilled','ExitCode']}
        observation['final_state']['health']=state.get('Health',{}).get('Status')
        assert state.get('Running') is True and state.get('OOMKilled') is False, 'observed container stopped or OOM killed'
        assert observation['final_state']['health']=='healthy', 'observed container health not established'
        counters=dict(line.split() for line in subprocess.check_output(['docker','exec',container,'cat','/sys/fs/cgroup/memory.events'],text=True,timeout=3).splitlines())
        observation['final_oom_kill_lifetime_count']=int(counters['oom_kill'])
        assert int(counters['oom_kill'])==0, 'observed container lifetime OOM kill present'
        assert observation['samples'], 'additional container measurement required'
        assert not observation.get('sample_failures'), 'additional container observation incomplete'
        covered={s['phase'] for s in observation['samples'] if s['stable_phase']}
        required={'idle','import','query','query_after_restart'}
        observation['missing_phases']=sorted(required-covered)
        assert not observation['missing_phases'], 'additional container phase sampling incomplete; do not infer missing peaks'
        assert time.monotonic()-observation['samples'][-1]['monotonic']<15, 'additional container samples stale'
        assert not any(s['cgroup_oom_kill_events'] for s in observation['samples']), 'additional container OOM kill observed'
    report['status'] = 'passed'
    report['accepted'] = 1000
    report['filtered_count_before_and_after_restart'] = 250
    report['chirality_disabled_count'] = 500
    report['unfiltered_identity_count'] = 500
except BaseException as e:
    report['error'] = type(e).__name__ + ': ' + str(e)
    report['status'] = 'failed'
    raise
finally:
    phase = 'cleanup'
    if created:
        try: request('DELETE', '/api/v1/indexes/' + index)
        except Exception as e:
            report['cleanup_error'] = type(e).__name__
            report['status'] = 'failed'
    stop.set()
    thread.join(timeout=25)
    if thread.is_alive():
        report['status']='failed'
        report['error']='resource sampler did not stop within its deadline'
    try:
        report['final_incarnations'] = {name: inspect_incarnation(name) for name in expected_incarnations}
        for name, expected in expected_incarnations.items():
            assert_incarnation(expected, report['final_incarnations'][name])
    except Exception as error:
        report['status'] = 'failed'
        report['incarnation_error'] = str(error)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:report[k] for k in ('status','scope')}))

if report['status'] != 'passed':
    raise SystemExit(1)
