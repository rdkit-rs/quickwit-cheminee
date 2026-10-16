#!/usr/bin/env python3
"""Read-only HTTP regression probe; writes only the requested evidence JSON."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:19480')
    parser.add_argument('--fixture-dir', type=Path,
                        default=Path('/workspace/recovery/composable-native-run1'))
    parser.add_argument('--binary', type=Path,
                        default=Path('/workspace/recovery/quickwit-native-current'))
    parser.add_argument('--output', type=Path,
                        default=Path('/workspace/recovery/continuation-eager-validation-rerun.json'))
    parser.add_argument('--deadline-seconds', type=float, default=50)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists; choose a fresh evidence filename')
    deadline = time.monotonic() + args.deadline_seconds

    def request(path, body=None):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('bounded review deadline exceeded')
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(args.base_url.rstrip('/') + path, data=data,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=min(8, remaining)) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    fixture_path = args.fixture_dir / 'results.json'
    fixtures = json.loads(fixture_path.read_text())
    if fixtures.get('status') != 'passed':
        parser.error('original fixture harness did not pass')
    checks = fixtures['checks']
    t = next(c['distributed_topk']['tanimoto'] for c in checks
             if 'tanimoto' in c.get('distributed_topk', {}))
    g = next(c['distributed_topk']['molecular_graph'] for c in checks
             if 'molecular_graph' in c.get('distributed_topk', {}))
    c = next(c['leaf_verification_failure']['fingerprint_contains'] for c in checks
             if 'fingerprint_contains' in c.get('leaf_verification_failure', {}))
    ann = dict(t, ann=True)
    variants = {
        'threshold_2': ({'tanimoto': dict(t, minimum=2)}, 'tanimoto_minimum'),
        'short_fingerprint': ({'tanimoto': dict(t, fingerprint_hex='01')},
                              'fingerprint must encode exactly 2048 bits'),
        'empty_fingerprint': ({'fingerprint_contains': dict(c, fingerprint_hex='00' * 256)},
                              'fingerprint must contain at least one set bit'),
        'invalid_smiles': ({'molecular_graph': dict(g, prepared_smiles='not-smiles')},
                           'invalid SMILES'),
        'empty_spec_id': ({'tanimoto': dict(t, spec=dict(t['spec'], preparation_id=''))},
                          'fingerprint version identifiers'),
        'bad_candidate_field': ({'tanimoto': dict(t, candidates={
            'type': 'term', 'field': 'missing_review_field', 'value': 'x'})},
            'field does not exist'),
        'candidate_syntax': ({'tanimoto': dict(t, candidates={
            'type': 'user_input', 'user_text': '(', 'default_operator': 'AND', 'lenient': False})},
            'failed to parse query'),
        'unknown_option': ({'tanimoto': ann}, 'unknown field'),
        'unknown_option_quoted': ({'query_string': {
            'query': "_tanimoto:'" + json.dumps(ann, separators=(',', ':')) + "'"}},
            'unknown field'),
        'invalid_syntax': ({'query_string': {'query': '('}}, 'failed to parse query'),
    }
    none, all_docs = {'match_none': {}}, {'match_all': {}}

    def contexts(query):
        return {
            'bare': query,
            'and_left': {'bool': {'must': [query, none]}},
            'and_right': {'bool': {'must': [none, query]}},
            'or_left': {'bool': {'should': [query, all_docs], 'minimum_should_match': 1}},
            'or_right': {'bool': {'should': [all_docs, query], 'minimum_should_match': 1}},
            'not': {'bool': {'must_not': [query]}},
            'impossible_left': {'bool': {'should': [query, all_docs], 'minimum_should_match': 3}},
            'impossible_right': {'bool': {'should': [all_docs, query], 'minimum_should_match': 3}},
        }

    report = {
        'scope': 'independent read-only continuation regression; no campaign approval',
        'review_time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'base_url': args.base_url,
        'probe_sha256': file_hash(Path(__file__)),
        'server_binary': str(args.binary),
        'server_binary_sha256': file_hash(args.binary),
        'fixture_results_sha256': file_hash(fixture_path),
        'observation_only': 'Stored-corruption OR(match_all, chemistry), size0, has no pass/fail oracle here.',
        'checks': [],
        'failures': [],
    }
    failed_cause = 'indexed fingerprint must contain exactly 256 bytes'

    def check(kind, name, case, index, query, expected_status, size=0, diagnostic=None):
        body = {'query': query, 'size': size, 'track_total_hits': True}
        if size:
            body['sort'] = [{'_score': 'desc'}, {'record_id': 'asc'}]
        status, response = request('/api/v1/_elastic/' + index +
                                   '/_search?allow_partial_search_results=false', body)
        row = {'kind': kind, 'input': name, 'context': case, 'index': index,
               'request': body, 'expected_status': expected_status,
               'status': status, 'response': response, 'failures': []}
        if expected_status is not None:
            if status != expected_status:
                row['failures'].append('unexpected HTTP status')
            if diagnostic and diagnostic not in json.dumps(response):
                row['failures'].append('expected error cause missing')
            if expected_status == 200:
                if response.get('hits', {}).get('total') != {'value': 0, 'relation': 'eq'}:
                    row['failures'].append('expected exact zero total')
                if response.get('hits', {}).get('hits') != []:
                    row['failures'].append('expected no hits')
                if response.get('_shards', {}).get('failed') != 0 or response.get('timed_out') is not False:
                    row['failures'].append('successful zero response is incomplete')
        for failure in row['failures']:
            report['failures'].append({'input': name, 'context': case, 'size': size, 'failure': failure})
        report['checks'].append(row)

    try:
        status, cluster = request('/api/v1/cluster')
        if status != 200 or {node['node_id'] for node in cluster.get('ready_nodes', [])} != {'root', 'leaf-a', 'leaf-b'}:
            raise RuntimeError('expected root and two native leaves ready')
        report['cluster'] = cluster
        for name, (query, diagnostic) in variants.items():
            for case, wrapped in contexts(query).items():
                check('query_input', name, case, 'composable', wrapped, 400, diagnostic=diagnostic)
        # Exercise every Boolean collection when an impossible MSM would erase it.
        for clause in ['must', 'must_not', 'filter']:
            query, diagnostic = variants['short_fingerprint']
            wrapped = {'bool': {clause: [query], 'should': [all_docs], 'minimum_should_match': 2}}
            check('query_input', 'short_fingerprint', 'impossible_' + clause,
                  'composable', wrapped, 400, diagnostic=diagnostic)
        for name, query in {
            'stored_tanimoto': {'tanimoto': dict(t, minimum=0.5)},
            'stored_contains': {'fingerprint_contains': c},
        }.items():
            for case, wrapped in contexts(query).items():
                expected = None if case.startswith('or_') else (500 if case in ['bare', 'not'] else 200)
                check('stored_corruption', name, case, 'composable-leaf-failure', wrapped,
                      expected, diagnostic=failed_cause if expected == 500 else None)
            for case, clauses in [('or_none_left', [query, none]), ('or_none_right', [none, query])]:
                check('stored_corruption', name, case, 'composable-leaf-failure',
                      {'bool': {'should': clauses, 'minimum_should_match': 1}},
                      500, diagnostic=failed_cause)
            check('stored_corruption_rank', name, 'or_match_all', 'composable-leaf-failure',
                  contexts(query)['or_left'], 500, size=3, diagnostic=failed_cause)
        for name in ['short_fingerprint', 'invalid_smiles']:
            query, diagnostic = variants[name]
            for case in ['and_right', 'impossible_right']:
                check('query_input_topk', name, case, 'composable', contexts(query)[case],
                      400, size=3, diagnostic=diagnostic)
    except Exception as error:
        report['execution_error'] = type(error).__name__ + ': ' + str(error)
    report['status'] = 'passed' if not report['failures'] and 'execution_error' not in report else 'failed'
    report['request_count'] = len(report['checks'])
    report['observation_count'] = sum(row['expected_status'] is None for row in report['checks'])
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'request_count': report['request_count'],
                      'observation_count': report['observation_count'],
                      'failed_assertions': len(report['failures']), 'output': str(args.output),
                      'execution_error': report.get('execution_error')}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
