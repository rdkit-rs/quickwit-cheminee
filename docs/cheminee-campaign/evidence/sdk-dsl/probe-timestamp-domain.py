import json, urllib.request, urllib.error, pathlib, copy
w=pathlib.Path('/workspace/recovery/composable-native-run1')
base='http://127.0.0.1:19480'
def request(path, body, raw=False):
    req=urllib.request.Request(base+path,data=body if raw else json.dumps(body).encode(),headers={'Content-Type':'application/x-ndjson' if raw else 'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=90) as r: return {'status':r.status,'response':json.load(r)}
    except urllib.error.HTTPError as e: return {'status':e.code,'response':json.load(e)}
original=json.loads((w/'results.json').read_text())
q=next(c['leaf_verification_failure'] for c in original['checks'] if 'leaf_verification_failure' in c)
m=json.loads((w/'mapping.json').read_text()); m['index_id']='composable-timestamp-domain'; m['doc_mapping'].pop('chemistry'); m['doc_mapping']['timestamp_field']='observed_at'; m['doc_mapping']['field_mappings'].append({'name':'observed_at','type':'datetime','fast':True})
fp=next(f['name'] for f in m['doc_mapping']['field_mappings'] if f['type']=='bytes')
create=request('/api/v1/indexes',m); assert create['status']==200,create
rows=[{'record_id':1,'observed_at':'2020-01-01T00:00:00Z',fp:q['tanimoto']['fingerprint_hex']},{'record_id':2,'observed_at':'2021-01-01T00:00:00Z',fp:'01'}]
ingest=request('/api/v1/composable-timestamp-domain/ingest?commit=force','\n'.join(map(json.dumps,rows)).encode(),True); assert ingest['status']==200,ingest
bounded=copy.deepcopy(q); bounded['tanimoto']['candidates']={'type':'range','field':'observed_at','lower_bound':{'Included':'2020-01-01T00:00:00Z'},'upper_bound':{'Included':'2020-12-31T00:00:00Z'}}
out={'mapping':m,'ingest':ingest,'queries':{}}
for name,query in [('unbounded',q),('explicit_timestamp_candidates',bounded)]: out['queries'][name]={'query':query,**request('/api/v1/_elastic/composable-timestamp-domain/_search?allow_partial_search_results=false',{'query':query,'size':20,'track_total_hits':True})}
(w/'timestamp-domain-probe.json').write_text(json.dumps(out,indent=2)); print(json.dumps(out))
