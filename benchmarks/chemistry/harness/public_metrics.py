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
import copy,json,pathlib,re
OUT=pathlib.Path(os.environ['STUDY_OUTPUT'])
DEST=pathlib.Path(os.environ['EVIDENCE_OUTPUT'])/'005-tuning-metrics.json'
data=json.loads((OUT/'enriched-metrics.json').read_text())
full=[row for row in data['runs'] if row['size']==100000]
assert len(full)==12 and all(row['status']=='completed' and row['audit']['status']=='passed' and row['query_audit']['status']=='passed' for row in full)
assert max(row['intervals']['background_lifecycle']['wall_seconds'] for row in full)>=2580
public={'schema_version':2,'experiment':'005','scope':'Configuration-only Quickwit flat-schema runtime study, 100k full runs and 10k screens; local file storage. Query latencies in correctness audits are not query-performance measurements.','stage_names':data['stage_names'],'selection':json.loads((OUT/'selection.json').read_text()),'memory_ownership':{'stage_owned_allocations':None,'reason':'Not reprofiled for each configuration. RSS/PSS are shared process snapshots and peaks are not additive.'},'runs':[]}
for original in data['runs']:
 row=copy.deepcopy(original)
 if row['query_audit']:
  audit=row['query_audit'];row['query_audit']={'status':audit['status'],'queries':audit['queries'],'oracle_sha256':audit['oracle_sha256'],'checks':[{'name':q['name'],'expected_status':q['expected_status'],'actual_status':q['status'],'status_check':q['status_check']} for q in audit['results']]}
 public['runs'].append(row)
# Fields were explicitly selected by the aggregators; reject any overlooked local
# paths or addresses rather than trying to hide them with broad substitutions.
blob=json.dumps(public,sort_keys=True)
assert not re.search(r'/workspace/|/tmp/|libfile_|download_url|Authorization|Bearer |api[_-]?key|\"pid\"|\"address\"',blob,re.I)
for row in public['runs']:
 for interval in row['intervals'].values():
  if 'cpu_attribution' in interval:
   a=interval['cpu_attribution'];assert abs(sum(a['stage_core_seconds'].values())+a['boundary_and_reconciliation_core_seconds']-interval['cpu_core_seconds'])<1e-7
   assert abs(a['attributed_core_seconds']+a['clock_reconciliation_residual_core_seconds']-a['interpolated_process_cpu_same_window'])<1e-7
# One complete run per line matches the historical metric file convention.
head={k:v for k,v in public.items() if k!='runs'}
DEST.write_text(json.dumps(head)[:-1]+', "runs": [\n'+',\n'.join(json.dumps(r,sort_keys=True) for r in public['runs'])+'\n]}\n')
print('Wrote sanitized metrics:',DEST,'bytes',DEST.stat().st_size)
