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

import hashlib,json,os,pathlib,re,zipfile
ROOT=pathlib.Path(os.environ['QUERY_STUDY_ROOT'])
DEST=pathlib.Path(os.environ['EVIDENCE_OUTPUT']);DEST.mkdir(parents=True,exist_ok=True)
RESOURCE_KEYS=['monotonic_ns','cpu_core_seconds','threads','Rss','Pss','Pss_Dirty','Pss_Anon','Pss_File','Pss_Shmem','Shared_Clean','Shared_Dirty','Private_Clean','Private_Dirty','Referenced','Anonymous','KSM','LazyFree','AnonHugePages','ShmemPmdMapped','FilePmdMapped','Shared_Hugetlb','Private_Hugetlb','Swap','SwapPss','Locked','rchar','wchar','syscr','syscw','read_bytes','write_bytes','cancelled_write_bytes','mmap_count','file_mmap_count','unique_mapped_files','fd_count','cgroup_cpu_stat']
def read(path):return json.loads(path.read_text())
def rows(path):return [json.loads(line) for line in path.read_text().splitlines()]
def select(row,keys):return {key:row[key] for key in keys if key in row}
def encode(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def safe(raw):
 assert not re.search(rb'/workspace/|/tmp/|libfile_|download_url|Authorization|Bearer |api[_-]?key|"pid"|"address"',raw,re.I)
 return raw
metrics=read(ROOT/'candidate-comparison-metrics.json');assert metrics['status']=='completed_and_audited'
metrics['experiment']='007'
metrics['publication_scope']='Combined batched decoding and candidate-first exact scoring on100k, result/predicate caches disabled; local source only. Includes separate bounded held-out C4 probes.'
for key in ['source','instrumented_source']:
 provenance=metrics[key]
 metrics[key]=select(provenance,['source_revision','source_base','production_source','profiler_revision','profiler_sha256','features','binary_sha256','binary_bytes','acceptance'])
metrics['commands']={'build':'cargo build --locked --release -p quickwit-cli --features descriptor-v1 --bin quickwit','test':'cargo test --locked --release -p tantivy-rdkit --features openapi','toolchain':'1.96.1','bindings':'0ae060c9cfc14626172070989fee890b16454373','rdkit_package':'2026.09.1+ds1-1~ubuntu26.04','tensorflow':'2.15.1 CPU'}
for run in metrics['runs']+metrics['heldout_extension']['runs']:
 run['boundaries']={key:select(value,RESOURCE_KEYS) for key,value in run['boundaries'].items()}
 for batch in run['batches']:
  assert batch['oracle_status']=='passed'
  if 'common_window_reconciliation' in batch:assert abs(batch['common_window_reconciliation']['process_minus_stage_core_seconds'])<.02
(DEST/'007-candidate-query-metrics.json').write_bytes(safe(encode(metrics)))
cases=read(ROOT/'cases-extended.json');case_map={case['name']:case for case in cases['cases']}
manifest={'experiment':'007','definition':'Sanitized query counter traces with unchanged numeric counters/timestamps. Omits process IDs, addresses, paths, service logs, request bodies and returned documents. Exact query definitions remain in the metrics JSON; ordered ID/score audits and raw-source hashes bind accepted responses. Combined candidate/batched-decode change; query-specific100k measurements, result caches disabled.','members':[]}
archive_path=DEST/'007-candidate-query-traces.zip'
with zipfile.ZipFile(archive_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
 def put(name,value,source,ndjson=False):
  raw=b''.join(encode(row) for row in value) if ndjson else encode(value)
  safe(raw);info=zipfile.ZipInfo(name,date_time=(2026,10,12,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;archive.writestr(info,raw)
  manifest['members'].append({'member':name,'source_file':source.name,'source_sha256':sha(source.read_bytes()),'published_sha256':sha(raw),'published_bytes':len(raw)})
 for tag in ['eager-control-1','candidate-control-1','candidate-instrumented-1','heldout-c4-eager-control-1','heldout-c4-candidate-control-1','heldout-c4-candidate-instrumented-1','pilot-candidate-control-1','pilot-candidate-instrumented-1']:
  folder=ROOT/'runs'/tag;summary=read(folder/'summary.json');assert summary['status']=='completed' and summary['exit_code']==0 and not summary['forced_shutdown'] and summary['immutable_index_verified']
  source=folder/'resources.jsonl';put(tag+'/resources.jsonl',[select(row,RESOURCE_KEYS) for row in rows(source)],source,True)
  source=folder/'summary.json';boundaries={'lifecycle':select(summary,['status','exit_code','forced_shutdown','immutable_index_verified','binary_sha256','cases_sha256','cpu_max','memory_max','cache_condition','index_split_hashes_before','index_split_hashes_after']),'boundaries':{name:select(point,RESOURCE_KEYS) for name,point in summary['boundaries'].items()},'batches':[{'case':batch['case'],'repetitions':batch['repetitions'],'before':select(batch['before'],RESOURCE_KEYS),'after':select(batch['after'],RESOURCE_KEYS),'stage_before':batch['stage_before'],'stage_after':batch['stage_after'],'oracle_status':batch['oracle_status']} for batch in summary['batches']]};put(tag+'/boundaries.json',boundaries,source)
  source=folder/'requests.jsonl';requests=rows(source);public=[];audits=[]
  for request in requests:
   public.append(select(request,['case','status','start_monotonic_ns','end_monotonic_ns','wall_seconds','request_body_bytes','response_body_bytes','response_file']))
   response_path=folder/request['response_file'];response=read(response_path);case=case_map[request['case']];actual=[[int(hit['record_id']),hit['score']] for hit in response['hits']]
   assert request['status']==200 and response['num_hits']==case['num_hits']
   assert [hit[0] for hit in actual]==[hit[0] for hit in case['expected_hits']]
   assert all(abs(hit[1]-expected[1])<=1e-6 for hit,expected in zip(actual,case['expected_hits']))
   audits.append({'case':request['case'],'response_file':request['response_file'],'raw_response_sha256':sha(response_path.read_bytes()),'num_hits':response['num_hits'],'ordered_id_scores':actual,'oracle_status':'passed'})
  assert len(requests)==sum(b['repetitions'] for b in summary['batches'])+2;put(tag+'/requests.jsonl',public,source,True);put(tag+'/response-audits.jsonl',audits,source,True)
  source=folder/'stage-cpu.jsonl'
  if source.exists():
   stages=rows(source)
   assert all(set(row)<={'monotonic_ns','process_cpu_ns','thread_count_total','cpu_ns','work','retained_capacity_bytes','peak_retained_capacity_bytes'} for row in stages)
   assert max(row['thread_count_total'] for row in stages)<4096
   put(tag+'/stage-cpu.jsonl',stages,source,True)
 raw=safe(encode(manifest));info=zipfile.ZipInfo('manifest.json',date_time=(2026,10,12,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;archive.writestr(info,raw)
with zipfile.ZipFile(archive_path) as archive:
 assert archive.testzip() is None
 for member in manifest['members']:assert sha(archive.read(member['member']))==member['published_sha256']
metadata={'file':archive_path.name,'bytes':archive_path.stat().st_size,'sha256':sha(archive_path.read_bytes()),'sanitized_members':len(manifest['members']),'definition':manifest['definition']}
(DEST/'007-candidate-query-traces.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(json.dumps(metadata))
