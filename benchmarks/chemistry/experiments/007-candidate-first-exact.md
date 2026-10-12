# Experiment 007 — batched decoding and candidate-first exact scoring

Status: implemented and measured locally; source publication remains pending. All accepted runs completed normally, passed independent query oracles and preserved all eight index split hashes. The sanitized evidence is published separately from application source.

## Scope and result

These are **query-specific results on the fixed 100k MOSES corpus with partial-result and predicate caches disabled**. The change combines fallible batched fingerprint decoding with candidate-only exact scoring. It is not an ingestion measurement, a generic product ranking, a Cheminee query comparison, an ANN result or a claim about production tail latency. Historical measurements remain unchanged.

Query 1, unfiltered top10, decreased from 1.248529 to 0.201220 seconds mean latency and from 1.559 to 0.254 CPU core-seconds/request (6.20x wall speedup). Its empty metadata intersection decreased from 1.248294 to 0.100446 seconds and from 1.550 to 0.124 CPU core-seconds/request (12.43x wall speedup). All 20 matched similarity cases improved in this execution: wall speedups 5.50–13.72x, CPU speedups 4.83–13.57x. These descriptive ranges use ten repetitions per case in one process per variant; they do not establish independent run-to-run distributions.

[Machine-readable metrics and query definitions](../evidence/007-candidate-query-metrics.json), [sanitized raw counter traces and response audits](../evidence/007-candidate-query-traces.zip), [archive checksum](../evidence/007-candidate-query-traces.json).

## Revisions and fixed conditions

| Role | Local source revision | Executable SHA-256 |
|---|---|---|
| Eager control | `7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b` | `ec0873f6b39bddb380fb64cfc407ec23e6f01f070df33bd0809d11521db6c7e9` |
| Candidate control | `59808c3026a354304c41c6e8c6367fcfd73bf14c` | `8de516c229752377143024fdadf6a371d62ae7e11b4f48000a4caa43c7453fa4` |
| Candidate instrumented | `de8a6878f457e706345818c60f125f03d85cf982` | `5391963565a79cd3669a2c494c8d6d5edba38c155f57359a40db2364b5ca3ab5` |

Profiler source `837bab60ee95911b307800f44349395080b1a457`; shared object SHA-256 `f6bd23b072d8f53777c15042d33a1d60f47503c947a412fc1a00cbc18184b6e9`.

Same AMD EPYC 9V74 host, Ubuntu26.04.1, four-core quota (`cpu.max=400000 100000`), 14GiB memory, QW_NUM_CPUS=4 and Tokio threads=2. Dynamic homemade RDKit package `2026.09.1+ds1-1~ubuntu26.04`, TensorFlow CPU2.15.1, bindings `0ae060c9cfc14626172070989fee890b16454373`, Tantivy `057458bf14d6973c9c97594c1d99580b6af4c49d`, Rust1.96.1. Native CLI built with descriptor-v1. No overlapping engines or builds.

The completed experiment005 index supplies 100,000 documents, 99,995 per-segment unique fingerprint values, eight published splits/eight internal segments, 64 internal files and 48,065,742 split bytes. All eight SHA-256 identities are embedded in every run's metrics and raw lifecycle record. Query-only metastore/searcher services did not ingest or run indexer/janitor lifecycle work. The observed deletion lifecycle remains experiment005's result; this experiment does not establish a new merge fixed point.

Raw corpus SHA-256 `9a63bf25bc02ba3c965bb050cd74ba1a059bc362b8fb210b8febb6a326ce2e5e`; original exhaustive oracle SHA-256 `c6c0210cbf4b52a28d88a5a18e731b2f830bd8cd448668e5b89ca1157cb6449c`. All exact query SMILES, float32 thresholds, metadata predicates, limits and expected ordered hits are in the metrics. Eager similarity timings are the unchanged subset of experiment006, not a rerun selected after optimization.

OS caches were not dropped. Each fresh process had two explicit unfiltered warmups and a loaded idle interval. Restarted means a new process, not cold storage. Partial-result and predicate cache capacity were both explicitly zero. The earlier result-cache-serving measurements are incomparable to this execution path.

## Compatibility and correctness

Global validation still checks the exact256-byte width of every dictionary fingerprint and exactly one ordinal for every document in0..max_doc, including excluded/deleted rows. Global validation runs before candidate setup. The implementation uses fallible `sorted_ords_to_term_cb`; it does not use the streaming API that unwraps read failures. Width validation is bounded to256-ordinal batches; candidate ordinals are sorted/deduplicated and decoded through the batched API. A dense score vector plus candidate DocIds/temporary ordinals adds explicit memory.

Scoring remains exact float32 Tanimoto with inclusive thresholds, boosts, full counts, deterministic existing tie order and valid all-zero indexed fingerprints. All-zero query fingerprints remain invalid. Fallible work remains in scorer setup; explicit vector reservation failures propagate, without truncated candidates. Graph predicates retain their eager RDKit behavior and error semantics; Morgan candidates are not used to make graph matching incomplete.

Both production and instrumented builds passed nine scoring tests (five new, four existing). New cases cover excluded/deleted malformed values, missing/multiple values, duplicate ordinals, zero indexed vectors, thresholds, boosts, seeks, segments/deletions, candidate setup errors and600unique vectors across batch boundaries using an independent integer-bit oracle. Both native REST pilots passed36cases, including unchanged graph queries. Each candidate then passed200measured similarity requests. Complete response counts, ordered IDs and scores were re-audited from raw files (REST score tolerance1e-6); exact scorer tests cover float semantics. Repeated graph performance was not rerun.

The first test build failed because an internal test-only Tantivy cursor was unavailable; a private forward cursor replaced that dependency before accepted tests/builds. Failure logs remain retained. Held-out setup initially used a Python without RDKit and failed; the existing RDKit2026.09.1 study environment generated the accepted oracle. Neither failure produced accepted timing results. The production build started from the exact staged source and that unchanged source was committed during compilation; a subsequent Cargo artifact inventory confirmed the same source was fresh. Executables are separately saved, hashed copies, not mutable Cargo-output hardlinks.

## Matched sequential measurements

CPU is complete request-batch process CPU divided by ten. Wall means are individual HTTP request durations. Quantized process clocks and sequential host variation limit small differences.

| Case | Eager mean s | Candidate mean s | Eager CPU/request | Candidate CPU/request | Wall speedup |
|---|---:|---:|---:|---:|---:|
| historical-similarity-1-0.3-all-k10 | 1.248529 | 0.201220 | 1.559000 | 0.254000 | 6.20x |
| historical-similarity-1-0.3-all-k100 | 1.300079 | 0.236434 | 1.672000 | 0.346000 | 5.50x |
| historical-similarity-1-0.3-supplier10pct-k10 | 1.224248 | 0.176221 | 1.558000 | 0.220000 | 6.95x |
| historical-similarity-1-0.3-supplier10pct-k100 | 1.281755 | 0.168565 | 1.589000 | 0.212000 | 7.60x |
| historical-similarity-1-0.3-one-k10 | 1.366754 | 0.099621 | 1.709000 | 0.126000 | 13.72x |
| historical-similarity-1-0.3-one-k100 | 1.227442 | 0.101599 | 1.540000 | 0.125000 | 12.08x |
| historical-similarity-1-0.3-empty_intersection-k10 | 1.248294 | 0.100446 | 1.550000 | 0.124000 | 12.43x |
| historical-similarity-1-0.3-empty_intersection-k100 | 1.218850 | 0.097853 | 1.530000 | 0.121000 | 12.46x |
| historical-similarity-998-0.3-all-k10 | 1.228296 | 0.199936 | 1.535000 | 0.247000 | 6.14x |
| historical-similarity-998-0.3-supplier10pct-k10 | 1.243989 | 0.169250 | 1.563000 | 0.210000 | 7.35x |
| historical-similarity-998-0.3-one-k10 | 1.241549 | 0.095317 | 1.542000 | 0.121000 | 13.03x |
| historical-similarity-998-0.3-empty_intersection-k10 | 1.210945 | 0.097196 | 1.498000 | 0.123000 | 12.46x |
| historical-similarity-10000-0.3-all-k10 | 1.230649 | 0.201630 | 1.531000 | 0.258000 | 6.10x |
| historical-similarity-10000-0.3-supplier10pct-k10 | 1.227128 | 0.171325 | 1.554000 | 0.221000 | 7.16x |
| historical-similarity-10000-0.3-one-k10 | 1.259265 | 0.093129 | 1.561000 | 0.115000 | 13.52x |
| historical-similarity-10000-0.3-empty_intersection-k10 | 1.229521 | 0.100273 | 1.510000 | 0.122000 | 12.26x |
| similarity-50000-all-k10 | 1.243611 | 0.196217 | 1.546000 | 0.248000 | 6.34x |
| similarity-50000-supplier10pct-k10 | 1.234032 | 0.173455 | 1.548000 | 0.221000 | 7.11x |
| similarity-50000-one-k10 | 1.246789 | 0.096636 | 1.543000 | 0.120000 | 12.90x |
| similarity-50000-empty_intersection-k10 | 1.245522 | 0.093716 | 1.553000 | 0.115000 | 13.29x |

## What the instrumentation distinguishes

This is a **combined change, without a factorial ablation**. No valid percentage of speedup can be assigned independently to batching versus candidate-first scoring. The unfiltered case still computes99,995distances, so pruning cannot explain that case's gain. Instrumented query1/all fingerprint decoding previously cost1.541348core-seconds/request. New global batched validation costs0.110725 and candidate batched decode0.124342; distance CPU remains approximately0.03. This supports reduced dictionary access cost as the principal observed mechanism for that case, without proving an isolated causal speedup. Filtered cases additionally avoid distances and selected decoding, while global validation remains mandatory.

| Query1 filter | Global validated values | Materialized docs | Distances | Global validation/decode CPU | Candidate decode CPU | Distance CPU |
|---|---:|---:|---:|---:|---:|---:|
| historical-similarity-1-0.3-all-k10 | 99995 | 100000 | 99995 | 0.110725 | 0.124342 | 0.030316 |
| historical-similarity-1-0.3-supplier10pct-k10 | 99995 | 10000 | 10000 | 0.109729 | 0.088052 | 0.003081 |
| historical-similarity-1-0.3-one-k10 | 99995 | 1 | 1 | 0.117939 | 0.000023 | 0.000001 |
| historical-similarity-1-0.3-empty_intersection-k10 | 99995 | 0 | 0 | 0.106625 | 0.000003 | 0.000000 |

All100,000document cardinality checks remain in each query. Callback bytes are logical decoded payload volume, not storage/network reads: query1/all now emits51,197,440bytes across global and selected passes; empty emits25,598,720. Batched API call counts include empty calls and do not equal physical I/O.

Stage CPU uses exclusive per-thread clocks propagated across async polls and worker pools. Shared execution/collection remains honestly grouped. Direct process CPU and stage sums are sampled at the same profiler boundaries; threads are not globally stopped during reads. Sequential residuals are -0.000009936 to+0.000010035core-seconds/batch. Concurrent residuals are -0.000003636 to+0.000008793. All pass the0.02core-second acceptance bound. These close reconciliations do not imply attribution is perfect: shared runtime and uninstrumented cleanup remain grouped.

Sequential instrumented/control ratios span0.9463–1.1615wall and0.9516–1.1908CPU. This includes host/run variation and instrumentation cost; below-one ratios are not negative overhead. Instrumentation is not subtracted from individual stages. The concurrency instrumented variant has visibly higher unfiltered cost; full figures remain in JSON and are not used as control speedups.

## Held-out concurrent probes

Benzene and caffeine canonical SMILES are absent from the100k index. Independent exhaustive integer-bit Tanimoto used the existing payloads, with query fingerprints generated in RDKit2026.09.1 and packing/profile calibrated against an indexed fingerprint. Thresholds are float32(.05) and float32(.2). Their all/supplier hit counts are7424/761 and173/13. One-document and empty intersections have zero hits. These are two small molecular probes, not a representative held-out production distribution.

Each of eight cases ran one barrier-started cohort of four concurrent requests per variant,32measured requests per variant. All96responses passed independent counts/order/score oracles; observed buffer ownership returned to zero after each instrumented cohort. No individual concurrent-request CPU attribution is claimed: CPU/request below is cohort total divided by four. There are no independent cohort repetitions or production p99 claims.

| Case | Eager mean request s | Candidate mean request s | Eager cohort s | Candidate cohort s | Eager CPU/request | Candidate CPU/request |
|---|---:|---:|---:|---:|---:|---:|
| heldout-benzene-all-k10 | 1.594998 | 0.259384 | 2.241383 | 0.310583 | 1.587500 | 0.247500 |
| heldout-benzene-supplier10pct-k10 | 1.538048 | 0.247534 | 1.656175 | 0.314193 | 1.550000 | 0.247500 |
| heldout-benzene-one-k10 | 1.543123 | 0.136353 | 1.787053 | 0.156426 | 1.535000 | 0.130000 |
| heldout-benzene-empty_intersection-k10 | 1.702382 | 0.143404 | 2.019796 | 0.176933 | 1.690000 | 0.145000 |
| heldout-caffeine-all-k10 | 1.646630 | 0.293896 | 2.101326 | 0.382876 | 1.647500 | 0.292500 |
| heldout-caffeine-supplier10pct-k10 | 1.616421 | 0.243967 | 2.012438 | 0.334894 | 1.612500 | 0.242500 |
| heldout-caffeine-one-k10 | 1.624993 | 0.141924 | 1.831012 | 0.157415 | 1.617500 | 0.135000 |
| heldout-caffeine-empty_intersection-k10 | 1.582227 | 0.128774 | 1.642636 | 0.138594 | 1.612500 | 0.122500 |

## Memory, lifecycle and transfer accounting

Shared process RSS/PSS are sampled values, not stage-owned memory. Maximum sampled active-batch RSS/PSS are shown below; these differ from full-lifetime mixed-workload peaks in006. Do not sum peaks across nonconcurrent runs or add logical capacities to RSS.

| Run | Sampled active RSS MiB | Sampled active PSS MiB |
|---|---:|---:|
| eager-control-1 | 302.246 | 300.470 |
| candidate-control-1 | 309.465 | 307.752 |
| candidate-instrumented-1 | 304.945 | 303.075 |
| heldout-c4-eager-control-1 | 300.480 | 298.604 |
| heldout-c4-candidate-control-1 | 302.602 | 300.805 |
| heldout-c4-candidate-instrumented-1 | 298.840 | 297.013 |

Instrumented logical capacity peaks, in order score-vector/external-graph-buffer/candidate-DocId/temporary-ordinal bytes, are `[715160,286,524288,1048576]` sequential and `[1292720,288,2097152,4194304]` concurrent. Each includes graph warmup; independent component maxima must not be summed into a concurrent peak. All four observed retained values were zero after every measured batch/cohort and finally. Native RDKit allocations, allocator overhead, stacks and internal dictionary decoder buffers are not observed; this is not a full allocation profile or proof that all process memory was freed.

JSON retains boot-idle, loaded-idle, query-complete and post-query-idle snapshots, mapping/file/FD counts, request/response body bytes, process read/write counters and rates over explicitly bounded batch/cohort intervals. HTTP body rates include execution/backpressure, exclude headers, and are not network capacity. Actual read bytes differ from logical decoded bytes. This harness did not capture fault counters. All eight split identities and the three executable identities were checked independently after the final run. No forced shutdown occurred.

## Reproduction and evidence limits

Native commands (same locked dependency graph and environment as006):

```bash
cargo test --locked --release -p tantivy-rdkit --features openapi
cargo build --locked --release -p quickwit-cli --features descriptor-v1 --bin quickwit
python3 run_candidate_queries.py --tag candidate-control-1 --variant control --case-family similarity
python3 run_candidate_queries.py --tag candidate-instrumented-1 --variant instrumented --case-family similarity
python3 run_heldout_concurrent.py --tag heldout-c4-eager-control-1 --variant control --engine-version eager
python3 run_heldout_concurrent.py --tag heldout-c4-candidate-control-1 --variant control --engine-version candidate
python3 run_heldout_concurrent.py --tag heldout-c4-candidate-instrumented-1 --variant instrumented --engine-version candidate
python3 summarize_candidate.py
```

The exporter is independently replayable from retained raw artifacts:

```bash
export QUERY_STUDY_ROOT=/absolute/path/to/query-study
export EVIDENCE_OUTPUT=/absolute/path/to/output
python3 benchmarks/chemistry/harness/public_candidate_evidence.py
```

The public ZIP includes35sanitized members covering baseline, both candidate pilots, both candidate repeats and all three concurrent runs: unchanged numeric resource/stage counters, lifecycle/batch boundaries, request timings/volumes and864ordered-response audits (including warmups). Member hashes link to original raw source files. Process IDs, addresses, paths, service logs, raw request bodies and full returned documents are excluded. Source, profiler implementation, original harnesses, models and executables remain local; their absence limits independent replay from the public ledger alone. A deterministic re-export, ZIP CRC/member SHA checks, JSON/AST checks, local Markdown links, file line limits, `make fmt` and `git diff --check` validate publication.

The exact-query optimization gate is complete for these tests and this corpus. Candidate application source remains local pending publication approval. Generic typed storage and optional ANN remain separate implementation/feasibility gates; no measured claim from this experiment applies to them.
