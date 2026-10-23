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

"""Capacity admission; thresholds are provisional, not measured sizing claims."""
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path('.e2e/evidence')
root.mkdir(parents=True, exist_ok=True)
free = shutil.disk_usage('.').free
memory = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
info = json.loads(subprocess.check_output(['docker', 'info', '--format', '{{json .}}']))
result = {'free_bytes': free, 'memory_bytes': memory, 'cpus': os.cpu_count(),
          'docker_driver': info['Driver'], 'docker_root': info['DockerRootDir'],
          'required_free_bytes': 20 * 1024**3, 'required_memory_bytes': 10 * 1024**3,
          'budget': '6 GiB kind/containerd + 2 images + 1 corpus + 3 generations + 2 backup/restore + 2 WAL/cache + 4 reserve',
          'native_build': False}
(root / 'admission.json').write_text(json.dumps(result, indent=2))
if free < result['required_free_bytes'] or memory < result['required_memory_bytes']:
    raise SystemExit('Standard runner lacks provisional disk/RAM admission; no paid upgrade or deletion fallback')
