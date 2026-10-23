#!/usr/bin/env python3
"""Real HTTP schema evolution and deterministic timestamp ordering; synthetic fixtures."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

if not __debug__:
    raise SystemExit('correctness assertions require unoptimized Python')
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--binary', type=Path, required=True)
p.add_argument('--work-dir', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--reuse', action='store_true')
p.add_argument('--port', type=int, default=19680)
a = p.parse_args()
if a.output.exists(): p.error('choose fresh output')
if not a.reuse:
    a.work_dir.mkdir(parents=True, exist_ok=False)
    (a.work_dir/'data').mkdir()
base = 'http://127.0.0.1:' + str(a.port)
report = {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'checks': [],
    'failures': [], 'binary_sha256': hashlib.sha256(a.binary.read_bytes()).hexdigest(),
    'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'scope': 'single native worker, synthetic schema-evolution and timestamp fixtures'}
http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def request(method, path, body=None):
    if isinstance(body, dict): body = json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=body, method=method,
        headers={'Content-Type': 'application/x-ndjson' if '/ingest?' in path else 'application/json'})
    try:
        with http.open(req, timeout=45) as r: return r.status, json.load(r)
    except urllib.error.HTTPError as e: return e.code, json.load(e)
def must(method, path, body=None):
    code, data = request(method, path, body)
    assert code == 200, (path, code, data)
    return data
def ingest(index, rows):
    result = must('POST', '/api/v1/' + index + '/ingest?commit=force',
        b''.join((json.dumps(r) + '\n').encode() for r in rows))
    assert result['num_ingested_docs'] == len(rows) and result['num_rejected_docs'] == 0, result
def check(name, index, query, ids, total, size=5, sort=None, expected_status=200, offset=0):
    code, data = request('POST', '/api/v1/_elastic/' + index + '/_search?allow_partial_search_results=false',
        {'query':query, 'size':size, 'from':offset, 'track_total_hits':True,
         'sort':sort or [{'record_id':'asc'}]})
    errors=[]
    if code != expected_status: errors.append('status')
    if code == expected_status == 200:
        if data.get('hits',{}).get('total') != {'value':total,'relation':'eq'}: errors.append('exact total')
        if [h['_source']['record_id'] for h in data['hits']['hits']] != ids: errors.append('ordered IDs')
        if data.get('_shards',{}).get('failed') != 0 or data.get('timed_out') is not False: errors.append('incomplete')
    report['checks'].append({'name':name,'query':query,'size':size,'offset':offset,'sort':sort,
        'expected_status':expected_status,'expected_ids':ids,'expected_total':total,'status':code,'response':data,'errors':errors})
    if errors: report['failures'].append(name)
config = {'version':'0.8','cluster_id':'schema-timestamp','node_id':'single',
    'listen_address':'127.0.0.1','rest':{'listen_port':a.port},'data_dir':str(a.work_dir/'data'),
    'metastore_uri':(a.work_dir/'data/indexes').as_uri(),
    'default_index_root_uri':(a.work_dir/'data/indexes').as_uri(),
    'indexer':{'enable_otlp_endpoint':False,'cpu_capacity':'16000m'},
    'searcher':{'max_num_concurrent_split_searches':1}}
(a.work_dir/'node.json').write_text(json.dumps(config))
log=(a.work_dir/(a.output.stem+'-server.log')).open('w')
server=subprocess.Popen([str(a.binary.resolve()),'run','--config',str(a.work_dir/'node.json')],stdout=log,stderr=subprocess.STDOUT,
    env=dict(os.environ,QW_DISABLE_TELEMETRY='1',QW_DISABLE_PER_INDEX_METRICS='1'))
try:
    deadline=time.monotonic()+60
    while True:
        if server.poll() is not None: raise RuntimeError('server exited during startup; inspect log')
        try:
            code, cluster=request('GET','/api/v1/cluster')
            if code==200 and len(cluster.get('ready_nodes',[]))==1: break
        except (OSError,ValueError): pass
        if time.monotonic()>deadline: raise TimeoutError('startup')
        time.sleep(.2)
    spec={'format':'morgan-r3-2048-lsb0-v1','rdkit_version':'2026.09.1','preparation_id':'sanitize-only-v1'}
    fp='morgan_'+hashlib.sha256(('morgan-r3-2048-lsb0-chiral0-features0-v1\0'+spec['rdkit_version']+'\0'+spec['preparation_id']).encode()).hexdigest()
    settings={'commit_timeout_secs':1,'merge_policy':{'type':'no_merge'},'resources':{'heap_size':'32MiB'}}
    index='schema-evolution'
    if not a.reuse:
        old={'version':'0.9','index_id':index,'doc_mapping':{'mode':'strict','tag_fields':[],'timestamp_field':'timestamp',
            'field_mappings':[{'name':'record_id','type':'u64','fast':True},
                {'name':'timestamp','type':'datetime','fast':True,'input_formats':['rfc3339'],'fast_precision':'nanoseconds'},
                {'name':'family','type':'text','tokenizer':'raw'}, {'name':'smiles','type':'text','tokenizer':'raw'}]},
             'indexing_settings':settings}
        must('POST','/api/v1/indexes',old)
        ingest(index,[{'record_id':1,'family':'old','smiles':'CCO','timestamp':'1970-01-01T00:00:01.200000000Z'}])
        new=json.loads(json.dumps(old))
        new['doc_mapping']['chemistry']={'spec':spec,'smiles_field':'smiles','prepared_smiles_field':'prepared'}
        new['doc_mapping']['field_mappings'] += [
            {'name':'prepared','type':'text','fast':True,'indexed':False},
            {'name':fp,'type':'bytes','fast':True,'indexed':False,'input_format':'hex','output_format':'hex'}]
        must('PUT','/api/v1/indexes/'+index,new)
        ingest(index,[{'record_id':2,'family':'new','smiles':'CCO','timestamp':'1970-01-01T00:00:02.500000000Z'}])
    splits=must('GET','/api/v1/indexes/'+index+'/splits?split_states=Published')['splits']
    assert len(splits)==2 and len({s['doc_mapping_uid'] for s in splits})==2, splits
    assert sum(s['num_docs'] for s in splits)==2
    assert not any(tag.startswith('family') for s in splits for tag in s['tags'])
    report['schema_splits']=splits
    deadline=time.monotonic()+30
    while True:
        code, all_docs=request('POST','/api/v1/_elastic/'+index+'/_search?allow_partial_search_results=false',
            {'query':{'match_all':{}},'size':5,'track_total_hits':True})
        if code==200: break
        assert code==500 and 'no available searcher nodes' in json.dumps(all_docs), all_docs
        report['startup_read_retries']=report.get('startup_read_retries',0)+1
        if time.monotonic()>deadline: raise TimeoutError('searcher membership')
        time.sleep(.2)
    fingerprint=next(h['_source'][fp] for h in all_docs['hits']['hits'] if h['_source']['record_id']==2)
    operators={
        'tanimoto':{'spec':spec,'fingerprint_hex':fingerprint,'minimum':0.0},
        'fingerprint_contains':{'spec':spec,'fingerprint_hex':fingerprint,'direction':'document_contains_query'},
        'molecular_graph':{'spec':spec,'prepared_field':'prepared','prepared_smiles':'CCO','predicate':'identity',
                           'ranking':'stable_id','use_chirality':True,'include_identity':True}}
    for op, args in operators.items():
        for candidate,ids,status in [('new',[2],200),('absent',[],200),('old',[],500)]:
            query={op:dict(args,candidates={'type':'term','field':'family','value':candidate})}
            for size in [0,5]: check(op+'/'+candidate+'/'+str(size),index,query,ids if size else [],len(ids),size,expected_status=status)
        check(op+'/unbounded',index,{op:args},[],0,expected_status=500)
        check(op+'/sorted-count-relevant-error',index,{op:args},[],0,size=1,
              sort=[{'timestamp':'desc'},{'record_id':'asc'}],expected_status=500)
        bad=dict(args,candidates={'type':'term','field':'family','value':'absent'})
        bad['prepared_smiles' if op=='molecular_graph' else 'fingerprint_hex']='invalid'
        check(op+'/eager-invalid',index,{op:bad},[],0,expected_status=400)
        check(op+'/necessary-sibling',index,{'bool':{'filter':[{'term':{'family':'new'}},{op:args}]}},[2],1)
    cases={
        'positive-desc':('desc',[(99,'1970-01-01T00:00:02.500000000Z',False),(12,'1970-01-01T00:00:01.200000000Z',True)],[(18,'1970-01-01T00:00:01.800000000Z',True)],[18,12,5]),
        'negative-asc':('asc',[(99,'1969-12-31T23:59:57.500000000Z',False),(12,'1969-12-31T23:59:58.800000000Z',True)],[(18,'1969-12-31T23:59:58.200000000Z',True)],[18,12,5]),
        'tie-desc':('desc',[(99,'1970-01-01T00:00:02.500000000Z',False),(12,'1970-01-01T00:00:01.500000000Z',True)],[(2,'1970-01-01T00:00:01.500000000Z',True)],[2,12,5]),
    }
    for name,(order,first,second,expected) in cases.items():
        idx='timestamp-'+name
        if not a.reuse:
            must('POST','/api/v1/indexes',{'version':'0.9','index_id':idx,'doc_mapping':{'timestamp_field':'timestamp','field_mappings':[
                {'name':'record_id','type':'u64','fast':True},{'name':'keep','type':'bool'},
                {'name':'timestamp','type':'datetime','fast':True,'input_formats':['rfc3339'],'fast_precision':'nanoseconds'}]},'indexing_settings':settings})
            worse='1969-12-31T23:59:59.500000000Z' if order=='asc' else '1970-01-01T00:00:00.500000000Z'
            for rows in [first,second,[(5,worse,True)]]: ingest(idx,[{'record_id':i,'timestamp':t,'keep':k} for i,t,k in rows])
        tsplits=must('GET','/api/v1/indexes/'+idx+'/splits?split_states=Published')['splits']
        assert len(tsplits)==3 and sum(s['num_docs'] for s in tsplits)==4,tsplits
        report.setdefault('timestamp_splits',{})[idx]=tsplits
        for iteration in ['cold','warm']:
            for size,offset,ids in [(1,0,expected[:1]),(1,1,expected[1:2]),(0,0,[])]:
                check(name+'/'+iteration+'/'+str(size)+'/'+str(offset),idx,{'term':{'keep':'true'}},ids,3,size,
                      [{'timestamp':order},{'record_id':'asc'}],offset=offset)
    report['status']='passed' if not report['failures'] else 'failed'
except BaseException as e:
    report['execution_error']=type(e).__name__+': '+str(e)
    report['status']='error'
    raise
finally:
    server.terminate()
    try: server.wait(timeout=30)
    except subprocess.TimeoutExpired: server.kill();server.wait()
    log.close()
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'checks':len(report['checks']),'failures':report['failures']}))
