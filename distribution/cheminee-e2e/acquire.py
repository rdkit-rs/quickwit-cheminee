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

"""Consume one exact successful pilot run; never dispatch or rebuild a candidate."""
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import zipfile


def safe_members(archive):
    names = archive.namelist()
    if len(names) != len(set(names)) or not names:
        raise ValueError('empty or duplicate artifact members')
    if sum(i.file_size for i in archive.infolist()) > 6 * 1024**3:
        raise ValueError('artifact exceeds 6 GiB allowance')
    for name in names:
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError('artifact must contain only flat files')
    return names


def api(path):
    req = urllib.request.Request('https://api.github.com/' + path, headers={
        'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def main():
    config = json.loads(Path('distribution/cheminee-e2e/candidate.json').read_text())
    repo, run_id, sha = config['repository'], config['run_id'], config['source_commit']
    prefix = f'repos/{repo}/actions/runs/{run_id}'
    # A bounded wait for the already-running pilot; never launches another build.
    deadline = time.monotonic() + 20 * 60
    while True:
        run = api(prefix)
        Path('.e2e/evidence/pilot-run.json').write_text(json.dumps(run, indent=2))
        if run['head_sha'] != sha or run['path'] != '.github/workflows/prepare-cheminee-pilot.yml':
            raise ValueError('wrong pilot source/workflow')
        if run['status'] == 'completed':
            break
        if time.monotonic() >= deadline:
            raise TimeoutError('pilot still pending; acceptance not run')
        time.sleep(30)
    if run['conclusion'] != 'success':
        raise ValueError('pilot failed; diagnostic artifacts are not qualified runtimes')
    artifacts = api(prefix + '/artifacts?per_page=100')['artifacts']
    matches = [a for a in artifacts if a['name'] == f'cheminee-pilot-{sha}' and not a['expired']]
    if len(matches) != 1:
        raise ValueError('exact accepted artifact missing or ambiguous')
    artifact = matches[0]
    if artifact['id'] != config['artifact_id'] or artifact['size_in_bytes'] != config['artifact_bytes']:
        raise ValueError('artifact identity/size differs from verified handoff')
    if artifact['size_in_bytes'] > 6 * 1024**3:
        raise ValueError('artifact too large')
    # gh follows GitHub's authenticated temporary download redirect. Token is job-scoped.
    import subprocess
    archive_path = Path('.e2e/pilot.zip')
    with archive_path.open('xb') as output:
        subprocess.run(['gh', 'api', f'repos/{repo}/actions/artifacts/{artifact["id"]}/zip'],
                       stdout=output, check=True, timeout=600)
    reported = artifact.get('digest')
    actual = 'sha256:' + hashlib.file_digest(archive_path.open('rb'), 'sha256').hexdigest()
    if not reported or reported != actual or actual != 'sha256:' + config['artifact_sha256']:
        raise ValueError('GitHub artifact archive digest missing or mismatched')
    destination = Path('.e2e/candidate')
    destination.mkdir()
    with zipfile.ZipFile(archive_path) as archive:
        for name in safe_members(archive):
            with archive.open(name) as source, (destination / name).open('xb') as output:
                import shutil
                shutil.copyfileobj(source, output)
    Path('.e2e/evidence/pilot-artifact.json').write_text(json.dumps(artifact, indent=2))


if __name__ == '__main__':
    main()
