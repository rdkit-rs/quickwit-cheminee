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

import json,os,pathlib,time,threading
HZ=os.sysconf('SC_CLK_TCK')
def process_sample(pid):
 root=pathlib.Path('/proc')/str(pid)
 rest=(root/'stat').read_text().rsplit(')',1)[1].split()
 sample={'monotonic_ns':time.monotonic_ns(),'pid':pid,'cpu_core_seconds':(int(rest[11])+int(rest[12]))/HZ,'threads':int(rest[17])}
 for file in ['smaps_rollup','io']:
  try:
   for line in (root/file).read_text().splitlines():
    if ':' not in line:continue
    key,value=line.split(':',1);part=value.strip().split()
    if not part or not part[0].isdigit():continue
    sample[key]=int(part[0])*(1024 if len(part)>1 and part[1]=='kB' else 1)
  except FileNotFoundError:pass
 try:
  maps=(root/'maps').read_text().splitlines()
  sample['mmap_count']=len(maps)
  sample['file_mmap_count']=sum('/' in m for m in maps)
  sample['unique_mapped_files']=len(set(m.split(maxsplit=5)[5] for m in maps if len(m.split(maxsplit=5))==6 and '/' in m))
  sample['fd_count']=len(list((root/'fd').iterdir()))
 except FileNotFoundError:pass
 return sample
class Sampler:
 def __init__(self,pid,path):self.pid=pid;self.path=path;self.stop_event=threading.Event();self.thread=threading.Thread(target=self.run,daemon=True)
 def start(self):self.thread.start()
 def run(self):
  with self.path.open('w') as f:
   while not self.stop_event.is_set():
    try:f.write(json.dumps(process_sample(self.pid))+'\n');f.flush()
    except (FileNotFoundError,ProcessLookupError):break
    self.stop_event.wait(1)
 def stop(self):self.stop_event.set();self.thread.join()
def files_snapshot(root):
 rows=[]
 for base,dirs,files in os.walk(root):
  for name in files:
   path=pathlib.Path(base)/name
   try:s=path.stat()
   except FileNotFoundError:continue
   rows.append({'path':str(path.relative_to(root)),'logical_bytes':s.st_size,'allocated_bytes':s.st_blocks*512,'inode':s.st_ino})
 return {'files':rows,'file_count':len(rows),'logical_bytes':sum(x['logical_bytes'] for x in rows),'allocated_bytes':sum(x['allocated_bytes'] for x in rows)}
