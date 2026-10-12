# Experiment 008 — narrow USearch external-payload feasibility gate

Status: the standalone local fixture passed. This does not implement or release typed Tantivy storage, a Rust FFI adapter, Quickwit ANN, a production vector format or remote lifecycle support. Application and fixture source remain local. [Measured results, component identities and oracle audits](../evidence/008-usearch-feasibility.json).

## Boundary and provenance

Pinned [USearch source](https://github.com/unum-cloud/usearch/blob/9fd6b0115dcdd0016e037fb5335f36824dd02090/include/usearch/index.hpp), v2.25.3. Local fixture revision `88462583200c0debf2340f6ecce48dee55a82b99`; source/header/executable hashes are in the JSON. Same experiment 007 host and resource limits; no overlapping engine/build benchmark. A single shuffled graph build and a fresh child query process were used. Builder destruction and process exit precede reopening.

The canonical first10,000 rows are IDs 1..10000 in ascending order, no deduplication,256 bytes/row, LSB0 Morgan payload concatenation. SHA-256 `9e86a7574ed726a756816c70bb2fc801ba042c70f4b427d64b29d6e1503db82a`, exactly 2,560,000 bytes. Native member keys are zero-based final DocIds; insertion slots are independently shuffled with seed 811057. This fixed 10k subset is a feasibility fixture, not the 100k query-performance comparison.

## Established by the fixture

- Low-level `index_gt` stores a separate serialized topology of **1,443,900bytes**. A structural parser accounts for every byte as header, levels, node keys or adjacency slots; all keys are unique valid final DocIds, every neighbor slot and level is bounded, and no complete256-byte canonical payload row occurs in the graph file.
- The external payload is loaded once into a separately owned byte vector with deliberately misaligned row starts. The distance callback uses byte loads, no reinterpreted aligned SIMD/u64 pointers, no throws and no awaits. The gate uses negative float32 Tanimoto as distance to retain the similarity's float32 ordering; chemistry integration semantics remain a separate boundary.
- A new process reopens the saved graph after all builder allocations are destroyed. Twelve exhaustive query/filter combinations are audited against independent Python integer-bit truth, including full live masks, supplier-style masks intersected with deletions, a single document and empty masks. Twelve corresponding ANN probes pass result eligibility and distance checks. Tie-aware top-10 recall is 1.0 for these nine nonempty tiny probes, not evidence of production recall or stable exact tie ordering.
- Eight callers execute 160 searches through four exclusively leased contexts. Returned key/distance values are copied before releasing each lease. Concurrent search results retain correct scores across subsequent reuse. No filtered/deleted result is returned;55,602distance callbacks in the initial ANN probes visit metadata-excluded navigation nodes, which is allowed. Empty masks bypass native work.
- A blocked-worker timeout fixture verifies that timeout does not prematurely release its lease. This does not test cancellation of an actual native search; a production async adapter must still retain native/payload ownership until completion.
- Twenty-four malformed/mismatched cases are rejected before native search: identity/profile/shape/format/build settings, modified/truncated payload/graph, bad keys/neighbor slots/levels/entry. The test wrapper fully reads and hashes components, then parses structure. It is not a header-only or remote reader and is not a production hostile-input fuzzing claim.
- Fresh-process load/search/concurrency/destruction passed AddressSanitizer, UndefinedBehaviorSanitizer and leak detection, with empty stderr and byte-equivalent parsed results. Sanitized graph construction was not run. ARM64 runtime validation was unavailable; byte-safe access on x86_64 does not replace it.

## Ownership and costs

| Measurement | Value | Boundary |
|---|---:|---|
| Graph construction wall |31.643999s| Child process including payload load, build, save, validation, destruction |
| Graph construction CPU |31.638020core-s| Complete child process |
| Fresh query fixture wall |0.613503s| Load,24 emitted probes,160 concurrent searches, timeout fixture and destruction |
| Fresh query fixture CPU |1.651834core-s| Complete child process, multiple threads |
| Native graph requested allocation peak |1,423,860B| Graph allocator, query process |
| Dynamic requested allocation before searches |148,480B| Index/context ownership |
| Dynamic requested allocation after searches |777,216B| Still retained after request leases release |
| Dynamic requested allocation peak |806,912B| Same query process |
| Final graph/dynamic requested bytes |0/0| After index destruction |

These instrumented allocator timings are feasibility costs, without an uninstrumented overhead control or independent build repetitions. They must not be compared with service-query latencies in007. Requested-byte counters exclude allocator metadata, payload/STL/result allocations and process RSS/PSS. The observed retained scratch remains owned by the index, not the completed request. Independent peaks are not summed.

## Reproduction and remaining gates

```bash
c++ -std=c++17 -O2 -DNDEBUG -pthread -Iinclude gate.cpp -o gate
python3 run_gate.py
c++ -std=c++17 -O1 -g -pthread -fsanitize=address,undefined -fno-omit-frame-pointer -Iinclude gate.cpp -o gate-asan
ASAN_OPTIONS=detect_leaks=1 ./gate-asan query payload.bin graph.bin
```

Two fixture compilation attempts failed before accepted runs: qualified lookup missed a hidden friend; an inferred size_t query key differed from the intended u32. Both were corrected without changing library source; logs are retained. The public JSON includes exact component definitions, source/artifact hashes, oracle summaries and measurements; source, raw files and payload remain local, limiting external replay.

The next storage gate must implement explicit metadata-only open and payload warmup, typed u1 and f32 fixtures, integrity/segment binding, final DocId remapping, sorted/unsorted merge/deletion/restart, required-file registration and packaging/publication/GC tests. Existing indexes retain their readers and migration requires explicit reindexing. The old local columnar draft eagerly reads its complete payload and is not approved by this feasibility result. Optional ANN must not block exact-vector delivery or make RDKit graph predicates incomplete.
