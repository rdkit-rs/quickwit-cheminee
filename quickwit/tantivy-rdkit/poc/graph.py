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
from rdkit.Chem.MolStandardize import rdMolStandardize

parser = argparse.ArgumentParser()
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--leaf-binary', type=Path)
parser.add_argument('--expect-native-unavailable', action='store_true')
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
results = {'raw_smiles': True, 'separate_leaf_binary': bool(args.leaf_binary), 'storage':'local filesystem shared between three processes', 'rdkit':rdBase.rdkitVersion}

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
    config={'version':'0.8','cluster_id':'cheminee-graph-'+work.name,'node_id':name,'listen_address':'127.0.0.1','rest':{'listen_port':args.port_base+offset},'data_dir':str(data.resolve()),'peer_seeds':[f'127.0.0.1:{args.port_base}'],'metastore_uri':(work/'root/indexes').resolve().as_uri(),'default_index_root_uri':(work/'root/indexes').resolve().as_uri()}
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

CANONICAL = 'cheminee-fragment-tautomer-neutralize-v1'
PRESERVE = 'cheminee-fragment-neutralize-v1'

def normalize(smiles, preparation):
    molecule = Chem.MolFromSmiles(smiles)
    if preparation == 'sanitize-only-v1': return molecule
    molecule = rdMolStandardize.FragmentParent(molecule, skipStandardize=True)
    if preparation == CANONICAL:
        molecule = rdMolStandardize.TautomerEnumerator().Canonicalize(molecule)
    pattern = Chem.MolFromSmarts('[+1!h0!$([*]~[-1,-2,-3,-4]),-1!$([*]~[+1,+2,+3,+4])]')
    for (index,) in molecule.GetSubstructMatches(pattern):
        atom = molecule.GetAtomWithIdx(index)
        charge = atom.GetFormalCharge()
        if atom.GetIsAromatic() or (atom.GetHybridization() == Chem.HybridizationType.SP3 and charge < 0): continue
        hydrogens = atom.GetTotalNumHs()
        atom.SetFormalCharge(0)
        atom.SetNumExplicitHs(hydrogens-charge)
        atom.UpdatePropertyCache(strict=True)
        Chem.SetHybridization(molecule)
    molecule = Chem.MolFromSmiles(Chem.MolToSmiles(molecule))
    assert molecule is not None
    return molecule

def graph_score(document, query, kind, chirality, include_identity, ranking):
    forward = document.HasSubstructMatch(query, useChirality=chirality)
    reverse = query.HasSubstructMatch(document, useChirality=chirality)
    accepted = {'identity':forward and reverse, 'substructure':forward, 'superstructure':reverse}[kind]
    if not include_identity and kind != 'identity' and forward and reverse: accepted = False
    if not accepted: return None
    if ranking == 'stable_id' or kind == 'identity': return 1.0
    if kind == 'substructure': return f32(1/(1+document.GetNumHeavyAtoms()-query.GetNumHeavyAtoms()))
    return f32(document.GetNumHeavyAtoms()/query.GetNumHeavyAtoms())

try:
    start_node('root',0,['metastore','control-plane','indexer','janitor'])
    wait_for(lambda: request('/api/v1/cluster'))
    leaves=[start_node('leaf-a',10,['searcher']),start_node('leaf-b',20,['searcher'])]
    wait_for(lambda: len(request('/api/v1/cluster').get('ready_nodes',[]))==3)
    assert all(process.poll() is None for process in processes)
    results['cluster']=request('/api/v1/cluster')
    results['checks']=0
    source=Path(RDConfig.RDDataDir)/'NCI/first_5K.smi'
    raw_smiles=[line.split()[0] for line in source.read_text().splitlines()[:64]]
    raw_smiles += ['C','CC','CCC','CCCC','CCO','CCO','CCCO','CCN','c1ccccc1','Cc1ccccc1',
        'CC(=O)[O-].[Na+]','CC(=O)O','CC(O)=C','CC(=O)C','C[NH3+]','CN',
        'F[C@H](Cl)Br','F[C@@H](Cl)Br','C[C@H](O)C(=O)O','C[C@@H](O)C(=O)O','FC(Cl)Br','[13CH3]CO','[CH2-]C','c1cc[nH+]cc1']
    raw_smiles = ['CCO'] + raw_smiles + ['CCO']
    generator=rdFingerprintGenerator.GetMorganGenerator(radius=3,fpSize=2048,includeChirality=False)
    for preparation, index in [(CANONICAL,'canonical'), (PRESERVE,'preserve')]:
        spec={'format':'morgan-r3-2048-lsb0-v1','rdkit_version':rdBase.rdkitVersion,'preparation_id':preparation}
        field='morgan_'+hashlib.sha256(('morgan-r3-2048-lsb0-chiral0-features0-v1\0'+spec['rdkit_version']+'\0'+preparation).encode()).hexdigest()
        docs=[{'record_id':i,'smiles':s,'family':'even' if i%2==0 else 'odd'} for i,s in enumerate(raw_smiles)]
        fixture='\n'.join(json.dumps(doc,sort_keys=True) for doc in docs)+'\n'
        (work/'molecules.ndjson').write_text(fixture)
        results['fixture_sha256']=hashlib.sha256(fixture.encode()).hexdigest()
        molecules=[normalize(doc['smiles'],preparation) for doc in docs]
        fingerprints=[generator.GetFingerprint(mol) for mol in molecules]
        mapping={'version':'0.8','index_id':index,'doc_mapping':{'mode':'strict','chemistry':{'spec':spec,'smiles_field':'smiles','prepared_smiles_field':'prepared_smiles'},'field_mappings':[
            {'name':'record_id','type':'u64','fast':True}, {'name':'smiles','type':'text','tokenizer':'raw'},
            {'name':'family','type':'text','tokenizer':'raw'}, {'name':'prepared_smiles','type':'text','indexed':False,'fast':True},
            {'name':field,'type':'bytes','fast':True,'indexed':False,'input_format':'hex','output_format':'hex'}]},
            'indexing_settings':{'commit_timeout_secs':1,'merge_policy':{'type':'no_merge'}}}
        request('/api/v1/indexes',mapping)
        (work/(index+'-mapping.json')).write_text(json.dumps(mapping,indent=2))
        for start in range(0,len(docs),20):
            ingested=ingest(index,docs[start:start+20]);assert ingested['num_rejected_docs']==0,ingested
        invalid=request('/api/v1/'+index+'/ingest',json.dumps({'record_id':99999,'smiles':'bad-smiles','family':'invalid'}).encode(),raw=True)
        assert invalid['num_rejected_docs']==1
        if args.expect_native_unavailable:
            failed=request(f'/v1/indexes/{index}/search/identity',{'spec':spec,'smiles':'CC'},expected=503)
            assert 'native-chemistry' in failed['message'],failed
            exact=request(f'/v1/indexes/{index}/search/similarity',{'spec':spec,'smiles':'CC','tanimoto_minimum':0})
            assert exact['num_hits']==len(docs)
            results['native_unavailable']={'graph_status':503,'similarity_status':200,'error':failed}
            (work/'results.json').write_text(json.dumps(results,indent=2)+'\n')
            print(json.dumps(results['native_unavailable'],indent=2))
            sys.exit(0)
        for query_smiles in ['CC','CCO','CC(=O)[O-].[Na+]','CC(O)=C','F[C@H](Cl)Br','C[C@H](O)C(=O)O','c1ccccc1']:
            query=normalize(query_smiles,preparation)
            for kind in ['identity','substructure','superstructure']:
                for chirality in [False,True]:
                    for family in [None,'even','absent']:
                        for ranking in ['best_match','stable_id']:
                            for include_identity_value in [True,False]:
                                expected=[]
                                for doc,molecule in zip(docs,molecules):
                                    if family is not None and doc['family']!=family: continue
                                    score=graph_score(molecule,query,kind,chirality,include_identity_value,ranking)
                                    if score is not None: expected.append((score,doc['record_id']))
                                expected.sort(key=lambda item:(-item[0],item[1]))
                                body={'spec':spec,'smiles':query_smiles,'use_chirality':chirality,'ranking':ranking,
                                    'include_identity':include_identity_value,'extra_query':'*' if family is None else 'family:'+family,'result_limit':3}
                                response=request(f'/v1/indexes/{index}/search/{kind}',body)
                                actual=[(hit['score'],int(hit['record_id'])) for hit in response['hits']]
                                assert response['num_hits']==len(expected),(body,response,expected)
                                assert [id for _,id in actual]==[id for _,id in expected[:3]],(body,actual,expected[:3])
                                for (score,_),(oracle,_) in zip(actual,expected): assert abs(score-oracle)<1e-6
                                assert response['searched_splits']>=2
                                results['checks']+=1
            for threshold in [0,0.4,1]:
                query_fp=generator.GetFingerprint(query)
                expected=sorted([(f32(DataStructs.TanimotoSimilarity(query_fp,fp)),doc['record_id']) for doc,fp in zip(docs,fingerprints)],key=lambda pair:(-pair[0],pair[1]))
                expected=[pair for pair in expected if pair[0]>=f32(threshold)]
                response=request(f'/v1/indexes/{index}/search/similarity',{'spec':spec,'smiles':query_smiles,'tanimoto_minimum':threshold,'result_limit':3})
                assert response['num_hits']==len(expected)
                assert [int(hit['record_id']) for hit in response['hits']]==[id for _,id in expected[:3]]
                for hit,(score,_) in zip(response['hits'],expected): assert abs(hit['score']-score)<1e-6
                results['checks']+=1
        basic=request(f'/v1/indexes/{index}/search/basic',{'query':'family:even','extra_query':'record_id:[10 TO 30]','sort_field':'record_id','sort_ascending':True,'result_limit':3})
        assert basic['num_hits']==11 and [hit['record_id'] for hit in basic['hits']]==[10,12,14]
        for kind in ['basic','identity','substructure','superstructure','similarity']:
            valid={'query':'*'} if kind=='basic' else {'spec':spec,'smiles':'CCO'}
            request(f'/v1/indexes/{index}/search/{kind}',dict(valid,result_limit=0),expected=400)
            request(f'/v1/indexes/{index}/search/{kind}',dict(valid,unknown=True),expected=400)
            request(f'/v1/indexes/{index}/search/{kind}',dict(valid,extra_query='bad_field:foo'),expected=400)
            request(f'/v1/indexes/absent/search/{kind}',valid,expected=404)
            if kind!='basic': request(f'/v1/indexes/{index}/search/{kind}',dict(valid,smiles='bad-smiles'),expected=400)
        for kind in ['identity','substructure','superstructure']:
            request(f'/v1/indexes/{index}/search/{kind}',{'spec':spec,'smiles':'[H][H]'},expected=400)
        for kind, ranking in [('substructure','fewest_extra_heavy_atoms'),('superstructure','greatest_query_coverage')]:
            explicit=request(f'/v1/indexes/{index}/search/{kind}',{'spec':spec,'smiles':'CCO','ranking':ranking})
            default=request(f'/v1/indexes/{index}/search/{kind}',{'spec':spec,'smiles':'CCO'})
            assert explicit['hits']==default['hits'] and explicit['num_hits']==default['num_hits']
            request(f'/v1/indexes/{index}/search/identity',{'spec':spec,'smiles':'CCO','ranking':ranking},expected=400)
        mismatch=dict(spec,preparation_id=PRESERVE if preparation==CANONICAL else CANONICAL)
        request(f'/v1/indexes/{index}/search/identity',{'spec':mismatch,'smiles':'CCO'},expected=400)
        request(f'/v1/indexes/{index}/search/identity',{'spec':spec,'smiles':'CCO','prepared_smiles_field':'smiles'},expected=400)
        splits=request(f'/api/v1/indexes/{index}/splits')
        print('Completed oracle checks for',index,results['checks'],flush=True)
        results[index]={'split_metadata':splits,'documents':len(docs),'basic':basic}
    spec_json=request('/v1/openapi.json')
    validate_openapi(spec_json)
    assert len(spec_json['paths'])==5
    (work/'openapi.json').write_text(json.dumps(spec_json,indent=2))
    config=work/'client-config.json'
    config.write_text(json.dumps({'package_name_override':'cheminee_client','project_name_override':'cheminee-client'}))
    subprocess.run([str(Path(sys.executable).with_name('openapi-python-client')),'generate','--path',str(work/'openapi.json'),'--output-path',str(work/'cheminee_client'),'--meta','none','--config',str(config)],check=True,env=dict(os.environ,PATH=str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH','')))
    sys.path.insert(0,str(work))
    client_module=importlib.import_module('cheminee_client')
    models=importlib.import_module('cheminee_client.models')
    results['client']={}
    with client_module.Client(base_url=base) as client:
        for kind in ['basic','identity','substructure','superstructure','similarity']:
            operation=importlib.import_module('cheminee_client.api.cheminee.cheminee_v1_'+kind)
            model={'basic':models.BasicSearchRequest,'similarity':models.SmilesSimilarityRequest}.get(kind,models.GraphSearchRequest)
            data={'query':'*'} if kind=='basic' else {'spec':spec,'smiles':'CCO'}
            body=model.from_dict(data)
            success=operation.sync_detailed(index_id='preserve',client=client,body=body)
            assert success.status_code==200 and success.parsed is not None
            body.result_limit=0
            error=operation.sync_detailed(index_id='preserve',client=client,body=body)
            assert error.status_code==400 and isinstance(error.parsed,models.ChemistryError)
            results['client'][kind]={'success':200,'typed_error':400}
    false_positives=[{'record_id':100000+i,'smiles':'F[C@@H](Cl)Br','family':'adversarial'} for i in range(10051)]
    assert ingest('preserve',false_positives)['num_rejected_docs']==0
    assert ingest('preserve',[{'record_id':200000,'smiles':'F[C@H](Cl)Br','family':'adversarial'}])['num_rejected_docs']==0
    for kind in ['identity','substructure','superstructure']:
        response=request('/v1/indexes/preserve/search/'+kind,{'spec':spec,'smiles':'F[C@H](Cl)Br','use_chirality':True,'extra_query':'family:adversarial','result_limit':1})
        assert response['num_hits']==1 and response['hits'][0]['record_id']=='200000',response
        results['adversarial_'+kind]=response
    results['worker_metrics']={}
    for name,offset in [('leaf-a',10),('leaf-b',20)]:
        metrics=urllib.request.urlopen(f'http://127.0.0.1:{args.port_base+offset}/metrics',timeout=10).read().decode()
        (work/(name+'-metrics.txt')).write_text(metrics)
        results['worker_metrics'][name]=[line for line in metrics.splitlines() if not line.startswith('#') and 'search' in line and ('count' in line or 'total' in line)]
    (work/'results.json').write_text(json.dumps(results,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'checks':results['checks'],'routes':results['client'],'adversarial':True,'work':str(work)},indent=2))
finally:
    for process in processes:
        if process.poll() is None: process.send_signal(signal.SIGINT)
    for process in processes:
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill();process.wait()
    for log in logs: log.close()
