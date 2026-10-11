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

"""REST acceptance cases derived from Cheminee property and chemistry prefilters."""
import json


def check_nested_queries(request, expected, spec):
    evidence = []

    def check(query, predicate, index="moses", rows=expected):
        response = request(f"/v1/indexes/{index}/search/basic", {
            "query": query, "result_limit": 100, "sort_field": "record_id",
            "sort_ascending": True,
        })
        wanted = sorted(row["extra_data"]["record_id"] for row in rows if predicate(row))
        actual = sorted(hit["record_id"] for hit in response["hits"])
        assert actual == wanted and response["num_hits"] == len(wanted), (query, actual, wanted)
        evidence.append({"query": query, "index": index, "ids": actual})

    # Literal operators, mixed open/closed endpoints, unbounded and empty ranges.
    for field in ["NumAtoms", "NumHeavyAtoms", "NumAmideBonds", "exactmw", "CrippenClogP"]:
        boundary = expected[0][field]
        name = f"descriptors.{field}"
        for suffix, predicate in [
            (f":{boundary}", lambda v: v == boundary),
            (f":>{boundary}", lambda v: v > boundary),
            (f":>={boundary}", lambda v: v >= boundary),
            (f":<{boundary}", lambda v: v < boundary),
            (f":<={boundary}", lambda v: v <= boundary),
            (f":[{boundary} TO {boundary}]", lambda v: v == boundary),
            (f":{{{boundary} TO {boundary}}}", lambda v: False),
            (f":[* TO {boundary}]", lambda v: v <= boundary),
            (f":{{{boundary} TO *}}", lambda v: v > boundary),
            (f":[{boundary} TO {boundary + 1}}}", lambda v: boundary <= v < boundary + 1),
            (f":{{{boundary - 1} TO {boundary}]", lambda v: boundary - 1 < v <= boundary),
        ]:
            check(name + suffix, lambda row: predicate(row[field]))
    check("descriptors.NumAtoms:10.0", lambda r: r["NumAtoms"] == 10)
    check("descriptors.NumAtoms:[13 TO 100]", lambda r: 13 <= r["NumAtoms"] <= 100)
    check("descriptors.exactmw:[136.2 TO 10000] AND descriptors.NumAtoms:[10 TO 10000]",
          lambda r: 136.2 <= r["exactmw"] <= 10000 and 10 <= r["NumAtoms"] <= 10000)
    check("descriptors.NumAtoms:[10 TO 10000]", lambda r: 10 <= r["NumAtoms"] <= 10000)
    check("descriptors.NumAtoms:[0 TO 10] AND (other_descriptors.scaffolds:0 OR other_descriptors.scaffolds:1 OR other_descriptors.scaffolds:-1)",
          lambda r: 0 <= r["NumAtoms"] <= 10 and bool(set(r["other_descriptors"]["scaffolds"]) & {0, 1, -1}))
    check("(other_descriptors.similarity_cluster:0 OR other_descriptors.similarity_cluster:2) AND descriptors.NumAtoms:[1 TO 100] AND descriptors.NumAmideBonds:[1 TO 5]",
          lambda r: r["other_descriptors"]["similarity_cluster"] in [0, 2] and 1 <= r["NumAtoms"] <= 100 and 1 <= r["NumAmideBonds"] <= 5)
    check("descriptors.NumAtoms:>5 AND NOT descriptors.NumHeavyAtoms:<5",
          lambda r: r["NumAtoms"] > 5 and not r["NumHeavyAtoms"] < 5)
    check("descriptors.exactmw:<50 OR descriptors.exactmw:>100",
          lambda r: r["exactmw"] < 50 or r["exactmw"] > 100)
    for field in ["NumAtoms", "exactmw", "CrippenClogP"]:
        for ascending in [False, True]:
            response = request("/v1/indexes/moses/search/basic", {
                "query": "*", "sort_field": f"descriptors.{field}",
                "sort_ascending": ascending, "result_limit": 100,
            })
            wanted = [r["extra_data"]["record_id"] for r in sorted(expected,
                key=lambda r: ((1 if ascending else -1) * r[field], r["extra_data"]["record_id"]))]
            actual = [hit["record_id"] for hit in response["hits"]]
            assert actual == wanted, (field, ascending, actual, wanted)
            evidence.append({"sort_field": field, "ascending": ascending, "ids": actual})

    # Actual chemistry endpoints: compare filtered results with an independently
    # filtered complete unfiltered result set. The eight-document corpus fits top-k.
    by_id = {r["extra_data"]["record_id"]: r for r in expected}
    for route, smiles in [("identity", "CCO"), ("substructure", "C"),
                          ("superstructure", "CCO"), ("similarity", "CCO")]:
        body = {"spec": spec, "smiles": smiles, "result_limit": 100}
        if route == "similarity":
            body["tanimoto_minimum"] = 0
        else:
            body["prepared_smiles_field"] = "smiles"
        path = f"/v1/indexes/moses/search/{route}"
        baseline = request(path, body)
        for expression, predicate in [
            ("descriptors.NumAtoms:>0 AND descriptors.exactmw:<100", lambda r: r["NumAtoms"] > 0 and r["exactmw"] < 100),
            ("descriptors.NumAtoms:<0", lambda r: False),
        ]:
            filtered = request(path, dict(body, extra_query=expression))
            wanted = [h["record_id"] for h in baseline["hits"] if predicate(by_id[int(h["record_id"])])]
            actual = [h["record_id"] for h in filtered["hits"]]
            assert actual == wanted, (route, expression, actual, wanted)
            evidence.append({"route": route, "extra_query": expression, "ids": actual})

    # Full preparation always emits every property. A separate generic index
    # exercises missing/null paths, mixed JSON numeric types and absent columns.
    request("/api/v1/indexes", {"version":"0.8", "index_id":"descriptor-missing",
        "doc_mapping":{"field_mappings":[{"name":"record_id","type":"u64","fast":True},
            {"name":"descriptors","type":"json","fast":True}]}})
    rows = [{"extra_data":{"record_id":i}, "v":v} for i, v in enumerate([10, 10.0, 10.5, None, None], 1)]
    payload = b"".join((json.dumps({"record_id":r["extra_data"]["record_id"],
        "descriptors":{} if r["extra_data"]["record_id"] == 4 else {"mixed":r["v"]}})+"\n").encode() for r in rows)
    accepted = request("/api/v1/descriptor-missing/ingest?commit=force", payload)
    assert accepted["num_ingested_docs"] == 5, accepted
    # A separately published split has no descriptors object or numeric column.
    accepted = request("/api/v1/descriptor-missing/ingest?commit=force", b'{"record_id":6}\n')
    assert accepted["num_ingested_docs"] == 1, accepted
    rows.append({"extra_data":{"record_id":6}, "v":None})
    for query, predicate in [
        ("descriptors.mixed:10", lambda r: r["v"] == 10),
        ("descriptors.mixed:[9.5 TO 10.5]", lambda r: r["v"] is not None and 9.5 <= r["v"] <= 10.5),
        ("descriptors.mixed:>10", lambda r: r["v"] is not None and r["v"] > 10),
        ("NOT descriptors.mixed:10", lambda r: r["v"] != 10),
        ("descriptors.unknown:[0 TO 100]", lambda r: False),
    ]:
        check(query, predicate, "descriptor-missing", rows)
    return evidence
