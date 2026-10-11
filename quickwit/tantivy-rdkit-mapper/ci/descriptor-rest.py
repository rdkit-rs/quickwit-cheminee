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

"""Exercise complete preparation through HTTP against pinned Cheminee golden outputs."""
import argparse
import json
from pathlib import Path
import os
import subprocess
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--binary", type=Path, required=True)
parser.add_argument("--work-dir", type=Path, required=True)
args = parser.parse_args()
args.work_dir.mkdir(parents=True, exist_ok=False)
fixtures = Path(__file__).resolve().parent.parent / "tests/fixtures"
index = json.loads((fixtures / "descriptor_v1.index.json").read_text())
raw = [json.loads(line) for line in (fixtures / "descriptor_v1.raw.ndjson").read_text().splitlines()]
expected = [{key: value[0] for key, value in json.loads(line).items()} for line in (fixtures / "descriptor_v1.cheminee.ndjson").read_text().splitlines()]
base = "http://127.0.0.1:17880"
config = {"version":"0.8", "cluster_id":"descriptor-smoke", "node_id":"single", "listen_address":"127.0.0.1", "rest":{"listen_port":17880}, "data_dir":str(args.work_dir / "data"), "metastore_uri":(args.work_dir / "indexes").as_uri(), "default_index_root_uri":(args.work_dir / "indexes").as_uri()}
(args.work_dir / "data").mkdir()
config_path = args.work_dir / "node.json"
config_path.write_text(json.dumps(config))
def request(path, body=None):
    encoded = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(base+path, data=encoded, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)
log = (args.work_dir / "service.log").open("w")
process = subprocess.Popen([str(args.binary.resolve()), "run", "--config", str(config_path)], stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ, QW_DISABLE_TELEMETRY="1"))
try:
    for attempt in range(300):
        if process.poll() is not None:
            raise RuntimeError("Quickwit exited; inspect service.log")
        try:
            request("/health/livez")
            break
        except OSError:
            time.sleep(.2)
    request("/api/v1/indexes", index)
    time.sleep(10)
    docs = [{"record_id":row["extra_data"]["record_id"], "input_smiles":row["smiles"], "extra_data":row["extra_data"]} for row in raw]
    docs += [{"record_id":99, "input_smiles":"invalid-smiles"}]
    payload = b"".join((json.dumps(row)+"\n").encode() for row in docs)
    accepted = request("/api/v1/moses/ingest?commit=force&detailed_response=true", payload)
    assert accepted["num_ingested_docs"] == len(raw) and accepted["num_rejected_docs"] == 1, accepted
    found = request("/api/v1/moses/search", {"query":"*", "max_hits":20})
    assert found["num_hits"] == len(raw), found
    observed = {hit["record_id"]:hit for hit in found["hits"]}
    fingerprint = index["doc_mapping"]["chemistry"]["spec"]
    fingerprint_name = next(field["name"] for field in index["doc_mapping"]["field_mappings"] if field["name"].startswith("morgan_"))
    query_checks = 0
    for row in expected:
        record_id = row["extra_data"]["record_id"]
        actual = observed[record_id]
        for field in ["smiles", "pattern_fingerprint", "extra_data"]:
            assert actual[field] == row[field], (record_id, field)
        assert actual[fingerprint_name] == row["morgan_fingerprint"], record_id
        for field, value in row.items():
            if field in ["smiles", "pattern_fingerprint", "morgan_fingerprint", "extra_data", "other_descriptors"]:
                continue
            response = request("/api/v1/moses/search", {"query":f"record_id:{record_id} AND {field}:{value}", "max_hits":0})
            assert response["num_hits"] == 1, (record_id, field, response)
            query_checks += 1
        cluster = row["other_descriptors"]["similarity_cluster"]
        response = request("/api/v1/moses/search", {"query":f"record_id:{record_id} AND other_descriptors.similarity_cluster:{cluster}", "max_hits":0})
        assert response["num_hits"] == 1, (record_id, response)
        query_checks += 1
    forged = json.dumps({"record_id":100, "input_smiles":"CCO", "NumHeavyAtoms":99}).encode()
    rejected = request("/api/v1/moses/ingest?commit=force&detailed_response=true", forged)
    assert rejected["num_ingested_docs"] == 0 and rejected["num_rejected_docs"] == 1, rejected
    (args.work_dir / "results.json").write_text(json.dumps({"accepted":accepted,"rejected_forgery":rejected,"golden_documents":len(raw),"descriptor_and_cluster_queries":query_checks,"status":"passed"},indent=2))
finally:
    process.terminate()
    try:
        process.wait(timeout=40)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    log.close()
