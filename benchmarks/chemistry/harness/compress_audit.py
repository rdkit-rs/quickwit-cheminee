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
import gzip,hashlib,json,pathlib,shutil,sys
run=pathlib.Path(os.environ['STUDY_ROOT'])/'runs'/sys.argv[1]
source=run/'stored-audit.ndjson';target=run/'stored-audit.ndjson.gz'
assert not target.is_file()
original=hashlib.file_digest(source.open('rb'),'sha256').hexdigest()
with source.open('rb') as incoming,gzip.open(target,'wb',compresslevel=1) as outgoing:shutil.copyfileobj(incoming,outgoing)
with gzip.open(target,'rb') as incoming:restored=hashlib.file_digest(incoming,'sha256').hexdigest()
assert original==restored
(run/'stored-audit-compression.json').write_text(json.dumps({'original_sha256':original,'uncompressed_bytes':source.stat().st_size,'compressed_sha256':hashlib.file_digest(target.open('rb'),'sha256').hexdigest(),'compressed_bytes':target.stat().st_size,'lossless_verified':True},indent=2))
source.unlink()
