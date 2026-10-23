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

"""Exercise CA bundle packaging with tiny fixtures, without Docker or a network."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from prepare_runtime import CA_BUNDLE, copy_runtime_ca_bundle

# Public ISRG Root X2 from the distro's Mozilla CA package, not host test trust.
ROOT_CERTIFICATE = b"""-----BEGIN CERTIFICATE-----
MIICGzCCAaGgAwIBAgIQQdKd0XLq7qeAwSxs6S+HUjAKBggqhkjOPQQDAzBPMQsw
CQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJuZXQgU2VjdXJpdHkgUmVzZWFyY2gg
R3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBYMjAeFw0yMDA5MDQwMDAwMDBaFw00
MDA5MTcxNjAwMDBaME8xCzAJBgNVBAYTAlVTMSkwJwYDVQQKEyBJbnRlcm5ldCBT
ZWN1cml0eSBSZXNlYXJjaCBHcm91cDEVMBMGA1UEAxMMSVNSRyBSb290IFgyMHYw
EAYHKoZIzj0CAQYFK4EEACIDYgAEzZvVn4CDCuwJSvMWSj5cz3es3mcFDR0HttwW
+1qLFNvicWDEukWVEYmO6gbf9yoWHKS5xcUy4APgHoIYOIvXRdgKam7mAHf7AlF9
ItgKbppbd9/w+kHsOdx1ymgHDB/qo0IwQDAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0T
AQH/BAUwAwEB/zAdBgNVHQ4EFgQUfEKWrt5LSDv6kviejM9ti6lyN5UwCgYIKoZI
zj0EAwMDaAAwZQIwe3lORlCEwkSHRhtFcP9Ymd70/aTSVaYgLXTWNLxBo1BfASdW
tL4ndQavEi51mI38AjEAi/V3bNTIZargCyzuFJ0nN6T5U6VR5CmD1/iQMVtCnwr1
/q4AaOeMSQ+2b1tbFfLn
-----END CERTIFICATE-----
"""
# Test-only leaf certificate; no private key or runtime trust addition.
LEAF_CERTIFICATE = b"""-----BEGIN CERTIFICATE-----
MIIBmTCCAT6gAwIBAgIUS0noS06Hoiab5kcDoj5T+3OosuMwCgYIKoZIzj0EAwIw
GzEZMBcGA1UEAwwQVGVzdC1vbmx5IG5vbi1DQTAeFw0yNjEwMjMwNjA4MzRaFw0y
NjEwMjQwNjA4MzRaMBsxGTAXBgNVBAMMEFRlc3Qtb25seSBub24tQ0EwWTATBgcq
hkjOPQIBBggqhkjOPQMBBwNCAAQjR36wPVBccnyeLTIjneTFrTnVeMdTDXqfLJxn
wgDdv9o+7IHFiTXdGOQpdPvCSIjDvbU/OwYOUL2W09rVT7KEo2AwXjAdBgNVHQ4E
FgQU3GfEsVH/l8UmOKsgzA22LYC7h4IwHwYDVR0jBBgwFoAU3GfEsVH/l8UmOKsg
zA22LYC7h4IwDAYDVR0TAQH/BAIwADAOBgNVHQ8BAf8EBAMCB4AwCgYIKoZIzj0E
AwIDSQAwRgIhAK1M/oNo/AyOXoAhhoAjWfOWBRFua5cwqxt08be2GkGeAiEAlUVW
iqlDSNtyzn5TU6OjeDphtl0M4r+DwJOvYNnj6Q8=
-----END CERTIFICATE-----
"""


class RuntimeCABundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.filesystem = Path(self.temporary.name) / "builder"
        self.source = self.filesystem / CA_BUNDLE.relative_to("/")
        self.source.parent.mkdir(parents=True)
        self.root = Path(self.temporary.name) / "runtime"
        self.root.mkdir()
        self.target = self.root / CA_BUNDLE.relative_to("/")

    def test_missing_bundle_fails_without_loading_host_roots(self):
        with self.assertRaisesRegex(ValueError, "regular contained file"):
            copy_runtime_ca_bundle(self.root, self.filesystem)
        self.assertEqual([], list(self.root.iterdir()))

    def test_empty_malformed_and_mixed_bundles_fail_before_copy(self):
        malformed = b"-----BEGIN CERTIFICATE-----\nYWJj\n-----END CERTIFICATE-----\n"
        for data in (b"", b"\n \n", b"not certificates", b"\xff", malformed,
                     ROOT_CERTIFICATE + malformed, ROOT_CERTIFICATE + b"trailing junk",
                     ROOT_CERTIFICATE.replace(b"-----END CERTIFICATE-----", b"")):
            with self.subTest(data=data[:30]):
                self.source.write_bytes(data)
                with self.assertRaises(ValueError):
                    copy_runtime_ca_bundle(self.root, self.filesystem)
                self.assertEqual([], list(self.root.iterdir()))

    def test_leaf_only_and_mixed_leaf_bundle_fail_before_copy(self):
        for data in (LEAF_CERTIFICATE, ROOT_CERTIFICATE + LEAF_CERTIFICATE):
            with self.subTest(leaf_only=data == LEAF_CERTIFICATE):
                self.source.write_bytes(data)
                with self.assertRaisesRegex(ValueError, "CA certificates only"):
                    copy_runtime_ca_bundle(self.root, self.filesystem)
                self.assertEqual([], list(self.root.iterdir()))

    def test_valid_bundle_preserves_bytes_hash_path_and_nonroot_readability(self):
        self.source.write_bytes(ROOT_CERTIFICATE)
        self.source.chmod(0o600)
        with patch.dict(os.environ, {"SSL_CERT_FILE": "/absent/other-trust.pem", "SSL_CERT_DIR": "/absent/roots"}):
            manifest = copy_runtime_ca_bundle(self.root, self.filesystem)
        self.assertEqual(ROOT_CERTIFICATE, self.target.read_bytes())
        self.assertEqual(0o644, self.target.stat().st_mode & 0o777)
        self.assertFalse(self.target.is_symlink())
        self.assertEqual({"path": str(CA_BUNDLE), "source": str(CA_BUNDLE),
                          "resolved_source": str(CA_BUNDLE),
                          "sha256": hashlib.sha256(ROOT_CERTIFICATE).hexdigest(),
                          "certificate_count": 1, "ca_count": 1}, manifest)

    def test_symlink_source_and_escaping_parent_fail(self):
        external = Path(self.temporary.name) / "external.crt"
        external.write_bytes(ROOT_CERTIFICATE)
        self.source.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "regular contained file"):
            copy_runtime_ca_bundle(self.root, self.filesystem)
        self.source.unlink()
        self.source.parent.rmdir()
        self.source.parent.symlink_to(external.parent, target_is_directory=True)
        external.rename(external.parent / CA_BUNDLE.name)
        with self.assertRaisesRegex(ValueError, "regular contained file"):
            copy_runtime_ca_bundle(self.root, self.filesystem)
        self.assertEqual([], list(self.root.iterdir()))

    def test_existing_destination_is_never_overwritten(self):
        self.source.write_bytes(ROOT_CERTIFICATE)
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b"retain")
        with self.assertRaisesRegex(ValueError, "already exists"):
            copy_runtime_ca_bundle(self.root, self.filesystem)
        self.assertEqual(b"retain", self.target.read_bytes())

    def test_destination_parent_cannot_escape_packaging_root(self):
        self.source.write_bytes(ROOT_CERTIFICATE)
        external = Path(self.temporary.name) / "outside"
        external.mkdir()
        (self.root / "etc").symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "escapes packaging root"):
            copy_runtime_ca_bundle(self.root, self.filesystem)
        self.assertEqual([], list(external.iterdir()))


if __name__ == "__main__":
    unittest.main()
