# 003: full native preparation, flat schema

Status: completed; backfilled 2026-10-12.

## Change and headline

All descriptor_v1 preparation moved into Quickwit's process, with prepared-output
reuse through validation and mapping. Raw SMILES plus searchable metadata is the
ingestion input for both engines. Learned-cluster fields, normalization,
fingerprints, scaffolds, descriptors and validation were retained.

Measured Quickwit: `7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b`, based on
`681733774139d965c89f81cc8a8cb58d572ff674`. Preparation implementation:
`b960bb517833dc8f87ebefde1618c3afc7a391f3`; delivery
`1ac653e6d6ef23f894adb40a56b88fbc7c9daf4e` only adds generated license records.
Cheminee/bindings remain the [common revisions](../METHODS.md). This is flat
schema, not the later nested-descriptor head.

**Physical schemas and scoring algorithms differ:** Cheminee reads stored Morgan
bytes after learned-cluster routing; Quickwit scores a bytes fast-field dictionary
exhaustively. See [schema/scoring audit](../SCHEMA-AND-SCORING.md). These results
do not isolate the engine from storage, routing or retrieval choices.

## Protocol and repetitions

AMD EPYC 9V74, four-core quota, five visible CPUs, 14 GiB, local file storage.
Use the recovered raw file/hash and dependencies in methods. Quickwit B200/C1,
auto commit, 30-second timeout; Cheminee B1000/C1, default threads. Each has two
fresh uninstrumented runs and two fresh CPU-instrumented runs, sequentially.
A full stored audit follows each run. Payload construction is separately timed;
model initialization and all chemistry are inside the raw-to-searchable interval.

| Engine/variant | n | Mean searchable s (range) | Mean CPU core-s | Mean per-run peak RSS MiB |
|---|---:|---:|---:|---:|
| Cheminee control | 2 | 328.01 (319.49–336.54) | 1,219.51 | 3,208.47 |
| Quickwit control | 2 | 485.65 (484.81–486.48) | 1,036.58 | 674.19 |
| Cheminee instrumented | 2 | 324.13 (322.84–325.42) | 1,202.20 | 3,282.59 |
| Quickwit instrumented | 2 | 486.70 (485.35–488.05) | 1,037.49 | 669.99 |

Quickwit uses 15.00% less CPU and about 79% less peak RSS, but takes 48.06% longer.
Average service use is 2.13 versus 3.72 cores. With payload setup: 486.29 versus
328.43 s. HTTP request bodies: 22,421,752 versus 20,033,857 bytes.
Instrumentation differences (+0.22% Quickwit wall, -1.18% Cheminee wall) include
ordinary variance; negative overhead is not acceleration evidence.

## CPU ownership and memory

| Instrumented ownership mean, core-s | Cheminee | Quickwit |
|---|---:|---:|
| Shared runtime/unclassified | 0.476 | 1.918 |
| REST/routing | not separated | 0.087 |
| Normalization/preparation overhead | 436.493 | 458.543 |
| Numeric descriptors | 89.470 | 94.263 |
| Fingerprints/validation work | 25.153 | 30.037 |
| Scaffolds | 83.929 | 21.605 |
| Learned cluster/TensorFlow | 355.005 | 412.787 |
| Validation/WAL envelope | not separated | 1.536 |
| Mapping | 1.142 | 7.384 |
| Writer/commit/attached workers | 206.208 | 3.519 |
| Serialization/packaging | grouped above | 1.340 |
| Local upload/publication | grouped above | 0.454 |
| Instrumented background merge | not separated | 2.210 |
| Barrier query | 0.320 | 0.016 |
| Profiler sampler | 0.031 | 0.031 |
| Boundary/reconciliation residual | 3.979 | 1.753 |

These are actual exclusive thread CPU clocks, not elapsed spans. Native chemistry
is about 98% of indexing CPU. TensorFlow's approximately 40% share does not imply
a guaranteed 40% wall-time saving if replaced. Native session calls are serialized
per molecule; Cheminee encodes groups of 200. Model operations/results match.

Separate 1k heaptrack experiments measured one global live-heap peak:
2,333,523,459 bytes Cheminee and 110,865,385 Quickwit. These heavily perturbed
profiles are not 100k allocations or throughput controls. Full-scale owned
allocation and query-owned allocation traces were not collected. RSS/PSS is
shared process memory. Some Cheminee repetitions recorded cgroup reclaim-pressure
max events; none recorded OOM/OOM-kill. Stage peaks are never summed.

## Lifecycle and correctness

One Quickwit instrumented run observed 2,580 s after searchable completion,
using 5.44 additional CPU core-s. All ten obsolete split files were physically
deleted. Final state: seven published splits, seven internal segments, 56
internal files. Published allocated bytes 48,406,528; live cache 48,291,840;
WAL 23,777,280; sparse queues 8,192. Deduplicated total 120,483,840 bytes.
Other repetitions observe only 60 s; their retained files are not fully cleaned
storage. Normal two-day maturation remains. No forced merge or manual deletion.

Cheminee control 1 has 300 live segments/1,800 live files, 101,523,456 live
allocated bytes, but 2,729,033,728 bytes for the entire directory including
unreferenced/temporary files. This is not a pure codec comparison.

All 100k prepared documents matched the Cheminee oracle. Eight full stored audits
found no missing IDs, duplicates or mismatches. REST descriptor checks (352) and
independent graph checks (1,050) passed. Across 954 query requests, 932 successes
had valid results; 22 expected HTTP 400s covered the non-fast range limitation.
Native exact totals/global stable top-k match independent corpus truth.

Default Cheminee threshold recall for seed 1/0.3/limit 10,000 was 54/123 (43.90%);
Quickwit returned all 123. At limit 100 the Cheminee exact-top100 overlap was 46%.
A separate restarted OS-warm exhaustive request (n=1) took 38.920545 s/39.56 CPU
for Cheminee with 100% clusters, versus 1.068571 s/1.81 CPU for Quickwit. Both had
valid tie-aware exact top100; this is not a repeated equal-quality benchmark.
Repeated native queries can hit result caches. Warm latency is not fresh-scan
throughput. Loaded idle RSS/PSS MiB: Cheminee 282.75/280.26, Quickwit 324.71/322.97;
loaded mmap counts 278/318. These are process snapshots, not stage allocations.

## Commands and evidence

Release build: `cargo +1.96.1 build --release --locked -p quickwit-cli --features descriptor-v1 --bin quickwit`
using the repository's Kerberos/C23 wrapper and verified dynamic libraries.
Launch all required roles in one process with local node/index configuration;
POST raw documents to `/api/v1/moses/ingest?commit=auto&detailed_response=true`;
poll `/api/v1/moses/search?query=*&max_hits=0` for 100,000. No exporter runs.
Cheminee launches `rest-api-server` with a local index directory and receives
raw `docs` at `/v1/indexes/moses/bulk_index` on descriptor_v1.

[Sanitized per-repetition/stage metrics](../evidence/003-native-metrics.json) retain
CPU reconciliation and boundaries. [Public completion report](https://github.com/rdkit-rs/quickwit-cheminee/pull/3#issuecomment-6112515642)
is the source record. Large raw traces and overlay sources are not attached to
this backfill; their absence limits independent instrumentation replay. Hardware,
metadata serialization, historical lockfile and query-mix recovery differences
prevent causal comparisons with exporter-era timings. Historical figures remain
in experiments 001/002.
