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

import argparse,base64,fcntl,hashlib,json,os,pathlib,subprocess,time,urllib.request
ROOT=pathlib.Path(os.environ['STUDY_ROOT']);p=argparse.ArgumentParser();p.add_argument('run');a=p.parse_args();run=ROOT/'runs'/a.run
lock=(ROOT/'engine.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
summary=json.loads((run/'summary.json').read_text());size=summary['size'];output=run/'stored-audit.ndjson';results={'expected_rows':size,'fields':['smiles','morgan_fingerprint','pattern_fingerprint','extra_data'],'rows':0,'mismatches':0,'duplicate_record_ids':0,'examples':[]}
expected={}
for i,line in enumerate((ROOT/'audits/native-100k.ndjson').open()):
 if i==size:break
 r=json.loads(line);expected[r['extra_data']['record_id']]=r
if summary['engine']=='cheminee':
 with output.open('w') as f:subprocess.run([str(ROOT/'target-cheminee/release/examples/audit_index'),str(run/'engine/moses')],stdout=f,check=True)
 def rows():
  for line in output.open():yield {k:v[0] for k,v in json.loads(line).items()}
else:
 env=dict(os.environ,QW_DISABLE_TELEMETRY='1');env.pop('LD_PRELOAD',None);command=json.loads((run/'command.json').read_text())['command'];command[0]=str(ROOT/'bin/quickwit-control');command=command[:4]+['--service','metastore','--service','searcher']
 process=subprocess.Popen(command,env=env,stdout=(run/'stored-audit-service.log').open('w'),stderr=subprocess.STDOUT)
 def request(path,body=None):
  req=urllib.request.Request('http://127.0.0.1:7280'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=120) as r:return json.load(r)
 try:
  for _ in range(600):
   try:request('/health/livez');break
   except OSError:time.sleep(.2)
  time.sleep(10)
  with output.open('w') as f:
   for start in range(1,size+1,5000):
    response=request('/api/v1/moses/search',{'query':f'record_id:[{start} TO {min(size,start+4999)}]','max_hits':5000})
    assert response['num_hits']==min(5000,size-start+1),response
    for hit in response['hits']:f.write(json.dumps(hit,separators=(',',':'))+'\n')
 finally:
  process.terminate()
  try:process.wait(timeout=180)
  except subprocess.TimeoutExpired:process.kill();process.wait()
 specfield=next(f['name'] for f in json.loads((run/'index.json').read_text())['doc_mapping']['field_mappings'] if f['name'].startswith('morgan_'))
 def rows():
  for line in output.open():
   r=json.loads(line);r['morgan_fingerprint']=r.pop(specfield);yield r
seen=set()
for r in rows():
 rid=r['extra_data']['record_id'];results['rows']+=1
 if rid in seen:results['duplicate_record_ids']+=1
 seen.add(rid)
 for field in results['fields']:
  if r[field]!=expected[rid][field]:
   results['mismatches']+=1
   if len(results['examples'])<10:results['examples'].append({'record_id':rid,'field':field})
results['missing_record_ids']=sorted(set(expected)-seen);results['sha256']=hashlib.file_digest(output.open('rb'),'sha256').hexdigest();results['status']='passed' if results['rows']==size and not results['mismatches'] and not results['duplicate_record_ids'] and not results['missing_record_ids'] else 'failed'
(run/'stored-audit.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2));assert results['status']=='passed'
