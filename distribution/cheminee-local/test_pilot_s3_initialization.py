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

"""Small fixture/acceptance regressions; these do not execute or qualify an image."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from pilot_provenance import digest
from s3_initialization_smoke import (ACCESS_KEY, BINARY_PATH, CA_PATH, FIXTURE_PATH,
                                     MAX_LOG_BYTES, TRUSTSTORE_PANIC, create_arguments,
                                     run_probe, s3_fixture, validate_probe)


class S3InitializationTests(unittest.TestCase):
    def setUp(self):
        self.runtime = {"runtime_binary_sha256": "a" * 64, "ca_bundle": {"sha256": "b" * 64}}
        self.path = "/cheminee-smoke/test-nonce/manifest.json"
        self.marker = "controlled-test-nonce"
        self.hash_lines = f"{'a' * 64}  {BINARY_PATH}\n{'b' * 64}  {CA_PATH}\n"
        self.positive_log = self.hash_lines + f"command failed: AccessDenied: {self.marker}\n"
        self.negative_log = self.hash_lines + f"thread 'main' panicked at source.rs:163\n{TRUSTSTORE_PANIC}\n"
        self.observation = {"status": "failed", "running": False, "oom_killed": False,
                            "restart_count": 0, "log_truncated": False, "exit_code": 1,
                            "requests": [{"method": method, "path": self.path,
                                          "signed_with_synthetic_key": True, "status": status}
                                         for method, status in (("HEAD", 200), ("GET", 403))]}

    def validate(self, observation, log=None, negative=False):
        validate_probe(observation, log or self.positive_log, self.runtime,
                       self.path, self.marker, negative)

    def test_positive_requires_controlled_error_from_the_packaged_image(self):
        self.validate(self.observation)
        self.assertEqual("passed", self.observation["status"])
        self.assertTrue(self.observation["request_observed"])
        self.assertTrue(self.observation["controlled_s3_error_observed"])
        self.assertEqual(2, self.observation["request_count"])

    def test_missing_or_changed_actual_image_hashes_fail(self):
        for log in (self.positive_log.replace("b" * 64, "c" * 64),
                    self.positive_log.replace("a" * 64, "c" * 64),
                    self.positive_log + self.hash_lines, "AccessDenied: " + self.marker):
            with self.subTest(log=log), self.assertRaisesRegex(ValueError, "image bytes differ"):
                self.validate(copy.deepcopy(self.observation), log)

    def test_generic_error_success_panic_or_missing_s3_reply_never_pass(self):
        cases = [(self.positive_log.replace(self.marker, "another-run"), 1),
                 (self.positive_log.replace("AccessDenied", "network failure"), 1),
                 (self.positive_log, 0), (self.positive_log, 101),
                 (self.positive_log + "thread 'worker' panicked at source.rs:1", 1),
                 (self.positive_log + "no native root CA certificates found!", 1)]
        for log, exit_code in cases:
            result = copy.deepcopy(self.observation)
            result["exit_code"] = exit_code
            with self.subTest(log=log, exit_code=exit_code), self.assertRaises(ValueError):
                self.validate(result, log)

    def test_endpoint_request_sequence_and_synthetic_identity_are_required(self):
        for key, value in (("method", "PUT"), ("path", "/wrong-object"),
                           ("signed_with_synthetic_key", False), ("status", 200)):
            result = copy.deepcopy(self.observation)
            result["requests"][1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(result)
        for requests in ([], self.observation["requests"][:1], self.observation["requests"] * 2):
            result = dict(self.observation, requests=requests)
            with self.subTest(requests=requests), self.assertRaises(ValueError):
                self.validate(result)

    def test_running_oom_restarted_or_truncated_probes_fail(self):
        for key, value in (("running", True), ("oom_killed", True),
                           ("restart_count", 1), ("log_truncated", True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(dict(self.observation, **{key: value}))

    def test_negative_requires_exact_root_panic_and_zero_requests(self):
        negative = dict(self.observation, exit_code=101, requests=[])
        self.validate(negative, self.negative_log, negative=True)
        self.assertEqual("passed", negative["status"])
        self.assertTrue(negative["missing_roots_rejected"])
        self.assertEqual(0, negative["request_count"])
        for log, exit_code, requests in ((self.hash_lines + "unrelated panic", 101, []),
                                         (self.negative_log, 1, []),
                                         (self.negative_log, 101, self.observation["requests"])):
            result = dict(self.observation, exit_code=exit_code, requests=requests)
            with self.subTest(exit_code=exit_code, requests=requests), self.assertRaises(ValueError):
                self.validate(result, log, negative=True)

    def test_fixture_serves_head_then_controlled_s3_error_and_records_no_headers(self):
        http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        headers = {"Authorization": f"AWS4-HMAC-SHA256 Credential={ACCESS_KEY}/20261023/us-east-1/s3/aws4_request, "
                   f"SignedHeaders=host;x-amz-date, Signature={'c' * 64}"}
        with s3_fixture("127.0.0.1", self.path, self.marker) as (endpoint, records):
            with http.open(urllib.request.Request(endpoint + self.path, method="HEAD", headers=headers), timeout=2) as response:
                self.assertEqual(200, response.status)
                self.assertEqual(b"", response.read())
            with self.assertRaises(urllib.error.HTTPError) as caught:
                http.open(urllib.request.Request(endpoint + self.path, headers=headers), timeout=2)
            self.assertEqual(403, caught.exception.code)
            body = caught.exception.read().decode()
            self.assertIn("<Code>AccessDenied</Code>", body)
            self.assertIn(self.marker, body)
        self.assertEqual(self.observation["requests"], records)

    def test_fixture_rejects_unexpected_path_or_credentials(self):
        http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with s3_fixture("127.0.0.1", self.path, self.marker) as (endpoint, records):
            for path in (self.path, "/another-object"):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    http.open(endpoint + path, timeout=2)
                self.assertEqual(400, caught.exception.code)
                caught.exception.close()
        self.assertTrue(all(record["signed_with_synthetic_key"] is False for record in records))

    def test_positive_keeps_image_roots_while_negative_overrides_both_paths(self):
        positive = create_arguments("probe", "sha256:image", "internal-network", Path("/fixture"), False)
        negative = create_arguments("probe", "sha256:image", "internal-network", Path("/fixture"), True)
        self.assertFalse(any(argument.startswith("--env=SSL_CERT_") for argument in positive))
        self.assertIn(f"--env=SSL_CERT_FILE={FIXTURE_PATH}/empty.pem", negative)
        self.assertIn(f"--env=SSL_CERT_DIR={FIXTURE_PATH}/empty-roots", negative)
        self.assertIn("--env=AWS_EC2_METADATA_DISABLED=true", positive)
        self.assertIn("--env=AWS_SHARED_CREDENTIALS_FILE=/dev/null", positive)
        self.assertIn("--env=HTTPS_PROXY=", positive)
        self.assertIn("--read-only", positive)
        self.assertIn("--memory=2g", positive)
        self.assertEqual(1, positive.count("--mount"))
        self.assertIn(f"exec {BINARY_PATH} tool local-search", positive[-1])

    def test_wait_timeout_retains_bounded_image_log_and_failed_receipt(self):
        image = "sha256:" + "c" * 64
        observation, created, calls = {}, [], []

        def fake_docker(arguments, timeout=20):
            calls.append((arguments, timeout))
            if arguments[0] == "wait":
                raise subprocess.TimeoutExpired(["docker", "wait"], timeout)
            if arguments[0] == "inspect":
                return json.dumps([{"Image": image, "RestartCount": 0,
                                    "State": {"Running": True, "OOMKilled": False}}])
            if arguments[0] == "logs":
                return "x" * (MAX_LOG_BYTES + 1)
            return "probe"

        with tempfile.TemporaryDirectory() as temporary, patch("s3_initialization_smoke.docker", side_effect=fake_docker):
            output = Path(temporary)
            with self.assertRaises(subprocess.TimeoutExpired):
                run_probe("probe", image, "network", output, output, [], observation, created)
            self.assertEqual(MAX_LOG_BYTES, (output / "positive.log").stat().st_size)
            self.assertEqual(digest(output / "positive.log"), observation["log_sha256"])
        self.assertEqual(["probe"], created)
        self.assertEqual("failed", observation["status"])
        self.assertTrue(observation["running"])
        self.assertTrue(observation["log_truncated"])
        self.assertIn((["wait", "probe"], 45), calls)


if __name__ == "__main__":
    unittest.main()
