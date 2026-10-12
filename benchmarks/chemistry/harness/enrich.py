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

import os
import bisect,collections,json,pathlib,re,struct
ROOT=pathlib.Path(os.environ['STUDY_ROOT'])/'runs'
OUT=pathlib.Path(os.environ['STUDY_OUTPUT'])
def read(path):return json.loads(path.read_text())
def lines(path):return [json.loads(line) for line in path.read_text().splitlines()]
def interpolate(rows,time):
 timestamps=[r['monotonic_ns'] for r in rows];i=bisect.bisect_left(timestamps,time)
 if i==0:return rows[0]['cpu_core_seconds']
 if i==len(rows):return rows[-1]['cpu_core_seconds']
 a,b=rows[i-1],rows[i];weight=(time-a['monotonic_ns'])/(b['monotonic_ns']-a['monotonic_ns']);return a['cpu_core_seconds']+weight*(b['cpu_core_seconds']-a['cpu_core_seconds'])
def enrich(row):
 folder=ROOT/row['tag'];summary=read(folder/'summary.json');phases=summary['phases'];samples=lines(folder/'resources.jsonl')
 row['setup_controller_cpu_seconds']=summary['setup_controller_cpu_seconds']
 row['disk_preflight']=read(folder/'disk-preflight.json') if (folder/'disk-preflight.json').is_file() else None
 row['boundaries']={name:{k:p[k] for k in ['cpu_core_seconds','Rss','Pss','threads','mmap_count','file_mmap_count','unique_mapped_files','fd_count'] if k in p} for name,p in phases.items()}
 for name,start,end in [('acceptance','ingest_start','accepted'),('publication_tail','accepted','all_searchable'),('raw_to_searchable','ingest_start','all_searchable'),('background_lifecycle','all_searchable','lifecycle_observed')]:
  a,b=phases[start],phases[end];interval=row['intervals'][name]
  interval['process_io_delta']={key:b.get(key,0)-a.get(key,0) for key in ['rchar','wchar','read_bytes','write_bytes','syscr','syscw']}
  if 'cpu_attribution' in interval:
   snapshots=[s for s in lines(folder/'stage-cpu.jsonl') if a['monotonic_ns']<=s['monotonic_ns']<=b['monotonic_ns']]
   first,last=snapshots[0],snapshots[-1];cpu=interval['cpu_attribution'];process=interpolate(samples,last['monotonic_ns'])-interpolate(samples,first['monotonic_ns']);cpu['interpolated_process_cpu_same_window']=process;cpu['clock_reconciliation_residual_core_seconds']=process-cpu['attributed_core_seconds'];cpu['thread_records']=last['thread_count_total']
 requests=lines(folder/'requests.jsonl');duration=(max(r['end_monotonic_ns'] for r in requests)-min(r['start_monotonic_ns'] for r in requests))/1e9
 row['http_boundary']={'request_count':len(requests),'request_body_bytes':sum(r['request_body_bytes'] for r in requests),'response_body_bytes':sum(r['response_body_bytes'] for r in requests),'interval_seconds':duration,'body_bytes_per_second':sum(r['request_body_bytes'] for r in requests)/duration,'accepted_documents':sum(r['response']['num_ingested_docs'] for r in requests),'rejected_documents':sum(r['response'].get('num_rejected_docs',0) for r in requests),'definition':'First request start to last acknowledgement; includes chemistry/backpressure, not network capacity.'}
 last=samples[-1];boundary=phases['lifecycle_observed'];row['shutdown_observation']={'last_sample_seconds_after_lifecycle':(last['monotonic_ns']-boundary['monotonic_ns'])/1e9,'cpu_through_last_sample':last['cpu_core_seconds']-boundary['cpu_core_seconds'],'forced':summary['forced_shutdown'],'exit_code':summary['exit_code'],'limit':'Last live sample only; up to one second before exit, not an exact process-exit boundary.'}
 changes=[];previous=None
 for snap in lines(folder/'lifecycle-splits.jsonl'):
  splits=snap['splits']['splits'];states=dict(collections.Counter(s['split_state'] for s in splits))
  if states!=previous:
   changes.append({'seconds_after_searchable':(snap['monotonic_ns']-phases['all_searchable']['monotonic_ns'])/1e9,'states':states,'published_documents':sum(s['num_docs'] for s in splits if s['split_state']=='Published')});previous=states
 row['lifecycle_transitions']=changes
 inventory=[]
 for root in ['engine','indexes']:
  inventory += read(folder/f'files-{root}-lifecycle.json')['files']
 unique={x['inode']:x for x in inventory}
 row['deduplicated_lifecycle_files']={'unique_inodes':len(unique),'logical_bytes':sum(x['logical_bytes'] for x in unique.values()),'allocated_bytes':sum(x['allocated_bytes'] for x in unique.values()),'definition':'Same filesystem, deduplicated across node and index roots by retained inode inventory.'}
 row['merge_gc_metric_snapshots']={}
 for boundary in ['searchable','lifecycle']:
  content=(folder/f'metrics-{boundary}.txt').read_text();row['merge_gc_metric_snapshots'][boundary]=[line for line in content.splitlines() if not line.startswith('#') and re.search(r'merge|publish|upload|garbage|deleted|gc_',line)]
 row['split_internal_geometry']=[]
 for split in read(folder/'splits-lifecycle.json')['splits']:
  matches=list((folder/'indexes').rglob(split['split_id']+'.split'))
  if not matches:
   row['split_internal_geometry'].append({'state':split['split_state'],'num_docs':split['num_docs'],'file_present_after_shutdown':False});continue
  assert len(matches)==1
  path=matches[0]
  with path.open('rb') as handle:
   handle.seek(-4,2);hot=struct.unpack('<I',handle.read(4))[0];handle.seek(-8-hot,2);length=struct.unpack('<I',handle.read(4))[0];handle.seek(-8-hot-length,2);raw=handle.read(length)
   assert struct.unpack('<II',raw[:8])==(403881646,1)
   files=json.loads(raw[8:])['files'];location=files['meta.json'];handle.seek(location['start']);metadata=json.loads(handle.read(location['end']-location['start']))
  row['split_internal_geometry'].append({'state':split['split_state'],'num_docs':split['num_docs'],'file_present_after_shutdown':True,'file_bytes':path.stat().st_size,'hotcache_bytes':hot,'internal_file_count':len(files),'internal_segment_count':len(metadata['segments'])})
 row['stored_audit_compression']=read(folder/'stored-audit-compression.json') if (folder/'stored-audit-compression.json').is_file() else None
 return row
if __name__=='__main__':
 data=read(OUT/'metrics.json');data['stage_names']=read(pathlib.Path(__file__).with_name('stage-names.json'));data['runs']=[enrich(r) for r in data['runs']];(OUT/'enriched-metrics.json').write_text(json.dumps(data,indent=2)+'\n')
