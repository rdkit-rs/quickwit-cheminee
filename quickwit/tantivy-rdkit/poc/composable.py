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

"""Real HTTP -> root -> two native leaves, with tiny hand-checkable fixtures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--work-dir', type=Path, required=True)
parser.add_argument('--port-base', type=int, default=19480)
args = parser.parse_args()
work = args.work_dir.resolve()
work.mkdir(parents=True, exist_ok=False)
base = f'http://127.0.0.1:{args.port_base}'
processes, logs, checks = [], [], []


def request(path, body=None, expected=200, raw=False):
    data = body if raw else None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, headers={
        'Content-Type': 'application/x-ndjson' if raw else 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            status, content = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, content = error.code, error.read()
    assert status == expected, (path, status, content[:3000])
    return json.loads(content)


def wait_for(predicate):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (OSError, AssertionError):
            pass
        time.sleep(0.2)
    raise RuntimeError('startup timeout; inspect node logs')


def start(name, offset, services):
    data = work / name
    data.mkdir()
    config = {'version': '0.8', 'cluster_id': 'composable-' + work.name,
              'node_id': name, 'listen_address': '127.0.0.1',
              'rest': {'listen_port': args.port_base + offset}, 'data_dir': str(data),
              'peer_seeds': [f'127.0.0.1:{args.port_base}'],
              'metastore_uri': (work / 'root/indexes').as_uri(),
              'default_index_root_uri': (work / 'root/indexes').as_uri()}
    path = work / (name + '.json')
    path.write_text(json.dumps(config))
    command = [str(args.binary.resolve()), 'run', '--config', str(path)]
    for service in services:
        command.extend(['--service', service])
    log = (work / (name + '.log')).open('w')
    logs.append(log)
    processes.append(subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
        env=dict(os.environ, QW_DISABLE_TELEMETRY='1', RUST_LOG='info')))


def search_body(query, size=20, offset=0):
    return {'query': query, 'size': size, 'from': offset, 'track_total_hits': True,
            'sort': [{'_score': 'desc'}, {'record_id': 'asc'}]}


def hits_and_total(result):
    # This fork's ES converter omits _score; requested sort values carry the score.
    for hit in result['hits']['hits']:
        assert len(hit['sort']) == 2 and hit['sort'][1] == hit['_source']['record_id'], hit
    return ([(hit['_source']['record_id'], hit['sort'][0]) for hit in result['hits']['hits']],
            result['hits']['total']['value'])


def search(query, size=20, index='composable', offset=0):
    result = request(f'/api/v1/_elastic/{index}/_search?allow_partial_search_results=false',
                     search_body(query, size, offset))
    assert result['_shards']['failed'] == 0, result
    return hits_and_total(result)


def leaf_counters():
    counters = {}
    for name, offset in [('leaf-a', 10), ('leaf-b', 20)]:
        with urllib.request.urlopen(f'http://127.0.0.1:{args.port_base + offset}/metrics') as response:
            metrics = response.read().decode()
        (work / (name + '-metrics.txt')).write_text(metrics)
        counters[name] = sum(float(line.split()[-1]) for line in metrics.splitlines()
            if line.startswith('quickwit_search_leaf_search_requests_total{')
            and 'kind="server"' in line and 'status="success"' in line)
    return counters


def clause(name, operand):
    encoded = json.dumps(operand, separators=(',', ':')).replace('\\', '\\\\').replace("'", "\\'")
    return f"_{name}:'{encoded}'"


def parity(name, operand, expected_ids=None):
    structured = search({name: operand})
    text = search({'query_string': {'query': clause(name, operand)}})
    assert structured == text, (structured, text)
    if expected_ids is not None:
        assert [record_id for record_id, _ in structured[0]] == expected_ids, structured
    checks.append({'operator': name, 'operand': operand, 'result': structured})
    return structured


try:
    start('root', 0, ['metastore', 'control-plane', 'indexer', 'janitor'])
    wait_for(lambda: request('/api/v1/cluster'))
    start('leaf-a', 10, ['searcher'])
    start('leaf-b', 20, ['searcher'])
    wait_for(lambda: len(request('/api/v1/cluster').get('ready_nodes', [])) == 3)
    spec = {'format': 'morgan-r3-2048-lsb0-v1', 'rdkit_version': '2026.09.1',
            'preparation_id': 'sanitize-only-v1'}
    fingerprint_field = 'morgan_' + hashlib.sha256(
        ('morgan-r3-2048-lsb0-chiral0-features0-v1\0' + spec['rdkit_version'] + '\0' +
         spec['preparation_id']).encode()).hexdigest()
    mapping = {'version': '0.8', 'index_id': 'composable', 'doc_mapping': {'mode': 'strict', 'tag_fields': ['family'],
        'chemistry': {'spec': spec, 'smiles_field': 'smiles', 'prepared_smiles_field': 'prepared_smiles'},
        'field_mappings': [{'name': 'record_id', 'type': 'u64', 'fast': True},
            {'name': 'smiles', 'type': 'text', 'tokenizer': 'raw'},
            {'name': 'family', 'type': 'text', 'tokenizer': 'raw'},
            {'name': 'prepared_smiles', 'type': 'text', 'indexed': False, 'fast': True},
            {'name': 'descriptors', 'type': 'json', 'fast': True},
            {'name': fingerprint_field, 'type': 'bytes', 'fast': True, 'indexed': False,
             'input_format': 'hex', 'output_format': 'hex'}]},
        'indexing_settings': {'commit_timeout_secs': 1, 'merge_policy': {'type': 'no_merge'}}}
    request('/api/v1/indexes', mapping)
    (work / 'mapping.json').write_text(json.dumps(mapping, indent=2))
    # Descriptor numbers are synthetic metadata; this harness does not test preparation parity.
    docs = [{'record_id': record_id, 'smiles': smiles, 'descriptors': {'amw': weight}}
            for record_id, smiles, weight in [(10, 'C', 10), (4, 'CC', 20), (2, 'CCC', 30), (1, 'CC', 40)]]
    docs.append({'record_id': 9, 'smiles': 'O'})
    for doc in docs:
        doc['family'] = 'a' if doc['record_id'] == 10 else 'b'
    for doc in docs:  # separate commits and no merge exercise multiple splits
        ingested = request('/api/v1/composable/ingest?commit=force', json.dumps(doc).encode(), raw=True)
        assert ingested['num_rejected_docs'] == 0, ingested
    graph = {'spec': spec, 'prepared_field': 'prepared_smiles', 'prepared_smiles': 'CC',
             'predicate': 'substructure', 'ranking': 'best_match', 'use_chirality': False,
             'include_identity': True}
    parity('molecular_graph', graph, [1, 4, 2])
    bounded = dict(graph, candidates={'type': 'range', 'field': 'descriptors.amw',
                                     'lower_bound': {'Included': 0}, 'upper_bound': {'Included': 30}})
    parity('molecular_graph', bounded, [4, 2])
    parity('molecular_graph', dict(graph, candidates={'type': 'user_input',
        'user_text': 'descriptors.amw:[0 TO 30]', 'default_operator': 'AND', 'lenient': False}), [4, 2])
    for predicate, expected_ids in [('superstructure', [1, 4, 10]), ('identity', [1, 4])]:
        parity('molecular_graph', dict(graph, predicate=predicate), expected_ids)
    negative_candidates = dict(graph, candidates={'type': 'bool', 'must_not': [
        {'type': 'term', 'field': 'family', 'value': 'a'}]})
    negative = search({'bool': {'must_not': [{'molecular_graph': negative_candidates}]}})
    assert negative == search({'query_string': {'query': 'NOT ' + clause('molecular_graph', negative_candidates)}})
    assert [record_id for record_id, _ in negative[0]] == [9, 10], negative
    checks.append({'boolean': 'NOT graph(NOT family:a)', 'result': negative})
    range_query = {'range': {'descriptors.amw': {'gte': 0, 'lte': 30}}}
    for operator in ['AND', 'OR']:
        structured = {'bool': {'must' if operator == 'AND' else 'should':
                              [{'molecular_graph': graph}, range_query]}}
        text = clause('molecular_graph', graph) + f' {operator} descriptors.amw:[0 TO 30]'
        assert search(structured) == search({'query_string': {'query': text}})
        checks.append({'boolean': operator, 'result': search(structured)})
    negated = {'bool': {'must': [{'molecular_graph': graph}, {'bool': {'must_not': [range_query]}}]}}
    assert search(negated) == search({'query_string': {'query': clause('molecular_graph', graph) +
                                                           ' AND NOT descriptors.amw:[0 TO 30]'}})
    assert search({'bool': {'filter': [{'molecular_graph': graph}]}})[0] == [(1, 0.0), (2, 0.0), (4, 0.0)]
    assert search({'molecular_graph': graph}, size=1) == ([(1, 1.0)], 3)
    all_docs = request('/api/v1/_elastic/composable/_search', {'query': {'match_all': {}}, 'size': 20})
    fingerprints = {hit['_source']['record_id']: bytes.fromhex(hit['_source'][fingerprint_field])
                    for hit in all_docs['hits']['hits']}
    query_fp = fingerprints[1]
    similarity = {'spec': spec, 'fingerprint_hex': query_fp.hex(), 'minimum': 0.5}
    actual, count = parity('tanimoto', similarity)
    oracle = []
    for record_id, fp in fingerprints.items():
        intersection = sum((left & right).bit_count() for left, right in zip(query_fp, fp))
        union = sum((left | right).bit_count() for left, right in zip(query_fp, fp))
        if intersection / union >= 0.5:
            oracle.append((record_id, intersection / union))
    oracle.sort(key=lambda hit: (-hit[1], hit[0]))
    assert count == len(oracle) and len(actual) == len(oracle)
    for (actual_id, score), (expected_id, expected_score) in zip(actual, oracle):
        assert actual_id == expected_id and abs(score - expected_score) < 1e-6
    combined = {'bool': {'must': [{'molecular_graph': graph}, {'tanimoto': similarity}]}}
    combined_text = clause('molecular_graph', graph) + ' AND ' + clause('tanimoto', similarity)
    assert search(combined) == search({'query_string': {'query': combined_text}})
    checks.append({'boolean': 'graph AND similarity', 'result': search(combined)})
    for direction in ['document_contains_query', 'query_contains_document']:
        operand = {'spec': spec, 'fingerprint_hex': query_fp.hex(), 'direction': direction}
        expected = sorted(record_id for record_id, fp in fingerprints.items() if all(
            (query & doc) == (query if direction == 'document_contains_query' else doc)
            for query, doc in zip(query_fp, fp)))
        parity('fingerprint_contains', operand, expected)
    for query in [{'tanimoto': dict(similarity, minimum=2)}, {'tanimoto': dict(similarity, ann=True)},
                  {'molecular_graph': dict(graph, prepared_smiles='not-smiles')}]:
        request('/api/v1/_elastic/composable/_search', {'query': query}, expected=400)

    # Four matches in each split, with the top-score ties interleaved across splits.
    # Both leaves must handle these queries, not merely earlier startup searches.
    topk_mapping = json.loads(json.dumps(mapping))
    topk_mapping['index_id'] = 'composable-topk'
    request('/api/v1/indexes', topk_mapping)
    for batch_number, record_ids in enumerate([[12, 8, 4], [11, 7, 3], [10, 6, 2], [9, 5, 1]]):
        batch = [{'record_id': record_id, 'smiles': 'CC', 'family': 'tie'} for record_id in record_ids]
        batch.append({'record_id': 101 + batch_number, 'smiles': 'CCC', 'family': 'lower'})
        ingested = request('/api/v1/composable-topk/ingest?commit=force',
            '\n'.join(json.dumps(doc) for doc in batch).encode(), raw=True)
        assert ingested['num_rejected_docs'] == 0, ingested
    splits = request('/api/v1/indexes/composable-topk/splits?split_states=Published')
    (work / 'topk-splits.json').write_text(json.dumps(splits, indent=2))
    assert len(splits['splits']) == 4, splits
    assert all(split['num_docs'] == 4 for split in splits['splits']), splits
    for query in [{'molecular_graph': graph}, {'tanimoto': dict(similarity, minimum=0)}]:
        before = leaf_counters()
        complete = search(query, index='composable-topk')
        page = search(query, size=4, offset=2, index='composable-topk')
        after = leaf_counters()
        assert complete[1] == page[1] == 16, (complete, page)
        assert page[0] == complete[0][2:6] == [(record_id, 1.0) for record_id in [3, 4, 5, 6]]
        assert all(after[name] > before[name] for name in before), (before, after)
        checks.append({'distributed_topk': query, 'from': 2, 'size': 4, 'result': page,
                       'leaf_requests_before': before, 'leaf_requests_after': after})

    # Native chemistry ingestion prevents invalid derived data. A normal bytes
    # mapping allows a one-byte fingerprint through ingestion, so failure happens
    # inside the leaf verifier, beside a separately committed healthy split.
    failure_mapping = json.loads(json.dumps(mapping))
    failure_mapping['index_id'] = 'composable-leaf-failure'
    failure_mapping['doc_mapping'].pop('chemistry')
    request('/api/v1/indexes', failure_mapping)
    for batch in [[{'record_id': record_id, fingerprint_field: query_fp.hex()} for record_id in [1, 2]],
                  [{'record_id': 3, fingerprint_field: '01'}]]:
        ingested = request('/api/v1/composable-leaf-failure/ingest?commit=force',
            '\n'.join(json.dumps(doc) for doc in batch).encode(), raw=True)
        assert ingested['num_rejected_docs'] == 0, ingested
    splits = request('/api/v1/indexes/composable-leaf-failure/splits?split_states=Published')
    (work / 'failure-splits.json').write_text(json.dumps(splits, indent=2))
    assert sorted(split['num_docs'] for split in splits['splits']) == [1, 2], splits
    failure_url = '/api/v1/_elastic/composable-leaf-failure/_search'
    for query in [{'tanimoto': similarity}, {'fingerprint_contains': {
            'spec': spec, 'fingerprint_hex': query_fp.hex(), 'direction': 'document_contains_query'}}]:
        body = search_body(query)
        strict = request(failure_url + '?allow_partial_search_results=false', body, expected=500)
        assert 'indexed fingerprint must contain exactly 256 bytes' in json.dumps(strict), strict
        partial = request(failure_url + '?allow_partial_search_results=true', body)
        default = request(failure_url, body)
        assert partial['_shards']['failed'] == 1 and partial['_shards']['successful'] == 1, partial
        assert partial['_shards']['total'] == 2, partial
        assert hits_and_total(partial) == hits_and_total(default) == ([(1, 1.0), (2, 1.0)], 2)
        assert default['_shards'] == partial['_shards'], default
        checks.append({'leaf_verification_failure': query, 'strict': strict, 'partial': partial})
    assert all(count > 0 for count in leaf_counters().values())
    (work / 'results.json').write_text(json.dumps({'checks': checks,
        'cluster': request('/api/v1/cluster'), 'status': 'passed'}, indent=2))
    print(json.dumps({'status': 'passed', 'parity_cases': len(checks)}))
finally:
    for process in processes:
        process.send_signal(signal.SIGTERM)
    for process in processes:
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    for log in logs:
        log.close()
