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
import bisect,collections,hashlib,json,pathlib,statistics
ROOT=pathlib.Path(os.environ['STUDY_ROOT'])/'runs'
OUT=pathlib.Path(os.environ['STUDY_OUTPUT'])
def counters(text):return {k:int(v) for k,v in (line.split() for line in text.splitlines())}
def splits(path):
 if not path.is_file():return None
 x=json.loads(path.read_text());rows=x['splits'] if isinstance(x,dict) else x
 return dict(collections.Counter(r.get('split_state') for r in rows))
runs=[]
for folder in sorted(ROOT.glob('knobs-*')):
 if not (folder/'summary.json').is_file():continue
 s=json.loads((folder/'summary.json').read_text());rows=[json.loads(l) for l in (folder/'resources.jsonl').read_text().splitlines()]
 r={k:s[k] for k in ['tag','size','batch_size','concurrency','cpu_hint','commit_seconds','variant','binary_sha256','payload_body_bytes','setup_wall_seconds','startup_wall_seconds','status','forced_shutdown','exit_code']}
 r['exclusion']=(json.loads((OUT/'exclusions.json').read_text()) if (OUT/'exclusions.json').is_file() else {}).get(folder.name)
 r['effective_inputs']=json.loads((folder/'effective-inputs.json').read_text());r['intervals']={}
 for name,start,end in [('acceptance','ingest_start','accepted'),('publication_tail','accepted','all_searchable'),('raw_to_searchable','ingest_start','all_searchable'),('background_lifecycle','all_searchable','lifecycle_observed')]:
  a,b=s['phases'][start],s['phases'][end];wall=(b['monotonic_ns']-a['monotonic_ns'])/1e9;cpu=b['cpu_core_seconds']-a['cpu_core_seconds'];points=[a]+[q for q in rows if a['monotonic_ns']<=q['monotonic_ns']<=b['monotonic_ns']]+[b]
  ca,cb=counters(a['cgroup']['cpu.stat']),counters(b['cgroup']['cpu.stat'])
  r['intervals'][name]={'wall_seconds':wall,'cpu_core_seconds':cpu,'average_cores':cpu/wall,'quota_fraction':cpu/wall/4,'docs_per_second':s['size']/wall if name in ['acceptance','raw_to_searchable'] else None,'peak_sampled_rss_bytes':max(q['Rss'] for q in points),'peak_sampled_pss_bytes':max(q['Pss'] for q in points),'cgroup_cpu_delta':{k:cb[k]-ca[k] for k in ca},'memory_event_delta':{k:counters(b['cgroup']['memory.events'])[k]-v for k,v in counters(a['cgroup']['memory.events']).items()},'end_threads':b['threads'],'end_mmap_count':b['mmap_count'],'end_file_mmap_count':b['file_mmap_count']}
 stages=[json.loads(line) for line in (folder/'stage-cpu.jsonl').read_text().splitlines()] if (folder/'stage-cpu.jsonl').is_file() else []
 for name,start,end in [('acceptance','ingest_start','accepted'),('publication_tail','accepted','all_searchable'),('raw_to_searchable','ingest_start','all_searchable'),('background_lifecycle','all_searchable','lifecycle_observed')]:
  a,b=s['phases'][start],s['phases'][end];inside=[q for q in stages if a['monotonic_ns']<=q['monotonic_ns']<=b['monotonic_ns']]
  if len(inside)>1:
   f,l=inside[0],inside[-1];values={str(i):(y-x)/1e9 for i,(x,y) in enumerate(zip(f['cpu_ns'],l['cpu_ns'])) if x!=y}
   r['intervals'][name]['cpu_attribution']={'covered_wall_seconds':(l['monotonic_ns']-f['monotonic_ns'])/1e9,'stage_core_seconds':values,'attributed_core_seconds':sum(values.values()),'boundary_and_reconciliation_core_seconds':r['intervals'][name]['cpu_core_seconds']-sum(values.values())}
 # Nonoverlapping ~10s process CPU bins, retain time-series rather than only a mean.
 start=s['phases']['ingest_start'];end=s['phases']['all_searchable'];last=start;r['cpu_timeline']=[]
 for q in rows+[end]:
  if q['monotonic_ns']<=last['monotonic_ns'] or q['monotonic_ns']>end['monotonic_ns']:continue
  elapsed=(q['monotonic_ns']-last['monotonic_ns'])/1e9
  if elapsed>=10 or q is end:
   r['cpu_timeline'].append({'end_seconds':(q['monotonic_ns']-start['monotonic_ns'])/1e9,'wall_seconds':elapsed,'cpu_core_seconds':q['cpu_core_seconds']-last['cpu_core_seconds'],'rss_bytes':q['Rss'],'pss_bytes':q['Pss']});last=q
 r['splits_searchable']=splits(folder/'splits-searchable.json');r['splits_lifecycle']=splits(folder/'splits-lifecycle.json')
 r['audit']=json.loads((folder/'stored-audit.json').read_text()) if (folder/'stored-audit.json').is_file() else None
 r['query_audit']=json.loads((folder/'query-audit.json').read_text()) if (folder/'query-audit.json').is_file() else None
 r['files']={}
 for fn in ['files-searchable.json','files-engine-lifecycle.json','files-indexes-lifecycle.json']:
  x=json.loads((folder/fn).read_text());r['files'][fn]={k:v for k,v in x.items() if k!='files'}
 r['evidence_sha256']={f.name:hashlib.file_digest(f.open('rb'),'sha256').hexdigest() for f in folder.iterdir() if f.is_file() and f.suffix in ['.json','.jsonl','.txt','.log']}
 runs.append(r)
(OUT/'metrics.json').write_text(json.dumps({'schema_version':1,'runs':runs},indent=2)+'\n')
for r in runs:
 a=r['intervals']['acceptance'];b=r['intervals']['raw_to_searchable'];print(r['tag'],f"accept {a['wall_seconds']:.2f}s {a['average_cores']:.2f}cores searchable {b['wall_seconds']:.2f}s {b['cpu_core_seconds']:.2f}cpu {b['peak_sampled_rss_bytes']/2**20:.1f}MiB",r['splits_lifecycle'],'audit',r['audit']['status'] if r['audit'] else 'pending')
