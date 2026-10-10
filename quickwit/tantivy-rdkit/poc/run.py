import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import statistics
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from openapi_spec_validator import validate as validate_openapi
from rdkit import Chem, DataStructs, RDConfig, rdBase
from rdkit.Chem import rdFingerprintGenerator

parser = argparse.ArgumentParser()
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--leaf-binary', type=Path)
parser.add_argument('--raw-smiles', action='store_true')
parser.add_argument('--work-dir', type=Path)
parser.add_argument('--port-base', type=int, default=17480)
args = parser.parse_args()
work = args.work_dir or Path(tempfile.mkdtemp(prefix='cheminee-poc-'))
work.mkdir(parents=True, exist_ok=True)
if (work/'results.json').exists():
    raise RuntimeError('Use a fresh work directory for each run')
base = f'http://127.0.0.1:{args.port_base}'
processes = []
logs = []
results = {'raw_smiles': args.raw_smiles, 'separate_leaf_binary': bool(args.leaf_binary), 'storage':'local filesystem shared between three processes', 'rdkit':rdBase.rdkitVersion}

def request(path, body=None, expected=200, raw=False):
    data = body if raw else None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base+path, data=data, headers={'Content-Type':'application/x-ndjson' if raw else 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            status, data = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, data = error.code, error.read()
    assert status == expected, (path, status, data[:2000])
    return json.loads(data)

def wait_for(predicate, timeout=60):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            if predicate(): return
        except (OSError, AssertionError): pass
        time.sleep(0.2)
    raise RuntimeError('Timed out; inspect node logs in '+str(work))

def start_node(name, offset, services):
    data=work/name
    data.mkdir(exist_ok=True)
    config={'version':'0.8','cluster_id':'cheminee-poc','node_id':name,'listen_address':'127.0.0.1','rest':{'listen_port':args.port_base+offset},'data_dir':str(data.resolve()),'peer_seeds':[f'127.0.0.1:{args.port_base}'],'metastore_uri':(work/'root/indexes').resolve().as_uri(),'default_index_root_uri':(work/'root/indexes').resolve().as_uri()}
    config_path=work/(name+'.json')
    config_path.write_text(json.dumps(config,indent=2))
    binary = args.leaf_binary if args.leaf_binary and services == ['searcher'] else args.binary
    command=[str(binary.resolve()),'run','--config',str(config_path)]
    for service in services: command.extend(['--service',service])
    log=(work/(name+'.log')).open('w')
    logs.append(log)
    process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,QW_DISABLE_TELEMETRY='1',RUST_LOG='info'))
    processes.append(process)
    return process

def ingest(index, docs):
    return request('/api/v1/'+index+'/ingest?commit=force',b'\n'.join(json.dumps(doc).encode() for doc in docs),raw=True)

def f32(number):
    return struct.unpack('f',struct.pack('f',number))[0]

try:
    start_node('root',0,['metastore','control-plane','indexer','janitor'])
    wait_for(lambda: request('/api/v1/cluster'))
    leaves=[start_node('leaf-a',10,['searcher']),start_node('leaf-b',20,['searcher'])]
    wait_for(lambda: len(request('/api/v1/cluster').get('ready_nodes',[]))==3)
    cluster=request('/api/v1/cluster')
    results['cluster']=cluster
    spec={'format':'morgan-r3-2048-lsb0-v1','rdkit_version':rdBase.rdkitVersion,'preparation_id':'sanitize-only-v1'}
    field='morgan_'+hashlib.sha256(('morgan-r3-2048-lsb0-chiral0-features0-v1\0'+spec['rdkit_version']+'\0'+spec['preparation_id']).encode()).hexdigest()
    generator=rdFingerprintGenerator.GetMorganGenerator(radius=3,fpSize=2048,includeChirality=False)
    source=Path(RDConfig.RDDataDir)/'NCI/first_5K.smi'
    results['public_source']={'path':'RDKit Data/NCI/first_5K.smi','sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    smiles=[(line.split()[0],'public') for line in source.read_text().splitlines()[:512]]
    smiles += [('C'*length+suffix,'synthetic') for length in range(1,25) for suffix in ['', 'O', 'N', '(=O)O']]
    smiles += [(value,'edge') for value in ['CCO','CCO','CC(=O)[O-].[Na+]','C[C@H](O)C(=O)O','C[C@@H](O)C(=O)O','[13CH3]CO','c1ccccc1','C1=CC=CC=C1','CC(=O)C','CC(O)=C','C.C','[NH4+]','bad-smiles']]
    docs=[];fingerprints=[];rejected=[]
    for raw,family in smiles:
        molecule=Chem.MolFromSmiles(raw)
        if molecule is None:
            rejected.append(raw);continue
        fingerprint=generator.GetFingerprint(molecule)
        binary=DataStructs.BitVectToBinaryText(fingerprint)
        for bit in fingerprint.GetOnBits(): assert binary[bit//8] & (1 << (bit%8))
        docs.append({'record_id':len(docs),'smiles':raw if args.raw_smiles else Chem.MolToSmiles(molecule),'family':family,field:binary.hex()})
        fingerprints.append(fingerprint)
    (work/'molecules.ndjson').write_text('\n'.join(json.dumps(doc,sort_keys=True) for doc in docs)+'\n')
    results['molecules']={'accepted':len(docs),'rejected':rejected,'fixture_sha256':hashlib.sha256((work/'molecules.ndjson').read_bytes()).hexdigest()}
    mapping={'version':'0.8','index_id':'molecules','doc_mapping':{'mode':'strict','field_mappings':[{'name':'record_id','type':'u64','fast':True},{'name':'smiles','type':'text','tokenizer':'raw'},{'name':'family','type':'text','tokenizer':'raw'},{'name':field,'type':'bytes','fast':True,'indexed':False,'input_format':'hex','output_format':'hex'}]},'indexing_settings':{'commit_timeout_secs':1,'merge_policy':{'type':'no_merge'}}}
    if args.raw_smiles:
        mapping['doc_mapping']['chemistry'] = {'spec': spec, 'smiles_field': 'smiles', 'prepared_smiles_field': 'prepared_smiles'}
        mapping['doc_mapping']['field_mappings'].append({'name':'prepared_smiles','type':'text','indexed':False})
    (work/'index.json').write_text(json.dumps(mapping,indent=2))
    request('/api/v1/indexes',mapping)
    ingestion_docs = [{key:value for key,value in doc.items() if key != field} for doc in docs] if args.raw_smiles else docs
    (work/'ingested.ndjson').write_text('\n'.join(json.dumps(doc) for doc in ingestion_docs)+'\n')
    if args.raw_smiles:
        assert all(field not in doc for doc in ingestion_docs)
        invalid = ingest('molecules', [{'record_id':99999,'smiles':'bad-smiles','family':'invalid'}])
        assert invalid['num_rejected_docs'] == 1 and invalid['num_ingested_docs'] == 0, invalid
        results['invalid_smiles_ingestion'] = invalid
    for start in range(0,len(docs),100): ingest('molecules',ingestion_docs[start:start+100])
    path='/api/v1/molecules/cheminee/search/similarity'
    body={'spec':spec,'fingerprint_hex':docs[0][field],'tanimoto_minimum':0,'result_limit':20}
    timings=[];checks=0
    for query_id in [0,1,17,111,300,512,len(docs)-2]:
        body['fingerprint_hex']=docs[query_id][field]
        for threshold in [0,0.4,1]:
            body['tanimoto_minimum']=threshold
            for family in [None,'public','synthetic','absent']:
                body['extra_query']='*' if family is None else 'family:'+family
                scores=[(f32(DataStructs.TanimotoSimilarity(fingerprints[query_id],fp)),doc['record_id']) for doc,fp in zip(docs,fingerprints) if family is None or doc['family']==family]
                expected=sorted([(score,record_id) for score,record_id in scores if score>=f32(threshold)],key=lambda pair:(-pair[0],pair[1]))
                for limit in [1,20]:
                    body['result_limit']=limit
                    start=time.perf_counter();response=request(path,body);timings.append((time.perf_counter()-start)*1000)
                    if args.raw_smiles:
                        smiles_body = {key:value for key,value in body.items() if key != 'fingerprint_hex'}
                        smiles_body['smiles'] = docs[query_id]['smiles']
                        native = request(path+'/smiles', smiles_body)
                        assert native['num_hits'] == response['num_hits'] and native['hits'] == response['hits'], (native, response)
                        for hit in native['hits']:
                            assert hit['document']['prepared_smiles']
                    assert response['num_hits']==len(expected),(body,response,expected)
                    actual=[(hit['score'],int(hit['record_id'])) for hit in response['hits']]
                    assert [record_id for _,record_id in actual]==[record_id for _,record_id in expected[:limit]],(body,actual,expected[:limit])
                    assert all(abs(left[0]-right[0])<1e-7 for left,right in zip(actual,expected))
                    checks+=1
    results['parity']={'queries':checks,'first_ms':timings[0],'median_ms':statistics.median(timings),'max_ms':max(timings),'reference':'RDKit exhaustive Tanimoto rounded to f32, then score descending and record_id ascending'}
    body={'spec':spec,'fingerprint_hex':docs[512][field],'tanimoto_minimum':0,'result_limit':20}
    for field_name,value in [('fingerprint_hex','00'*256),('fingerprint_hex','01'),('result_limit',0),('result_limit',10001),('tanimoto_minimum',-0.1),('extra_query','bad_field:foo'),('unknown',True)]:
        request(path,dict(body,**{field_name:value}),expected=400)
    for field_name in ['spec','fingerprint_hex','result_limit','tanimoto_minimum','extra_query']:
        request(path,dict(body,**{field_name:None}),expected=400)
    request(path,dict(body,spec=dict(spec,preparation_id='incompatible')),expected=400)
    request('/api/v1/absent/cheminee/search/similarity',body,expected=404)
    spec_json=request('/api/v1/cheminee/openapi.json')
    assert spec_json==request('/api/v1/cheminee/openapi.json')
    validate_openapi(spec_json)
    (work/'openapi.json').write_text(json.dumps(spec_json,indent=2,sort_keys=True)+'\n')
    config=work/'client-config.json'
    config.write_text(json.dumps({'package_name_override':'cheminee_client','project_name_override':'cheminee-client'}))
    subprocess.run([str(Path(sys.executable).with_name('openapi-python-client')),'generate','--path',str(work/'openapi.json'),'--output-path',str(work/'cheminee_client'),'--meta','none','--config',str(config)],check=True,env=dict(os.environ,PATH=str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH','')))
    sys.path.insert(0,str(work))
    client_module=importlib.import_module('cheminee_client')
    operation=importlib.import_module('cheminee_client.api.cheminee.cheminee_search_similarity')
    models=importlib.import_module('cheminee_client.models')
    generated_body=models.SimilarityRequest.from_dict(body)
    with client_module.Client(base_url=base) as client:
        generated=operation.sync_detailed(index_id='molecules',client=client,body=generated_body)
        assert generated.status_code==200
        assert generated.parsed.num_hits==len(docs)
        generated_body.result_limit=0
        error=operation.sync_detailed(index_id='molecules',client=client,body=generated_body)
        assert error.status_code==400 and isinstance(error.parsed,models.ChemistryError)
    if args.raw_smiles:
        smiles_operation=importlib.import_module('cheminee_client.api.cheminee.cheminee_search_similarity_smiles')
        smiles_body=models.SmilesSimilarityRequest.from_dict({'spec':spec,'smiles':docs[0]['smiles'],'tanimoto_minimum':0})
        with client_module.Client(base_url=base) as client:
            success=smiles_operation.sync_detailed(index_id='molecules',client=client,body=smiles_body)
            assert success.status_code==200 and success.parsed.num_hits==len(docs)
            smiles_body.smiles='bad-smiles'
            error=smiles_operation.sync_detailed(index_id='molecules',client=client,body=smiles_body)
            assert error.status_code==400 and isinstance(error.parsed,models.ChemistryError)
        results['native_client']={'success_status':200,'typed_error_status':400}
    results['client']={'generator':'openapi-python-client 0.29.1','success_status':200,'typed_error_status':400,'openapi':spec_json['openapi']}
    repeated=[dict(ingestion_docs[0],record_id=100000+index) for index in range(10050)]
    ingest('molecules',repeated)
    exact_body=dict(body,fingerprint_hex=docs[0][field],tanimoto_minimum=1,result_limit=1)
    large=request(path,exact_body)
    expected=sum(fp==fingerprints[0] for fp in fingerprints)+len(repeated)
    assert large['num_hits']==expected and int(large['hits'][0]['record_id'])==0
    results['uncapped']={'matching_records':large['num_hits'],'returned':len(large['hits']),'searched_splits':large['searched_splits']}
    poison=json.loads(json.dumps(mapping))
    poison['index_id']='malformed'
    poison['doc_mapping'].pop('chemistry', None)
    request('/api/v1/indexes',poison)
    ingest('malformed',[dict(docs[0],**{field:'01'})])
    failed=request('/api/v1/malformed/cheminee/search/similarity',body,expected=503)
    assert 'incomplete' in failed['message']
    results['malformed_data_status']=503
    results['published_splits']=request('/api/v1/indexes/molecules/splits')
    for leaf in leaves: leaf.send_signal(signal.SIGINT)
    for leaf in leaves: leaf.wait(timeout=30)
    wait_for(lambda: len(request('/api/v1/cluster').get('ready_nodes',[]))==1)
    request(path,dict(body,fingerprint_hex=docs[17][field],tanimoto_minimum=0.12345),expected=500)
    results['no_leaf_status']=500
    results['root_services']=['metastore','control-plane','indexer','janitor']
    (work/'results.json').write_text(json.dumps(results,indent=2,sort_keys=True)+'\n')
    print(json.dumps({key:value for key,value in results.items() if key not in ['cluster','published_splits']},indent=2))
    print('Artifacts:',work)
finally:
    for process in processes:
        if process.poll() is None: process.send_signal(signal.SIGINT)
    for process in processes:
        try: process.wait(timeout=45)
        except subprocess.TimeoutExpired:
            process.kill();process.wait()
    for log in logs: log.close()
