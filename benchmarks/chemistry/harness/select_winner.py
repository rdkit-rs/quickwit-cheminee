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
import collections,json,pathlib,statistics
root=pathlib.Path(os.environ['STUDY_OUTPUT']);data=json.loads((root/'metrics.json').read_text());groups=collections.defaultdict(list)
for row in data['runs']:
 if row['size']!=100000 or row['variant']!='control':continue
 assert row['status']=='completed' and row['audit']['status']=='passed' and row['query_audit']['status']=='passed'
 groups[(row['cpu_hint'],row['commit_seconds'],row['batch_size'])].append(row)
assert len(groups)==5 and all(len(rows)==2 for rows in groups.values())
aggregates=[{'cpu_hint':key[0],'commit_seconds':key[1],'batch_size':key[2],'runs':[r['tag'] for r in rows],'mean_searchable_seconds':statistics.mean(r['intervals']['raw_to_searchable']['wall_seconds'] for r in rows),'mean_cpu_core_seconds':statistics.mean(r['intervals']['raw_to_searchable']['cpu_core_seconds'] for r in rows)} for key,rows in groups.items()]
aggregates.sort(key=lambda r:(r['mean_searchable_seconds'],r['mean_cpu_core_seconds']))
(root/'selection.json').write_text(json.dumps({'criterion':'Lowest mean raw-to-searchable wall time across two uninstrumented full-scale repetitions; CPU is tie breaker. Instrumented follow-up is not an independent holdout.','aggregates':aggregates,'selected':aggregates[0]},indent=2))
x=aggregates[0];print(x['cpu_hint'],x['commit_seconds'],x['batch_size'])
