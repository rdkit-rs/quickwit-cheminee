#!/usr/bin/env python3
"""Read-only native selective-filter and subsecond regression over retained fixtures."""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--binary', type=Path, required=True)
p.add_argument('--fixture-dir', type=Path, default=Path('/workspace/recovery/composable-native-run1'))
p.add_argument('--base-url', default='http://127.0.0.1:19480')
a = p.parse_args()
if a.output.exists():
    p.error('choose a fresh output file')
report = {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'checks': [], 'failures': []}
for name, path in [('probe', Path(__file__)), ('binary', a.binary)]:
    with path.open('rb') as f:
        report[name + '_sha256'] = hashlib.file_digest(f, 'sha256').hexdigest()

def search(index, query, size):
    body = {'query': query, 'size': size, 'track_total_hits': True,
            'sort': [{'_score': 'desc'}, {'record_id': 'asc'}]}
    req = urllib.request.Request(a.base_url + '/api/v1/_elastic/' + index +
        '/_search?allow_partial_search_results=false', data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)

def check(name, index, query, size, ids=None, status=200):
    code, response = search(index, query, size)
    row = dict(name=name, index=index, query=query, size=size, status=code, response=response,
               expected_status=status, expected_ids=ids)
    errors = []
    if code != status:
        errors.append('HTTP status')
    if status == code == 200:
        hits = response.get('hits', {})
        if hits.get('total') != {'value': len(ids), 'relation': 'eq'}:
            errors.append('exact total')
        actual = [h['_source']['record_id'] for h in hits.get('hits', [])]
        if actual != (ids[:size] if size else []):
            errors.append('ordered IDs')
        if response.get('_shards', {}).get('failed') != 0 or response.get('timed_out') is not False:
            errors.append('incomplete response')
    row['failures'] = errors
    report['checks'].append(row)
    report['failures'].extend([{'name': name, 'failure': e} for e in errors])
    return response

fixtures = json.loads((a.fixture_dir / 'results.json').read_text())
operators = {}
for row in fixtures['checks']:
    operators.update(row.get('distributed_topk', {}))
    if 'fingerprint_contains' in row.get('leaf_verification_failure', {}):
        operators['fingerprint_contains'] = row['leaf_verification_failure']['fingerprint_contains']
# On this fixture all chemistry operators match IDs1..12; IDs101..104 are CCC.
guard = {'range': {'record_id': {'lte': 4}}}
explicit = {'type': 'range', 'field': 'record_id', 'lower_bound': 'Unbounded',
            'upper_bound': {'Included': 4}}
for operator in ['tanimoto', 'molecular_graph', 'fingerprint_contains']:
    spec = operators[operator]
    for size in [0, 20]:
        for order in [0, 1]:
            q = {operator: spec}
            narrowed = copy.deepcopy(q)
            narrowed[operator]['candidates'] = explicit
            clauses = [guard, q] if order == 0 else [q, guard]
            manual = [guard, narrowed] if order == 0 else [narrowed, guard]
            for repeat in ['cold', 'warm']:
                name = f'{operator}-{size}-{order}-{repeat}'
                lhs = check(name, 'composable-topk', {'bool': {'must': clauses}}, size, [1,2,3,4])
                rhs = check(name+'-explicit', 'composable-topk', {'bool': {'must': manual}}, size, [1,2,3,4])
                # Keep the original scoring predicate on both sides of the equivalence.
                left = [(h['_source']['record_id'], h.get('_score'), h.get('sort')) for h in lhs.get('hits', {}).get('hits', [])]
                right = [(h['_source']['record_id'], h.get('_score'), h.get('sort')) for h in rhs.get('hits', {}).get('hits', [])]
                if left != right:
                    report['failures'].append({'name': name, 'failure': 'candidate narrowing changed score/order'})
        check(f'{operator}-{size}-negative', 'composable-topk',
              {'bool': {'filter': [guard], 'must_not': [{operator: spec}]}}, size, [])
# Same split: healthy ID1 and malformed fingerprint ID2.
original = json.loads((a.fixture_dir / 'timestamp-domain-probe.json').read_text())
q = original['queries']['unbounded']['query']
good = {'range': {'record_id': {'lte': 1}}}
for size in [0, 20]:
    for clauses in [[good, q], [q, good]]:
        check('irrelevant-corrupt-sibling', 'composable-timestamp-domain', {'bool': {'must': clauses}}, size, [1])
    check('irrelevant-corrupt-negative', 'composable-timestamp-domain', {'bool': {'filter': [good], 'must_not': [q]}}, size, [])
    check('relevant-corrupt-or', 'composable-timestamp-domain', {'bool': {'should': [good, q], 'minimum_should_match': 1}}, size, status=500)
    check('relevant-corrupt-broad', 'composable-timestamp-domain', q, size, status=500)
for lower, upper, ids in [('2020-01-01T00:00:00.001Z', '2020-01-01T00:00:00.999Z', [3]),
                         ('1969-12-31T23:59:59.001Z', '1969-12-31T23:59:59.999Z', [4])]:
    for mode in ['ordinary', 'explicit_candidate']:
        query = {'range': {'observed_at': {'gt': lower, 'lt': upper}}}
        if mode == 'explicit_candidate':
            query = copy.deepcopy(q)
            query['tanimoto']['candidates'] = {'type': 'range', 'field': 'observed_at',
                'lower_bound': {'Excluded': lower}, 'upper_bound': {'Excluded': upper}}
        check('subsecond-'+mode+'-'+lower, 'composable-subsecond', query, 20, ids)
report['status'] = 'passed' if not report['failures'] else 'failed'
a.output.write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({'status': report['status'], 'checks': len(report['checks']), 'failures': report['failures']}))
raise SystemExit(bool(report['failures']))
