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
import hashlib,json,pathlib,re,zipfile
ROOT=pathlib.Path(os.environ['STUDY_ROOT'])/'runs'
OUT=pathlib.Path(os.environ['STUDY_OUTPUT'])
DEST=pathlib.Path(os.environ['EVIDENCE_OUTPUT'])/'005-counter-traces.zip'
DATA=json.loads((OUT/'enriched-metrics.json').read_text())
RESOURCE_KEYS=['monotonic_ns','cpu_core_seconds','threads','Rss','Pss','Pss_Dirty','Pss_Anon','Pss_File','Pss_Shmem','Shared_Clean','Shared_Dirty','Private_Clean','Private_Dirty','Referenced','Anonymous','KSM','LazyFree','AnonHugePages','ShmemPmdMapped','FilePmdMapped','Shared_Hugetlb','Private_Hugetlb','Swap','SwapPss','Locked','rchar','wchar','syscr','syscw','read_bytes','write_bytes','cancelled_write_bytes','mmap_count','file_mmap_count','unique_mapped_files','fd_count']
SPLIT_KEYS=['split_id','split_state','num_docs','uncompressed_docs_size_in_bytes','create_timestamp','update_timestamp','publish_timestamp','footer_offsets','maturity']
def read(path):return json.loads(path.read_text())
def select(row,keys):return {key:row[key] for key in keys if key in row}
def digest(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return (json.dumps(value,separators=(',',':'),sort_keys=True)+'\n').encode()
def ndjson(values):return b''.join(encode(value) for value in values)
def rows(path):return (json.loads(line) for line in path.read_text().splitlines())
manifest={'schema_version':1,'experiment':'005','definition':'Sanitized counter traces. Numeric counters/timestamps are unchanged. Process IDs, memory addresses, local paths, commands, service logs and molecule payloads are omitted. Original-source SHA256 binds each derivative to retained local evidence. Full readback documents are not included.','members':[]}
manifest['exclusions']=read(OUT/'exclusions.json')
manifest['runs']=[select(r,['tag','size','batch_size','concurrency','cpu_hint','commit_seconds','variant','binary_sha256','exclusion','effective_inputs']) for r in DATA['runs']]
assert sum(r['size']==100000 for r in DATA['runs'])==12
with zipfile.ZipFile(DEST,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
 def put(name,raw,source=None):
  assert not re.search(rb'/workspace/|/tmp/|libfile_|download_url|Authorization|Bearer |api[_-]?key|"pid"|"address"',raw,re.I),name
  entry=zipfile.ZipInfo(name,date_time=(2026,10,12,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16
  archive.writestr(entry,raw)
  if source is not None:manifest['members'].append({'member':name,'source_file':source.name,'source_sha256':hashlib.file_digest(source.open('rb'),'sha256').hexdigest(),'published_sha256':digest(raw),'published_bytes':len(raw)})
 for run in DATA['runs']:
  tag=run['tag'];assert re.fullmatch(r'knobs-[a-z0-9-]+',tag);folder=ROOT/tag
  source=folder/'resources.jsonl';put(tag+'/resources.jsonl',ndjson(select(row,RESOURCE_KEYS) for row in rows(source)),source)
  source=folder/'summary.json';summary=read(source);boundaries={}
  for name,phase in summary['phases'].items():
   boundaries[name]=select(phase,RESOURCE_KEYS);boundaries[name]['cgroup']=phase['cgroup']
  put(tag+'/boundaries.json',encode(boundaries),source)
  source=folder/'requests.jsonl';requests=[]
  for row in rows(source):
   assert row['status']==200 and row['response']['num_ingested_docs']==row['count'] and not row['response'].get('num_rejected_docs',0) and not row['response'].get('parse_failures',[])
   requests.append(select(row,['first_id','count','status','request_body_bytes','response_body_bytes','start_monotonic_ns','end_monotonic_ns','response']))
  put(tag+'/requests.jsonl',ndjson(requests),source)
  source=folder/'stage-cpu.jsonl'
  if source.is_file():
   for row in rows(source):assert set(row)=={'monotonic_ns','thread_count_total','cpu_ns'}
   put(tag+'/stage-cpu.jsonl',source.read_bytes(),source)
  source=folder/'lifecycle-splits.jsonl';put(tag+'/lifecycle-splits.jsonl',ndjson({'monotonic_ns':row['monotonic_ns'],'splits':[select(split,SPLIT_KEYS) for split in row['splits']['splits']]} for row in rows(source)),source)
  for boundary in ['searchable','lifecycle']:
   source=folder/f'splits-{boundary}.json';put(tag+'/'+source.name,encode({'splits':[select(split,SPLIT_KEYS) for split in read(source)['splits']]}),source)
  for name in ['stored-audit.json','stored-audit-compression.json','disk-preflight.json']:
   source=folder/name
   if source.is_file():
    value=read(source);assert not value.get('examples',[]);put(tag+'/'+name,encode(value),source)
 put('manifest.json',encode(manifest))
with zipfile.ZipFile(DEST) as archive:
 assert archive.testzip() is None
 for item in manifest['members']:assert digest(archive.read(item['member']))==item['published_sha256']
metadata={'file':DEST.name,'sha256':hashlib.file_digest(DEST.open('rb'),'sha256').hexdigest(),'bytes':DEST.stat().st_size,'sanitized_members':len(manifest['members']),'definition':manifest['definition']}
(DEST.parent/'005-counter-traces.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(json.dumps(metadata,indent=2))
