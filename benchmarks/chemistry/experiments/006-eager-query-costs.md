# Experiment 006 — eager query-cost baseline

Status: the eager baseline is complete and audited. Candidate-first validation is a separate ongoing gate; no optimization measurement is included here. No generic vector or ANN implementation is evaluated.

## Boundary and provenance

- Control source: `7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b` (the measured flat native preparation implementation).
- Instrumented source: `29adfec0fdfc76f6a7f4f9570c94e9277ef319ee`; profiler source: `c0725a06780a750a0bd499f1fb1046ba94738e0d`.
- Control binary SHA-256: `ec0873f6b39bddb380fb64cfc407ec23e6f01f070df33bd0809d11521db6c7e9`.
- Instrumented binary SHA-256: `0d9415bb42068316323a48fea7586cd6b6872f70de37a5ff2ab57314c93f82b5`.
- Both are native descriptor-v1/SMILES-capable builds using dynamically linked RDKit 2026.09 and TensorFlow libraries. RDKit package: `2026.09.1+ds1-1~ubuntu26.04`; TensorFlow CPU `2.15.1`; Rust `1.96.1`; bindings `0ae060c9cfc14626172070989fee890b16454373`. Build command: `cargo build --locked --release -p quickwit-cli --features descriptor-v1 --bin quickwit`. Linkage logs and build results remain retained locally.
- Same immutable 100k flat index: 8 published splits, 8 Tantivy segments, 64 internal files, 48,065,742 split bytes, from completed experiment 005. All split SHA-256 values were identical before/after both runs.
- Same four-core CPU quota and 14 GiB memory limit, QW_NUM_CPUS=4, Tokio threads=2, local file storage. No overlapping engine/build runs.
- Partial-result and predicate caches explicitly disabled; OS page cache not dropped. Two warmups precede measurement. This is warm execution, not OS-cold or cached-result serving.
- One fresh process per variant: 20 similarity cases × 10 repetitions plus 16 graph cases × 5 repetitions = 280 measured requests each, excluding warmups. All counts, ordered IDs and scores passed independent retained exhaustive oracles. Both services exited normally with no forced shutdown.
- This study does not measure ingestion again, does not replace historical hardware/exporter comparisons, and is not a matched Cheminee query comparison. Held-out/concurrent-request extensions are not included.

Raw corpus SHA-256: `9a63bf25bc02ba3c965bb050cd74ba1a059bc362b8fb210b8febb6a326ce2e5e`. Independent query-oracle SHA-256: `c6c0210cbf4b52a28d88a5a18e731b2f830bd8cd448668e5b89ca1157cb6449c`. The metrics JSON embeds all 36 exact query SMILES, thresholds, result limits, metadata predicates and expected counts/ordered hits.

The earlier cache-serving warm-query study is not directly comparable: it enabled result caching, while these runs explicitly disable it.

[Metrics and exact query definitions](../evidence/006-eager-query-metrics.json), [sanitized counter traces](../evidence/006-eager-query-traces.zip), and [archive checksum](../evidence/006-eager-query-traces.json). The instrumented revision is a local measurement overlay, not released production code.

## Query latency and process CPU

Means below use per-request wall durations and complete batch process CPU divided by repetitions. The small request counts support descriptive means; they do not establish production tail latency or independent host-to-host variability.

| Case | Reps | Control mean seconds | Control CPU/request | Instrumented mean seconds | Instrumented CPU/request |
|---|---:|---:|---:|---:|---:|
| historical-similarity-1-0.3-all-k10 | 10 | 1.248529 | 1.559000 | 1.305195 | 1.654000 |
| historical-similarity-1-0.3-all-k100 | 10 | 1.300079 | 1.672000 | 1.349120 | 1.764000 |
| historical-similarity-1-0.3-supplier10pct-k10 | 10 | 1.224248 | 1.558000 | 1.318950 | 1.658000 |
| historical-similarity-1-0.3-supplier10pct-k100 | 10 | 1.281755 | 1.589000 | 1.321160 | 1.645000 |
| historical-similarity-1-0.3-one-k10 | 10 | 1.366754 | 1.709000 | 1.309136 | 1.646000 |
| historical-similarity-1-0.3-one-k100 | 10 | 1.227442 | 1.540000 | 1.339026 | 1.687000 |
| historical-similarity-1-0.3-empty_intersection-k10 | 10 | 1.248294 | 1.550000 | 1.315169 | 1.660000 |
| historical-similarity-1-0.3-empty_intersection-k100 | 10 | 1.218850 | 1.530000 | 1.305112 | 1.645000 |
| historical-similarity-998-0.3-all-k10 | 10 | 1.228296 | 1.535000 | 1.302668 | 1.654000 |
| historical-similarity-998-0.3-supplier10pct-k10 | 10 | 1.243989 | 1.563000 | 1.345884 | 1.692000 |
| historical-similarity-998-0.3-one-k10 | 10 | 1.241549 | 1.542000 | 1.323819 | 1.700000 |
| historical-similarity-998-0.3-empty_intersection-k10 | 10 | 1.210945 | 1.498000 | 1.284380 | 1.628000 |
| historical-similarity-10000-0.3-all-k10 | 10 | 1.230649 | 1.531000 | 1.303026 | 1.651000 |
| historical-similarity-10000-0.3-supplier10pct-k10 | 10 | 1.227128 | 1.554000 | 1.290865 | 1.625000 |
| historical-similarity-10000-0.3-one-k10 | 10 | 1.259265 | 1.561000 | 1.302957 | 1.625000 |
| historical-similarity-10000-0.3-empty_intersection-k10 | 10 | 1.229521 | 1.510000 | 1.298656 | 1.648000 |
| similarity-50000-all-k10 | 10 | 1.243611 | 1.546000 | 1.298174 | 1.658000 |
| similarity-50000-supplier10pct-k10 | 10 | 1.234032 | 1.548000 | 1.297107 | 1.655000 |
| similarity-50000-one-k10 | 10 | 1.246789 | 1.543000 | 1.284480 | 1.622000 |
| similarity-50000-empty_intersection-k10 | 10 | 1.245522 | 1.553000 | 1.342418 | 1.651000 |
| identity-1-all-k10 | 5 | 8.436147 | 10.486000 | 8.778182 | 11.110000 |
| identity-1-supplier10pct-k10 | 5 | 8.304449 | 10.352000 | 8.633600 | 10.900000 |
| identity-1-one-k10 | 5 | 8.564431 | 10.446000 | 8.548974 | 10.694000 |
| identity-1-empty_intersection-k10 | 5 | 8.281912 | 10.286000 | 8.598177 | 10.790000 |
| substructure-0-all-k10 | 5 | 9.010745 | 11.076000 | 9.232936 | 11.570000 |
| substructure-0-supplier10pct-k10 | 5 | 9.091130 | 11.234000 | 9.593630 | 11.906000 |
| substructure-0-one-k10 | 5 | 9.291121 | 11.562000 | 9.517227 | 11.770000 |
| substructure-0-empty_intersection-k10 | 5 | 9.476881 | 11.722000 | 9.439478 | 11.632000 |
| substructure-selective-1-all-k10 | 5 | 8.297409 | 10.396000 | 8.676390 | 10.932000 |
| substructure-selective-1-supplier10pct-k10 | 5 | 8.518706 | 10.534000 | 8.598295 | 10.832000 |
| substructure-selective-1-one-k10 | 5 | 8.500326 | 10.314000 | 8.928049 | 10.970000 |
| substructure-selective-1-empty_intersection-k10 | 5 | 8.337809 | 10.416000 | 8.547623 | 10.794000 |
| superstructure-1-all-k10 | 5 | 8.256188 | 10.194000 | 8.476028 | 10.578000 |
| superstructure-1-supplier10pct-k10 | 5 | 8.040008 | 10.048000 | 8.453302 | 10.628000 |
| superstructure-1-one-k10 | 5 | 8.150993 | 10.036000 | 8.539969 | 10.676000 |
| superstructure-1-empty_intersection-k10 | 5 | 8.326744 | 10.484000 | 8.401396 | 10.498000 |

Instrumentation/control CPU ratios range from 0.9631 to 1.1025 across cases. These sequential runs mix instrumentation cost with run-to-run variation; ratios below 1 are not negative overhead, and no per-stage correction is inferred.

## Instrumented work and CPU ownership

Stage clocks use exclusive per-thread CPU, propagated across async polls and reusable worker pools. Stage 13 groups collection and shared query execution; it is not pure collection CPU. Instrumentation overhead is measured by the preceding control, not subtracted from individual stages.

| Case | FP values/request | Tanimoto/request | Target parses/request | FP decode CPU/request | Tanimoto CPU/request | RDKit parse CPU/request | Graph verify/rank CPU/request |
|---|---:|---:|---:|---:|---:|---:|---:|
| historical-similarity-1-0.3-all-k10 | 99995 | 99995 | 0 | 1.541348 | 0.031006 | 0.000000 | 0.000000 |
| historical-similarity-1-0.3-all-k100 | 99995 | 99995 | 0 | 1.542953 | 0.030680 | 0.000000 | 0.000000 |
| historical-similarity-1-0.3-supplier10pct-k10 | 99995 | 99995 | 0 | 1.543553 | 0.031786 | 0.000000 | 0.000000 |
| historical-similarity-1-0.3-supplier10pct-k100 | 99995 | 99995 | 0 | 1.533702 | 0.030458 | 0.000000 | 0.000000 |
| historical-similarity-1-0.3-one-k10 | 99995 | 99995 | 0 | 1.547334 | 0.030469 | 0.000000 | 0.000000 |
| historical-similarity-1-0.3-one-k100 | 99995 | 99995 | 0 | 1.578607 | 0.032604 | 0.000000 | 0.000000 |
| historical-similarity-1-0.3-empty_intersection-k10 | 99995 | 99995 | 0 | 1.556546 | 0.031487 | 0.000000 | 0.000000 |
| historical-similarity-1-0.3-empty_intersection-k100 | 99995 | 99995 | 0 | 1.544925 | 0.030592 | 0.000000 | 0.000000 |
| historical-similarity-998-0.3-all-k10 | 99995 | 99995 | 0 | 1.541068 | 0.032347 | 0.000000 | 0.000000 |
| historical-similarity-998-0.3-supplier10pct-k10 | 99995 | 99995 | 0 | 1.584501 | 0.030914 | 0.000000 | 0.000000 |
| historical-similarity-998-0.3-one-k10 | 99995 | 99995 | 0 | 1.586584 | 0.033887 | 0.000000 | 0.000000 |
| historical-similarity-998-0.3-empty_intersection-k10 | 99995 | 99995 | 0 | 1.521638 | 0.033759 | 0.000000 | 0.000000 |
| historical-similarity-10000-0.3-all-k10 | 99995 | 99995 | 0 | 1.539495 | 0.031123 | 0.000000 | 0.000000 |
| historical-similarity-10000-0.3-supplier10pct-k10 | 99995 | 99995 | 0 | 1.520339 | 0.031281 | 0.000000 | 0.000000 |
| historical-similarity-10000-0.3-one-k10 | 99995 | 99995 | 0 | 1.530717 | 0.029829 | 0.000000 | 0.000000 |
| historical-similarity-10000-0.3-empty_intersection-k10 | 99995 | 99995 | 0 | 1.537274 | 0.032859 | 0.000000 | 0.000000 |
| similarity-50000-all-k10 | 99995 | 99995 | 0 | 1.547462 | 0.031548 | 0.000000 | 0.000000 |
| similarity-50000-supplier10pct-k10 | 99995 | 99995 | 0 | 1.551531 | 0.030933 | 0.000000 | 0.000000 |
| similarity-50000-one-k10 | 99995 | 99995 | 0 | 1.525054 | 0.030199 | 0.000000 | 0.000000 |
| similarity-50000-empty_intersection-k10 | 99995 | 99995 | 0 | 1.553484 | 0.029918 | 0.000000 | 0.000000 |
| identity-1-all-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.717701 | 1.355668 |
| identity-1-supplier10pct-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.564358 | 1.321422 |
| identity-1-one-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.431949 | 1.303366 |
| identity-1-empty_intersection-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.496908 | 1.316065 |
| substructure-0-all-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.551640 | 1.996316 |
| substructure-0-supplier10pct-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.777708 | 2.050967 |
| substructure-0-one-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.711498 | 2.039056 |
| substructure-0-empty_intersection-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.586476 | 2.009031 |
| substructure-selective-1-all-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.557176 | 1.330246 |
| substructure-selective-1-supplier10pct-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.503966 | 1.311564 |
| substructure-selective-1-one-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.595967 | 1.331418 |
| substructure-selective-1-empty_intersection-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.488886 | 1.316363 |
| superstructure-1-all-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.388916 | 1.184733 |
| superstructure-1-supplier10pct-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.437069 | 1.193285 |
| superstructure-1-one-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.492961 | 1.204036 |
| superstructure-1-empty_intersection-k10 | 0 | 0 | 99995 | 0.000000 | 0.000000 | 7.371681 | 1.182637 |

All 36 stage intervals reconcile within their explicitly reported /proc sampling bounds. Estimate-minus-stage residual range: -0.010334 to 0.015451 core-seconds per batch. The JSON retains bounds, estimates and raw timestamps; endpoint sampling/10ms process-clock quantization limit precision.

## Memory, I/O and transport

| Variant | Peak shared process RSS MiB | Peak shared process PSS MiB |
|---|---:|---:|
| eager-control-1 | 307.379 | 305.603 |
| eager-instrumented-1 | 303.777 | 301.973 |

Instrumented logical Rust capacities (score vectors, external decode buffers): process-lifetime peaks [719960, 1024] bytes; final retained [0, 0] bytes. These counters exclude allocator overhead, RDKit allocations, internal dictionary buffers and other retained state. They are not a complete allocation profile and are not additive with RSS/PSS. Peaks across different stages/runs are not summed.

The metrics JSON includes boot-idle, loaded-idle and post-query-idle process snapshots, mappings/file/FD counts, per-batch process read/write counters, HTTP body byte volumes and rates over each complete batch interval. Body rates include query execution and backpressure and are not network capacity. Headers are excluded. Process I/O and logical decoded payload bytes are distinct boundaries. Fault counts were not captured by this harness.

## Exclusions and reproduction

Pilots 1–3 are excluded: missing node directory; a binary built without native chemistry; and an incorrect constant-score graph expectation in the new harness. The graph oracle was corrected from retained full graph matches and heavy-atom counts, cross-checked against existing ranked top 10 oracles. Engine code was not changed to pass. Pilot 4 then passed all 36 cases.

Original protocol files, exact build logs and binaries remain retained locally. The public evidence includes unchanged numeric counters, boundary snapshots, request timings, body volumes, ordered ID/score audits and SHA-256 links to the original records. It excludes process identifiers, addresses, local paths, service logs and full returned documents. This limits independent replay; it does not change the measured values.

The sanitized export is reproducible from the retained study:

```bash
export QUERY_STUDY_ROOT=/absolute/path/to/query-study
export EVIDENCE_OUTPUT=/absolute/path/to/evidence-output
python3 benchmarks/chemistry/harness/public_query_evidence.py
```

The underlying runs used `run_queries.py --tag eager-control-1 --variant control`
and then `run_queries.py --tag eager-instrumented-1 --variant instrumented`,
with default 10 similarity and 5 graph repetitions. Their prepared fixed index
is the completed experiment 005 index. No engine/build overlapped either run.
Historical indexing and lifecycle measurements remain separate and unchanged.

## Next optimization gate

The local candidate-first draft keeps validation of every fingerprint and document, uses fallible batched ordinal decoding, and computes distances only for metadata candidates. This combines batched decoding and candidate pruning; any future speedup must distinguish them. Candidate DocId/ordinal vectors add memory that must be accounted for. A separate local candidate implementation is under validation. No candidate performance measurement is included in this baseline report. Graph matching is unchanged.
