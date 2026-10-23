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

"""Verify exported candidate bytes before Docker load; no native build."""
import json
from pathlib import Path
import subprocess
import sys

source = Path('.e2e/source/distribution/cheminee-local').resolve()
sys.path.insert(0, str(source))
from pilot_provenance import digest
from finalize_pilot import verify_acceptance, verify_archive, verify_gem
from pilot_provenance import verify_image, verify_pair

root = Path('.e2e/candidate')
manifest = json.loads((root / 'pilot-manifest.json').read_text())
expected = json.loads(Path('distribution/cheminee-e2e/candidate.json').read_text())
if manifest['source_commit'] != expected['source_commit']:
    raise ValueError('candidate commit mismatch')
if digest(root / 'cheminee-image.tar') != expected['image_archive_sha256'] or digest(root / 'quickwit-cheminee.gem') != expected['gem_sha256']:
    raise ValueError('image/gem bytes differ from verified handoff')
for name, entry in manifest['files'].items():
    if Path(name).name != name or (root / name).is_symlink():
        raise ValueError('unsafe manifest file')
    if (root / name).stat().st_size != entry['bytes'] or digest(root / name) != entry['sha256']:
        raise ValueError('candidate bytes mismatch: ' + name)
runtime = json.loads((root / 'runtime-manifest.json').read_text())
sdk = json.loads((root / 'sdk-provenance.json').read_text())
image = json.loads((root / 'image-inspect.json').read_text())[0]
if image['Id'] != expected['image_config_digest']:
    raise ValueError('image config differs from verified handoff')
acceptance = json.loads((root / 'acceptance.json').read_text())
verify_pair(runtime, sdk, root / 'server-openapi.json', root / 'sdk-openapi.json')
verify_image(image, runtime)
verify_acceptance(acceptance, image, runtime, root)
verify_archive(root / 'cheminee-image.tar', image['Id'])
verify_gem(root / 'quickwit-cheminee.gem', sdk, root / 'sdk-openapi.json')
if acceptance['ruby_sdk']['gem_sha256'] != digest(root / 'quickwit-cheminee.gem'):
    raise ValueError('gem not exercised by pilot')
Path('.e2e/evidence/pilot-manifest.json').write_text(json.dumps(manifest, indent=2))
