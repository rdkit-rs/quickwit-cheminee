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

"""Collect diagnostics without cleanup/retry masking the original failure."""
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path('.e2e/evidence')
root.mkdir(parents=True, exist_ok=True)
os.environ['KUBECONFIG'] = str(Path('.e2e/kubeconfig').resolve())


def collect(name, args):
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        (root / name).write_bytes(result.stdout[-2_000_000:])
    except (OSError, subprocess.TimeoutExpired) as error:
        (root / name).write_text(repr(error))


collect('docker-images.txt', ['docker', 'image', 'ls', '--digests', '--no-trunc'])
collect('nodes.json', ['kubectl', 'get', 'nodes', '-o', 'json', '--request-timeout=10s'])
collect('pods.json', ['kubectl', 'get', 'pods', '-o', 'json', '--request-timeout=10s'])
collect('events.txt', ['kubectl', 'get', 'events', '--request-timeout=10s'])
for name in ('seaweed-source', 'seaweed-restored', 'cheminee-source-a', 'cheminee-source-b', 'cheminee-restored'):
    collect(name + '-logs.txt', ['kubectl', 'logs', name, '--tail=500', '--request-timeout=10s'])
collect('kind-container.log', ['docker', 'logs', '--tail=500', 'cheminee-e2e-control-plane'])
(root / 'final-capacity.json').write_text(json.dumps({'disk': dict(zip(('total', 'used', 'free'), shutil.disk_usage('.')))}))
if not (root / 'result.json').exists():
    (root / 'result.json').write_text(json.dumps({'status': 'not_run', 'reason': 'A prerequisite step failed; inspect workflow and admission/artifact evidence.'}))
