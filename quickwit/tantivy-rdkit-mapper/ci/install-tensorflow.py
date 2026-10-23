# Copyright 2021-Present Datadog, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http:#www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Install checksum-pinned TensorFlow C libraries from the publisher's CPU wheel."""
import hashlib
import json
import pathlib
import shutil
import sys
import tempfile
import urllib.request
import zipfile

root = pathlib.Path(sys.argv[1]).resolve()
metadata = json.load(urllib.request.urlopen("https://pypi.org/pypi/tensorflow-cpu/2.15.1/json"))
wheel = next(item for item in metadata["urls"] if "cp311-cp311-manylinux_2_17_x86_64" in item["filename"])
expected = "54660c074d7241a503e81edfd9f5ef5af88f64051b72e2945f26318c790f2d26"
if wheel["digests"]["sha256"] != expected:
    raise RuntimeError("publisher TensorFlow wheel differs from pinned checksum")
with tempfile.TemporaryDirectory() as temporary:
    archive = pathlib.Path(temporary) / "tensorflow.whl"
    urllib.request.urlretrieve(wheel["url"], archive)
    with archive.open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != expected:
            raise RuntimeError("TensorFlow download checksum mismatch")
    library = root / "lib"
    (library / "pkgconfig").mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for name in ["libtensorflow_cc.so.2", "libtensorflow_framework.so.2"]:
            with package.open("tensorflow/" + name) as source, (library / name).open("wb") as target:
                shutil.copyfileobj(source, target)
    for name, target in [("libtensorflow.so", "libtensorflow_cc.so.2"), ("libtensorflow_framework.so", "libtensorflow_framework.so.2")]:
        link = library / name
        if link.is_symlink():
            link.unlink()
        link.symlink_to(target)
    (library / "pkgconfig/tensorflow.pc").write_text(
        "Name: TensorFlow\nDescription: Pinned TensorFlow C API\nVersion: 2.15.1\n"
        f"Libs: -L{library} -ltensorflow -ltensorflow_framework\n"
    )
print(f"TensorFlow CPU 2.15.1 installed in {root}; wheel SHA-256 {expected}")
