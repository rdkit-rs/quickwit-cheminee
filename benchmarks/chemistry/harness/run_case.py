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

import concurrent.futures,threading
import argparse,fcntl,hashlib,json,os,pathlib,subprocess,time,urllib.request,urllib.parse,urllib.error
from resources import Sampler,process_sample,files_snapshot
ROOT=pathlib.Path(os.environ['STUDY_ROOT'])
p=argparse.ArgumentParser();p.add_argument('engine',choices=['quickwit','cheminee']);p.add_argument('--tag',required=True);p.add_argument('--size',type=int,default=100000);p.add_argument('--instrumented',action='store_true');p.add_argument('--lifecycle-seconds',type=int,default=2580);p.add_argument('--boot-idle',type=int,default=30);p.add_argument('--allocation-profile',action='store_true')
p.add_argument('--batch',type=int,default=200);p.add_argument('--concurrency',type=int,default=1);p.add_argument('--cpu-hint',type=int,default=4);p.add_argument('--commit-seconds',type=int,default=30)
a=p.parse_args()
assert a.engine=='quickwit'
assert a.batch>0 and a.concurrency>0
lock=(ROOT/'engine.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
# Capacity guard is outside every measured interval. Preserve matched run size.
space=os.statvfs(ROOT);free_bytes=space.f_bavail*space.f_frsize
reserve_bytes=2*1024**3;peak_additional_bytes=512*1024**2
preflight={'tag':a.tag,'time_unix_seconds':time.time(),'available_bytes':free_bytes,'reserve_bytes':reserve_bytes,'estimated_peak_additional_bytes':peak_additional_bytes,'basis':'Completed 100k runs retain <=230 MiB; raw/compressed audit coexistence adds about100 MiB. Budget512 MiB per new run, keep2 GiB reserve.'}
with (pathlib.Path(os.environ['STUDY_OUTPUT'])/'disk-preflights.jsonl').open('a') as out:out.write(json.dumps(preflight)+'\n')
if a.size>100000:raise RuntimeError('A larger corpus requires a separate measured capacity preflight')
if free_bytes<reserve_bytes+peak_additional_bytes:raise RuntimeError(f'Disk preflight stopped before launch: {free_bytes} bytes available, {reserve_bytes+peak_additional_bytes} required; preserve all prior evidence')
run=ROOT/'runs'/a.tag;run.mkdir(parents=True,exist_ok=False)
(run/'disk-preflight.json').write_text(json.dumps(preflight,indent=2))
variant='instrumented' if a.instrumented else 'control'
binary=ROOT/'bin'/f'{a.engine}-{variant}'
if not binary.is_file():raise RuntimeError(f'missing {binary}')
# A build or a second engine invalidates timing: refuse rather than subtract it later.
for entry in pathlib.Path('/proc').iterdir():
 if entry.name.isdigit():
  try:
   name=(entry/'comm').read_text().strip()
   if (entry/'stat').read_text().rsplit(')',1)[1].split()[0]=='Z':continue
  except FileNotFoundError:continue
  if name in ['rustc','cargo','cheminee','quickwit'] or name.startswith(('quickwit-','cheminee-')):raise RuntimeError(f'competing process {entry.name}: {name}')
setup_start=time.monotonic();setup_cpu=time.process_time()
rows=[]
with (ROOT/'data/raw-100k.ndjson').open() as f:
 for line in f:
  rows.append(json.loads(line))
  if len(rows)==a.size:break
assert len(rows)==a.size
batch_size=a.batch
payloads=[]
for i in range(0,len(rows),batch_size):
 batch=rows[i:i+batch_size]
 if a.engine=='quickwit':
  payload=b''.join((json.dumps({'record_id':r['extra_data']['record_id'],'input_smiles':r['smiles'],'extra_data':r['extra_data']},separators=(',',':'))+'\n').encode() for r in batch)
 else:payload=json.dumps({'docs':batch},separators=(',',':')).encode()
 payloads.append((i+1,len(batch),payload))
summary={'allocation_profile':a.allocation_profile,'engine':a.engine,'variant':variant,'tag':a.tag,'size':a.size,'batch_size':batch_size,'concurrency':a.concurrency,'cpu_hint':a.cpu_hint,'commit_seconds':a.commit_seconds,'setup_wall_seconds':time.monotonic()-setup_start,'setup_controller_cpu_seconds':time.process_time()-setup_cpu,'binary_sha256':hashlib.file_digest(binary.open('rb'),'sha256').hexdigest(),'payload_body_bytes':sum(len(x[2]) for x in payloads),'phases':{},'requests':[]}
port=7280 if a.engine=='quickwit' else 4001
base=f'http://127.0.0.1:{port}'+('/api' if a.engine=='cheminee' else '')
env=dict(os.environ,QW_DISABLE_TELEMETRY='1',RUST_LOG='info',CARGO_MANIFEST_DIR=str(ROOT/'cheminee-baseline'))
env.update(QW_NUM_CPUS=str(a.cpu_hint),QW_TOKIO_RUNTIME_NUM_THREADS='2')
for key in ['RAYON_NUM_THREADS','TOKIO_WORKER_THREADS','TF_NUM_INTRAOP_THREADS','TF_NUM_INTEROP_THREADS','OMP_NUM_THREADS']:env.pop(key,None)
if a.instrumented:env.update(LD_PRELOAD=str(ROOT/'instrumentation/libstage.so'),STUDY_STAGE_FILE=str(run/'stage-cpu.jsonl'))
else:env.pop('LD_PRELOAD',None);env.pop('STUDY_STAGE_FILE',None)
if a.engine=='quickwit':
 data=run/'engine';data.mkdir()
 config={'version':'0.8','cluster_id':'study-'+a.tag,'node_id':'single','listen_address':'127.0.0.1','rest':{'listen_port':port},'indexer':{'cpu_capacity':'4000m','merge_concurrency':2,'max_concurrent_split_uploads':12},'data_dir':str(data),'metastore_uri':(run/'indexes').as_uri(),'default_index_root_uri':(run/'indexes').as_uri()}
 (run/'node.json').write_text(json.dumps(config,indent=2))
 command=[str(binary),'run','--config',str(run/'node.json')]
 for service in ['metastore','control_plane','indexer','searcher','janitor']:command+=['--service',service]
else:command=[str(binary),'rest-api-server','--bind',f'127.0.0.1:{port}','--index-storage-directory',str(run/'engine'),'--index-storage-directory-create-if-missing']
(run/'command.json').write_text(json.dumps({'command':command,'settings':{'cpus':4,'memory_bytes':14*1024**3,'storage':'file:// local','instrumented':a.instrumented}},indent=2))
(run/'effective-inputs.json').write_text(json.dumps({'runtime_revision':'7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b','environment':{k:env[k] for k in ['QW_NUM_CPUS','QW_TOKIO_RUNTIME_NUM_THREADS','QW_DISABLE_TELEMETRY']},'cpu_max':pathlib.Path('/sys/fs/cgroup/cpu.max').read_text(),'cpuset':pathlib.Path('/sys/fs/cgroup/cpuset.cpus.effective').read_text(),'affinity':sorted(os.sched_getaffinity(0)),'memory_max':pathlib.Path('/sys/fs/cgroup/memory.max').read_text(),'input_sha256':hashlib.file_digest((ROOT/'data/raw-100k.ndjson').open('rb'),'sha256').hexdigest()},indent=2))
def http(path,body=None,method=None,timeout=120):
 req=urllib.request.Request(base+path,data=body,method=method,headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=timeout) as response:return response.status,response.read()
 except urllib.error.HTTPError as error:raise RuntimeError(f'{path}: HTTP {error.code}: {error.read().decode()}') from error
def get_json(path,**kwargs):return json.loads(http(path,**kwargs)[1])
def barrier():
 if a.engine=='quickwit':return get_json('/api/v1/moses/search?query=*&max_hits=0')['num_hits']
 data=get_json('/v1/indexes/moses/search/basic?query=*&limit='+str(a.size+1))
 (run/'visibility-response.json').write_text(json.dumps(data,separators=(',',':')))
 return len(data)
def boundary(name):
 point=process_sample(process.pid);point['cgroup']={f:pathlib.Path('/sys/fs/cgroup',f).read_text() for f in ['cpu.stat','memory.current','memory.events','memory.peak']};summary['phases'][name]=point
 (run/'summary.partial.json').write_text(json.dumps(summary,indent=2))
 return point
process=None;sampler=None;allocation_process=None
if a.allocation_profile:
 assert not a.instrumented,'Allocation and CPU profiling are separate experiments'
 fifo=run/'heaptrack.fifo';os.mkfifo(fifo)
 allocation_process=subprocess.Popen(['bash','-c','set -o pipefail; /usr/lib/heaptrack/libexec/heaptrack_interpret < "$1" | gzip -1 > "$2"','heaptrack-consumer',str(fifo),str(run/'heaptrack.gz')],stderr=(run/'heaptrack-interpreter.log').open('w'))
 env.update(LD_PRELOAD='/usr/lib/heaptrack/libheaptrack_preload.so',DUMP_HEAPTRACK_OUTPUT=str(fifo))
try:
 log=(run/'service.log').open('w');started=time.monotonic()
 process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env)
 sampler=Sampler(process.pid,run/'resources.jsonl');sampler.start()
 for _ in range(600):
  if process.poll() is not None:raise RuntimeError(f'service exited {process.returncode}')
  try:
   http('/health/livez' if a.engine=='quickwit' else '/v1/schemas',timeout=2);break
  except (OSError,urllib.error.HTTPError):time.sleep(.2)
 else:raise RuntimeError('service startup timed out')
 summary['startup_wall_seconds']=time.monotonic()-started
 time.sleep(a.boot_idle);boundary('quiescent_empty')
 if a.engine=='quickwit':
  config=json.loads((ROOT/'data/quickwit-index.json').read_text());config['indexing_settings']['commit_timeout_secs']=a.commit_seconds;(run/'index.json').write_text(json.dumps(config,indent=2));http('/api/v1/indexes',json.dumps(config).encode(),method='POST')
 else:http('/v1/indexes/moses?schema=descriptor_v1',method='POST')
 time.sleep(10)
 boundary('ingest_start')
 request_lock=threading.Lock()
 def send_batch(item):
  first_id,count,body=item
  start=time.monotonic_ns()
  path='/api/v1/moses/ingest?commit=auto&detailed_response=true' if a.engine=='quickwit' else '/v1/indexes/moses/bulk_index'
  status,response=http(path,body,method='POST');parsed=json.loads(response)
  record={'first_id':first_id,'count':count,'status':status,'request_body_bytes':len(body),'response_body_bytes':len(response),'start_monotonic_ns':start,'end_monotonic_ns':time.monotonic_ns(),'response':parsed}
  summary['requests'].append(record)
  if a.engine=='quickwit':
   assert parsed.get('num_ingested_docs')==count and not parsed.get('num_rejected_docs',0),parsed
  else:assert len(parsed['statuses'])==count and all(s.get('error') is None for s in parsed['statuses']),parsed
  with request_lock:
   with (run/'requests.jsonl').open('a') as out:out.write(json.dumps(record)+'\n')
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as executor:
  list(executor.map(send_batch,payloads))
 boundary('accepted')
 deadline=time.monotonic()+300
 while True:
  count=barrier()
  if count==a.size:break
  if count>a.size or time.monotonic()>deadline:raise RuntimeError(f'visibility count {count}, expected {a.size}')
  time.sleep(2)
 boundary('all_searchable')
 (run/'metrics-searchable.txt').write_bytes(http('/metrics')[1])
 if a.engine=='quickwit':(run/'splits-searchable.json').write_text(json.dumps(get_json('/api/v1/indexes/moses/splits'),indent=2))
 (run/'files-searchable.json').write_text(json.dumps(files_snapshot(run/'engine'),indent=2))
 # Observe lifecycle without forcing merge, cleanup, or deleting retained files.
 deadline=time.monotonic()+a.lifecycle_seconds
 while time.monotonic()<deadline:
  time.sleep(min(30,max(0,deadline-time.monotonic())))
  if process.poll() is not None:raise RuntimeError('service exited during lifecycle observation')
  if a.engine=='quickwit':
   with (run/'lifecycle-splits.jsonl').open('a') as f:f.write(json.dumps({'monotonic_ns':time.monotonic_ns(),'splits':get_json('/api/v1/indexes/moses/splits')})+'\n')
 boundary('lifecycle_observed')
 (run/'metrics-lifecycle.txt').write_bytes(http('/metrics')[1])
 for directory in ['engine','indexes']:
  if (run/directory).is_dir():(run/f'files-{directory}-lifecycle.json').write_text(json.dumps(files_snapshot(run/directory),indent=2))
 if a.engine=='quickwit':(run/'splits-lifecycle.json').write_text(json.dumps(get_json('/api/v1/indexes/moses/splits'),indent=2))
 summary['status']='completed'
except Exception as error:
 summary['status']='failed';summary['error']=repr(error)
 raise
finally:
 if process and process.poll() is None:
  process.terminate()
  try:process.wait(timeout=330 if a.lifecycle_seconds>=2580 or a.allocation_profile else 40);summary['forced_shutdown']=False
  except subprocess.TimeoutExpired:process.kill();process.wait();summary['forced_shutdown']=True
 if sampler:sampler.stop()
 if allocation_process:summary['allocation_profiler_exit']=allocation_process.wait(timeout=60)
 if process:summary['exit_code']=process.returncode
 summary.pop('requests',None)
 (run/'summary.json').write_text(json.dumps(summary,indent=2))
 print(json.dumps(summary,indent=2))
