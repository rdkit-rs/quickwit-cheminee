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
import csv,gzip,hashlib,json,pathlib,collections
root=pathlib.Path(os.environ['STUDY_ROOT'])/'data'
records=[]
counts={}
for name in ['train','test','test_scaffolds']:
 path=root/'molsets/moses/dataset/data'/f'{name}.csv.gz'
 with gzip.open(path,'rt') as f:
  for i,row in enumerate(csv.DictReader(f),1):
   smiles=row['SMILES']
   records.append((hashlib.sha256(b'tantivy-rdkit-compression-v1\0'+smiles.encode()).digest(),name,i,smiles))
  counts[name]=i
records.sort()
sample=records[:100000]
assert len(set(x[3] for x in records))==1936962
with (root/'raw-100k.ndjson').open('w') as f:
 for record_id,(_,source,row,smiles) in enumerate(sample,1):
  doc={'smiles':smiles,'extra_data':{'record_id':record_id,'catalog':'moses','source_set':source,'source_row':row,'supplier':f'supplier_{record_id%10}','assay_batch':record_id%20,'available':record_id%5!=0}}
  f.write(json.dumps(doc,separators=(',',':'))+'\n')
manifest={'source_counts':counts,'sample_counts':dict(collections.Counter(x[1] for x in sample)), 'sha256':hashlib.file_digest((root/'raw-100k.ndjson').open('rb'),'sha256').hexdigest(), 'bytes':(root/'raw-100k.ndjson').stat().st_size, 'metadata_reconstruction':'Provisional: metadata values not fully specified in published study. Does not claim prior byte hash.'}
(root/'corpus-manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
