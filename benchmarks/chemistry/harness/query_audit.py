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

import argparse,fcntl,hashlib,json,os,pathlib,subprocess,time,urllib.request,urllib.error
from resources import process_sample
ROOT=pathlib.Path(os.environ['STUDY_ROOT']);p=argparse.ArgumentParser();p.add_argument('tag');args=p.parse_args();run=ROOT/'runs'/args.tag
lock=(ROOT/'engine.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
meta=json.loads((run/'summary.json').read_text());assert meta['size']==100000
queries=json.loads((ROOT/'audits/query-oracles.json').read_text())['queries'];spec=json.loads((run/'index.json').read_text())['doc_mapping']['chemistry']['spec']
command=json.loads((run/'command.json').read_text())['command'];command=command[:4]+['--service','metastore','--service','searcher']
env=dict(os.environ,QW_NUM_CPUS=str(meta['cpu_hint']),QW_TOKIO_RUNTIME_NUM_THREADS='2',QW_DISABLE_TELEMETRY='1');env.pop('LD_PRELOAD',None)
def request(path,body=None):
 req=urllib.request.Request('http://127.0.0.1:7280'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=120) as r:return r.status,json.load(r)
 except urllib.error.HTTPError as e:return e.code,e.read().decode()
results=[];proc=None
try:
 proc=subprocess.Popen(command,env=env,stdout=(run/'query-audit-service.log').open('w'),stderr=subprocess.STDOUT)
 for _ in range(600):
  if proc.poll() is not None:raise RuntimeError('service exited')
  try:
   if request('/health/livez')[0]==200:break
  except OSError:pass
  time.sleep(.2)
 else:raise RuntimeError('startup timeout')
 time.sleep(10)
 for q in queries:
  if q['kind']=='basic':body={'query':q['query'],'result_limit':q.get('result_limit',10),'sort_field':'record_id','sort_ascending':True}
  else:
   body={'spec':spec,'smiles':q['smiles'],'result_limit':q.get('result_limit',10)}
   if q['kind']=='similarity':body['tanimoto_minimum']=q['threshold']
   else:body.update(prepared_smiles_field='smiles',use_chirality=False)
  before=process_sample(proc.pid);status,response=request('/v1/indexes/moses/search/'+q['kind'],body);after=process_sample(proc.pid)
  row={'name':q['name'],'status':status,'expected_status':q.get('expected_status_quickwit',200),'wall_seconds':(after['monotonic_ns']-before['monotonic_ns'])/1e9,'cpu_core_seconds':after['cpu_core_seconds']-before['cpu_core_seconds']}
  assert status==row['expected_status'],(q['name'],status,response)
  if status==200:
   assert response['num_hits']==q['num_hits'],(q['name'],response['num_hits'],q['num_hits'])
   ids=[int(h['record_id']) for h in response['hits']]
   expected=q.get('expected_quickwit_top10_ids') if q['kind']=='basic' else q.get('hits',q.get('expected_quickwit_top10'))
   if q['kind']!='basic':expected=[i for i,_ in expected[:q.get('result_limit',10)]]
   assert ids==expected,(q['name'],ids,expected)
   if q['kind']!='basic':
    scores=dict(q.get('hits',q.get('expected_quickwit_top10')))
    assert all(abs(h['score']-scores[int(h['record_id'])])<=1e-6 for h in response['hits'])
   row.update(num_hits=response['num_hits'],returned_ids=ids)
  row['status_check']='passed';results.append(row)
 (run/'query-audit.json').write_text(json.dumps({'status':'passed','queries':len(results),'oracle_sha256':hashlib.file_digest((ROOT/'audits/query-oracles.json').open('rb'),'sha256').hexdigest(),'results':results},indent=2))
 print('PASS',args.tag,len(results),'queries')
finally:
 if proc and proc.poll() is None:
  proc.terminate()
  try:proc.wait(timeout=60)
  except subprocess.TimeoutExpired:proc.kill();proc.wait()
