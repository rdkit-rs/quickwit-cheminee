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

"""Independent RDKit preparation/graph/fingerprint audit of every exported row."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import struct
import time
import urllib.request
from rdkit import Chem, DataStructs, rdBase
from rdkit.Chem import rdFingerprintGenerator
from rdkit.Chem.MolStandardize import rdMolStandardize
from rdkit.Chem.Scaffolds import MurckoScaffold

SPEC = {'format': 'morgan-r3-2048-lsb0-v1', 'rdkit_version': '2026.09.1',
        'preparation_id': 'cheminee-fragment-tautomer-neutralize-v1'}
FIELD = 'morgan_' + hashlib.sha256(('morgan-r3-2048-lsb0-chiral0-features0-v1\0' +
    SPEC['rdkit_version'] + '\0' + SPEC['preparation_id']).encode()).hexdigest()
GENERATOR = rdFingerprintGenerator.GetMorganGenerator(radius=3, fpSize=2048, includeChirality=False)
NEUTRAL = Chem.MolFromSmarts('[+1!h0!$([*]~[-1,-2,-3,-4]),-1!$([*]~[+1,+2,+3,+4])]')
TAUTOMERS = rdMolStandardize.TautomerEnumerator()


def prepare(smiles):
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError('oracle rejects input')
    parent = rdMolStandardize.FragmentParent(molecule, skipStandardize=True)
    normalized = TAUTOMERS.Canonicalize(parent)
    matches = normalized.GetSubstructMatches(NEUTRAL)
    if len(matches) >= 1000:
        raise ValueError('unsupported neutralization cardinality')
    for (index,) in matches:
        atom = normalized.GetAtomWithIdx(index)
        charge = atom.GetFormalCharge()
        if atom.GetIsAromatic() or (atom.GetHybridization() == Chem.HybridizationType.SP3 and charge < 0):
            continue
        hydrogens = atom.GetTotalNumHs()
        atom.SetFormalCharge(0)
        atom.SetNumExplicitHs(hydrogens - charge)
        atom.UpdatePropertyCache(strict=True)
        Chem.SetHybridization(normalized)
    return Chem.MolFromSmiles(Chem.MolToSmiles(normalized))


def f32(value):
    return struct.unpack('f', struct.pack('f', value))[0]


def request(base, generation, mode, body):
    start = time.monotonic()
    req = urllib.request.Request(base + f'/v1/indexes/{generation}/search/{mode}',
        data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as response:
        result = json.load(response)
    return result, time.monotonic() - start


def check_response(result, expected):
    if result.get('num_hits') != len(expected) or len(result.get('hits', [])) != len(expected):
        raise ValueError('facade count/truncation mismatch')
    actual = [(int(hit['record_id']), hit['score']) for hit in result['hits']]
    if [a[0] for a in actual] != [e[0] for e in expected]:
        raise ValueError('facade complete result identity/order mismatch')
    if any(abs(a[1] - e[1]) > 1e-6 for a, e in zip(actual, expected)):
        raise ValueError('facade score mismatch')


def audit(path, base, generation, evidence):
    started = time.monotonic()
    records, molecules, fingerprints, unique_raw, unique_prepared, scaffolds = [], [], [], set(), set(), set()
    evidence = Path(evidence)
    with (evidence / (path.stem + '-row-hashes.ndjson')).open('w') as hashes:
        for line in path.open():
            row = json.loads(line)
            molecule = prepare(row['smiles'])
            canonical = Chem.MolToSmiles(molecule, isomericSmiles=True)
            actual = Chem.MolFromSmiles(row['prepared_smiles'])
            if actual is None or Chem.MolToSmiles(actual, isomericSmiles=True) != canonical:
                raise ValueError(f'independent preparation mismatch at record {row["record_id"]}; do not normalize away version differences')
            fingerprint = GENERATOR.GetFingerprint(molecule)
            if DataStructs.BitVectToBinaryText(fingerprint).hex() != row[FIELD]:
                raise ValueError('Morgan fingerprint mismatch')
            pattern = DataStructs.BitVectToBinaryText(Chem.PatternFingerprint(molecule, fpSize=2048))
            if pattern != base64.b64decode(row['pattern_fingerprint'], validate=True):
                raise ValueError('Pattern fingerprint mismatch')
            unique_raw.add(row['smiles']); unique_prepared.add(canonical)
            scaffolds.add(MurckoScaffold.MurckoScaffoldSmiles(mol=molecule))
            records.append((row['record_id'], row['supplier'], row['smiles'], canonical))
            molecules.append(molecule); fingerprints.append(fingerprint)
            hashes.write(json.dumps({'record_id': row['record_id'], 'sha256': hashlib.sha256(line.encode()).hexdigest()}) + '\n')
    if len(records) < 100_000:
        raise ValueError('corpus below required size')
    queries, timings = [], []
    for query_id in (0, 49999, 99998):
        query = molecules[query_id]
        for supplier in (None, records[query_id][1], 'absent-synthetic-supplier'):
            domain = [i for i, r in enumerate(records) if supplier is None or r[1] == supplier]
            extra = '*' if supplier is None else 'supplier:' + json.dumps(supplier)
            for mode in ('identity', 'substructure', 'similarity'):
                body = {'spec': SPEC, 'smiles': records[query_id][2], 'extra_query': extra, 'result_limit': 10000}
                if mode == 'similarity':
                    body['tanimoto_minimum'] = 0.85
                    expected = [(records[i][0], f32(DataStructs.TanimotoSimilarity(fingerprints[query_id], fingerprints[i]))) for i in domain]
                    expected = sorted((v for v in expected if v[1] >= f32(.85)), key=lambda v: (-v[1], v[0]))
                else:
                    body.update(use_chirality=True, include_identity=True, ranking='stable_id', prepared_smiles_field='prepared_smiles')
                    selected = [i for i in domain if (records[i][3] == records[query_id][3] if mode == 'identity'
                                else molecules[i].HasSubstructMatch(query, useChirality=True))]
                    expected = sorted((records[i][0], 1.0) for i in selected)
                if len(expected) > 10000:
                    raise ValueError('query exceeds exhaustive result limit; never accept truncation')
                result, seconds = request(base, generation, mode, body)
                check_response(result, expected)
                timings.append(seconds)
                queries.append({'mode': mode, 'query_record_id': records[query_id][0], 'supplier': supplier,
                                'expected': expected, 'actual': result, 'seconds': seconds})
    # Bounded load: 2 simultaneous independent exact chemistry reads, 12 requests.
    body = {'spec': SPEC, 'smiles': records[0][2], 'result_limit': 10000,
            'use_chirality': True, 'include_identity': True, 'ranking': 'stable_id', 'prepared_smiles_field': 'prepared_smiles'}
    expected = sorted((r[0], 1.0) for r in records if r[3] == records[0][3])
    with ThreadPoolExecutor(max_workers=2) as pool:
        for result, seconds in pool.map(lambda _: request(base, generation, 'identity', body), range(12)):
            check_response(result, expected); timings.append(seconds)
    report = {'status': 'passed', 'records': len(records), 'unique_raw_smiles': len(unique_raw),
              'unique_prepared_molecules': len(unique_prepared), 'murcko_scaffolds': len(scaffolds),
              'oracle_rdkit': rdBase.rdkitVersion, 'native_spec': SPEC, 'seconds': time.monotonic() - started,
              'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'query_seconds': timings,
              'bounded_load': {'concurrency': 2, 'requests': 12}, 'queries': queries,
              'limits': 'Cross-version independent oracle; mismatch fails. No HA/crash guarantee or throughput sizing claim.'}
    (evidence / (path.stem + '-chemistry.json')).write_text(json.dumps(report, indent=2))
    return report
