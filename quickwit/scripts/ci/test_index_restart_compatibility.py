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
"""Negative controls for the REST index compatibility oracle and lifecycle."""
import copy
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import index_restart_compatibility as probe


DOCUMENTS = [{"record_id": 9007199254740993, "message": "first", "payload": "alpha"},
             {"record_id": 9007199254740994, "message": "second", "payload": "beta"},
             {"record_id": 9007199254740995, "message": "third", "payload": "gamma"}]


def response(documents=DOCUMENTS, total=None):
    return {"timed_out": False, "terminated_early": None,
            "_shards": {"total": 2, "successful": 2, "skipped": 0, "failed": 0},
            "hits": {"total": {"value": len(documents) if total is None else total, "relation": "eq"},
                     "hits": [{"_index": probe.INDEX_ID,
                               "_source": {**copy.deepcopy(document), "_source": copy.deepcopy(document)},
                               "sort": [document["record_id"]]}
                              for document in documents]}}


class OracleTests(unittest.TestCase):
    def test_complete_source_and_exact_u64_sort_pass(self):
        self.assertEqual(probe.verify_page(response(), DOCUMENTS, 3), [9007199254740995])

    def test_missing_duplicate_changed_extra_and_reordered_documents_fail(self):
        variants = [DOCUMENTS[:-1], [DOCUMENTS[0], DOCUMENTS[0], DOCUMENTS[2]],
                    [{**DOCUMENTS[0], "payload": "corrupted"}, *DOCUMENTS[1:]],
                    [*DOCUMENTS, DOCUMENTS[0]], list(reversed(DOCUMENTS)),
                    [{**DOCUMENTS[0], "extra": "unexpected"}, *DOCUMENTS[1:]],
                    [{"record_id": DOCUMENTS[0]["record_id"]}, *DOCUMENTS[1:]]]
        for documents in variants:
            with self.subTest(documents=documents), self.assertRaises(ValueError):
                probe.verify_page(response(documents, total=3), DOCUMENTS, 3)

    def test_wrong_and_inexact_counts_fail(self):
        for total in (0, 2, 4, True, 3.0, "3", None):
            payload = response()
            payload["hits"]["total"]["value"] = total
            with self.subTest(total=total), self.assertRaises(ValueError):
                probe.verify_page(payload, DOCUMENTS, 3)
        for total in (3, {"value": 3, "relation": "gte"}, {}):
            payload = response()
            payload["hits"]["total"] = total
            with self.subTest(total=total), self.assertRaises(ValueError):
                probe.verify_page(payload, DOCUMENTS, 3)

    def test_missing_failed_or_inconsistent_shards_fail(self):
        variants = [{}, {"total": 2, "successful": 1, "failed": 1, "skipped": 0},
                    {"total": 3, "successful": 2, "failed": 0, "skipped": 0},
                    {"total": 2, "successful": 2, "failed": 0, "skipped": 3},
                    {"total": 2, "successful": 2, "failed": 0, "skipped": 1},
                    {"total": 2, "successful": 2, "failed": False, "skipped": 0},
                    {"total": 2, "successful": 2, "failed": 0, "skipped": 0,
                     "failures": [{"reason": "unavailable"}]}]
        for shards in variants:
            payload = response()
            payload["_shards"] = shards
            with self.subTest(shards=shards), self.assertRaises(ValueError):
                probe.verify_page(payload, DOCUMENTS, 3)

    def test_wrong_index_fails(self):
        payload = response()
        payload["hits"]["hits"][0]["_index"] = "different-index"
        with self.assertRaises(ValueError):
            probe.verify_page(payload, DOCUMENTS, 3)

    def test_original_source_must_be_present_and_unchanged(self):
        for original in (None, {}, {**DOCUMENTS[0], "payload": "changed"}):
            payload = response()
            payload["hits"]["hits"][0]["_source"]["_source"] = original
            with self.subTest(original=original), self.assertRaises(ValueError):
                probe.verify_page(payload, DOCUMENTS, 3)

    def test_partial_results_and_imprecise_cursor_fail(self):
        for field, value in (("timed_out", True), ("timed_out", None),
                             ("terminated_early", True), ("error", "failure")):
            payload = response()
            payload[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                probe.verify_page(payload, DOCUMENTS, 3)
        for cursor in (None, [float(9007199254740993)], ["9007199254740993"], [9007199254740992]):
            payload = response()
            payload["hits"]["hits"][0]["sort"] = cursor
            with self.subTest(cursor=cursor), self.assertRaises(ValueError):
                probe.verify_page(payload, DOCUMENTS, 3)

    def test_pagination_checks_terminal_page_and_uses_verified_numeric_cursor(self):
        client = Mock()
        client.search.side_effect = [response(DOCUMENTS[:2], 3), response(DOCUMENTS[2:], 3),
                                     response([], 3)]
        with patch.object(probe, "PAGE_SIZE", 2):
            result = probe.verify_query(client, DOCUMENTS, {"match_all": {}}, "fixture")
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["pages"], 3)
        self.assertEqual([call.args[3] for call in client.search.call_args_list],
                         [None, [9007199254740994], [9007199254740995]])
        client.search.side_effect = [response(DOCUMENTS[:2], 3), response(DOCUMENTS[2:], 3),
                                     response([DOCUMENTS[-1]], 3)]
        with patch.object(probe, "PAGE_SIZE", 2), self.assertRaises(ValueError):
            probe.verify_query(client, DOCUMENTS, {"match_all": {}}, "fixture")

    def test_empty_query_must_have_zero_hits_and_total(self):
        for payload in (response(DOCUMENTS[:1], 1), response([], 1)):
            client = Mock()
            client.search.return_value = payload
            with self.assertRaises(ValueError):
                probe.verify_query(client, [], {"term": {"cohort": "absent"}}, "empty")


class LifecycleTests(unittest.TestCase):
    def test_write_failure_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            client = probe.RestClient(18080, Path(directory))
            client.opener = Mock()
            client.opener.open.side_effect = TimeoutError("uncertain acceptance")
            with self.assertRaises(TimeoutError):
                client.request("POST", "/api/v1/fixture/ingest", "write", b"{}\n")
            client.opener.open.assert_called_once()

    def test_preexisting_work_directory_is_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "keep"
            marker.write_text("original")
            args = SimpleNamespace(baseline_binary=Path("/unused/baseline"),
                                   candidate_binary=Path("/unused/candidate"),
                                   baseline_revision="same", candidate_revision="same",
                                   work_dir=root, port=18080)
            with patch.object(probe, "binary_info", return_value={"sha256": "same"}), \
                 self.assertRaises(FileExistsError):
                probe.run(args)
            self.assertEqual(list(root.iterdir()), [marker])
            self.assertEqual(marker.read_text(), "original")

    def test_revision_and_binary_pair_cannot_be_mislabeled(self):
        cases = [("same", "same", "old", "new"),
                 ("old-hash", "new-hash", "unknown", "a" * 40),
                 ("old-hash", "new-hash", "a" * 40, "a" * 40)]
        for old_hash, new_hash, old_revision, new_revision in cases:
            with self.subTest(case=(old_hash, new_hash, old_revision, new_revision)), \
                 tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "fresh"
                args = SimpleNamespace(baseline_binary=Path("/unused/baseline"),
                                       candidate_binary=Path("/unused/candidate"),
                                       baseline_revision=old_revision, candidate_revision=new_revision,
                                       work_dir=root, port=18080)
                with patch.object(probe, "binary_info", side_effect=[{"sha256": old_hash},
                                                                    {"sha256": new_hash}]), \
                     self.assertRaises(ValueError):
                    probe.run(args)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_clean_exit_is_required_and_timeout_forces_cleanup(self):
        for prior_exit, returncode, timeout in ((False, 0, False), (True, 0, False),
                                               (False, 1, False), (False, -9, True)):
            with self.subTest(prior_exit=prior_exit, returncode=returncode, timeout=timeout):
                server = probe.Server(Path("/unused"), {}, None, [], {})
                process = Mock(pid=123456, returncode=returncode)
                process.poll.side_effect = [returncode if prior_exit else None, returncode]
                if timeout:
                    process.wait.side_effect = [subprocess.TimeoutExpired("fixture", 90), returncode]
                server.process = process
                server.log = Mock()
                with patch.object(probe.os, "killpg") as signal_group:
                    if not prior_exit and returncode == 0:
                        server.stop()
                    else:
                        with self.assertRaises(ValueError):
                            server.stop()
                self.assertIsNone(server.process)
                self.assertEqual(signal_group.call_count, 0 if prior_exit else 2 if timeout else 1)
                self.assertEqual(server.events[-1]["forced"], timeout)

    def test_data_directory_exists_before_start_and_failure_retains_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fresh"
            args = SimpleNamespace(baseline_binary=Path("/unused/baseline"),
                                   candidate_binary=Path("/unused/candidate"),
                                   baseline_revision="same", candidate_revision="same",
                                   work_dir=root, port=18080)

            def inspect_start(*arguments):
                self.assertTrue((root / "data").is_dir())
                self.assertTrue((root / "indexes").is_dir())
                raise RuntimeError("startup failed")

            with patch.object(probe, "binary_info", return_value={"sha256": "same"}), \
                 patch.object(probe.Server, "start", side_effect=inspect_start), \
                 patch.object(probe.Server, "stop") as cleanup, \
                 self.assertRaisesRegex(RuntimeError, "startup failed"):
                probe.run(args)
            cleanup.assert_called_once_with(required=False)
            evidence = probe.json.loads((root / "result.json").read_text())
            self.assertEqual(evidence["status"], "failed")
            self.assertEqual(evidence["checks"], {})


class ReadinessTests(unittest.TestCase):
    def test_cluster_requires_self_generation_and_services(self):
        config = {"node_id": "fixture", "cluster_id": "fixture-cluster"}
        identity = {"node_id": "fixture", "generation_id": 123}
        snapshot = {"self_node_id": "fixture", "cluster_id": "fixture-cluster",
                    "ready_nodes": [identity], "chitchat_state_snapshot": {"node_states": [{
                        "chitchat_id": identity, "key_values": {
                            "enabled_services": {"value": "indexer,metastore,control-plane,searcher"},
                            "readiness": {"value": "READY"}}}]}}
        self.assertTrue(probe.cluster_ready(snapshot, config))
        pending = {**snapshot, "ready_nodes": []}
        self.assertFalse(probe.cluster_ready(pending, config))
        for field, value in (("self_node_id", "other"), ("cluster_id", "other"),
                             ("ready_nodes", [{"node_id": "other"}]),
                             ("ready_nodes", [{"node_id": "fixture", "generation_id": 456}]),
                             ("chitchat_state_snapshot", {})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                probe.cluster_ready({**snapshot, field: value}, config)
        snapshot["chitchat_state_snapshot"]["node_states"][0]["key_values"][
            "enabled_services"]["value"] = "metastore"
        with self.assertRaises(ValueError):
            probe.cluster_ready(snapshot, config)

    def test_only_known_startup_searcher_absence_is_retried(self):
        server = probe.Server(Path("/unused"), {}, Mock(), [], {})
        server.process = Mock()
        server.process.poll.return_value = None
        reason = ("internal error: `failed to assign search jobs: there are no available "
                  "searcher nodes in the cluster`")
        server.client.search.side_effect = [
            probe.RestError(500, probe.encoded({"error": {"reason": reason}})), response([], 3)]
        with patch.object(probe.time, "sleep") as sleep:
            server.wait_searcher("reopen")
        self.assertEqual(server.client.search.call_count, 2)
        sleep.assert_called_once_with(0.25)
        for status, message in ((500, "corrupt index"), (503, reason)):
            server.client.search.reset_mock()
            server.client.search.side_effect = probe.RestError(
                status, probe.encoded({"error": {"reason": message}}))
            with self.subTest(status=status), self.assertRaises(probe.RestError):
                server.wait_searcher("reopen")
            server.client.search.assert_called_once()

    def test_functional_readiness_rejects_partial_results_and_has_a_deadline(self):
        server = probe.Server(Path("/unused"), {}, Mock(), [], {})
        server.process = Mock()
        server.process.poll.return_value = None
        payload = response([], 3)
        payload["_shards"]["failed"] = 1
        server.client.search.return_value = payload
        with self.assertRaises(ValueError):
            server.wait_searcher("reopen")
        server.client.search.assert_called_once()
        with patch.object(probe, "START_TIMEOUT", 0), self.assertRaises(TimeoutError):
            server.wait_searcher("reopen")


if __name__ == "__main__":
    unittest.main()
