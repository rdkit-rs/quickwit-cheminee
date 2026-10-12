# 005: flat-schema runtime configuration tuning

Status: completed with bounded lifecycle evidence. Date: 2026-10-12 UTC.

## Change and headline

The selected configuration is **H12 / B200 / commit 10s**, chosen by lowest mean
raw-to-searchable time among five configurations with two uninstrumented fresh
100k runs each. Mean searchable latency changed from 487.82s to
376.86s (-22.7%); process CPU changed from
1023.09 to 1115.83 core-seconds (+9.1%).
Mean per-run peak sampled RSS changed from
662.44 MiB to
846.27 MiB.
These are workload-specific configuration effects at a frozen flat-schema revision,
not a nested-schema, vector-storage or ANN result. Two repetitions expose spread,
not a precise confidence interval or a universal optimum.

## Exact comparison

Measured Quickwit revision: `7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b`.
The uninstrumented binary SHA-256 is
`ec0873f6b39bddb380fb64cfc407ec23e6f01f070df33bd0809d11521db6c7e9`.
Instrumented binaries use that revision plus the retained measurement overlay;
their binary hashes and stage definitions are in the evidence. Neither PR3's
later nested-descriptor head nor the vector prototype was executed here.

The same 100k deterministic MOSES records, raw SMILES/searchable metadata,
`descriptor_v1`, models, normalization, 43 descriptors, both fingerprints,
scaffold IDs, learned clusters and error behavior are retained. Raw input SHA-256:
`9a63bf25bc02ba3c965bb050cd74ba1a059bc362b8fb210b8febb6a326ce2e5e`.
The [first-10k fingerprint identity proof](../evidence/canonical-first10k.json)
confirms byte identity with the independent Lucene fixture; this is not a
performance comparison across different boundaries or hardware.
[Methods and dependency hashes](../METHODS.md) and
[physical schema/scorer differences](../SCHEMA-AND-SCORING.md) still apply.
Unchanged Cheminee is the baseline in experiment 003; it was not rerun or modified
for this Quickwit-only configuration experiment. Do not mix old exporter-dependent
service-only timings or different-host ratios into these configuration deltas.

AMD EPYC 9V74, Ubuntu 26.04, dynamic RDKit 2026.09.1 package, TF CPU 2.15.1,
four-core quota (`cpu.max=400000 100000`), 14 GiB memory, single node and local
`file://` storage. Five CPUs are visible (affinity 0-4); quota remains four.
Every run fixes main Tokio threads 2, indexer capacity 4000m, merge concurrency 2,
and upload concurrency 12. TF/OMP/Rayon thread overrides remain unset.
`QW_NUM_CPUS` changes the small-task pool and actor pools together: hints 4/9/12
select 2/3/4 small-task workers. It is not an isolated chemistry-worker control.
All full runs use one HTTP client; batch size and commit timeout are in the table.
H denotes QW_NUM_CPUS and B denotes documents per request.

## Commands and repetitions

Use the [versioned harness](../harness/README.md). Runs were sequential, with no
other engine/build, fresh index paths and no retries. Order: baseline1, hint9-1,
hint12-1, B1000-1, hint12/10s-1, hint12/10s-2, B1000-2, hint12-2, hint9-2,
baseline2, baseline-instrumented, selected-winner-instrumented. Instrumented
follow-up selection uses these same controls; it is not an independent holdout.
Each completed service is stopped before full readback and query audits and the
next service starts only after those audits and evidence compression finish.

Example:

```sh
python3 run_case.py quickwit --tag UNIQUE --size 100000 --batch 200 \
  --concurrency 1 --cpu-hint 4 --commit-seconds 30 --boot-idle 30 \
  --lifecycle-seconds 60
```

The selected instrumented follow-up observes 2580 seconds
after searchable completion, covering the default 32-minute deletion grace and
ten-minute GC cadence. It does not force merges or delete files manually.

Eight clean 10k screens preceded the full runs. Hint24 and client concurrency 4
were not promoted. Small-run publication timing is strongly quantized by commit
phase; these screens are not 100k results. One B1000 screen overlapped formatting/
toolchain installation and is excluded; its clean repeat is retained. One guard
rejected a zombie compiler before launching any engine. Both attempts remain
identified in evidence; neither is silently overwritten. A pre-launch capacity
check was added while the seventh full run was already active and applies to
subsequent launches, outside measured intervals:
512 MiB of working room plus a 2 GiB filesystem reserve. It does not change the
100k workload, binaries or measured settings.

## Correctness and durability

All 12 full runs accepted 100,000 documents with zero rejections, passed full
restart readback of stored SMILES, Morgan, Pattern and metadata, and passed 26
query checks including expected unsupported-range errors. These query timings
are correctness probes, not a repeated query-performance experiment. The flat
schema does not store all 43 numeric descriptors; full preparation-value parity
is established separately by experiment 003 at the unchanged binary/profile.
Readback verifies document cardinality, unique IDs and content after shutdown;
it is not a power-loss durability test. Short-run shutdowns may reach the bounded
wait and require SIGKILL; exact flags/exit codes are retained per run.

## Uninstrumented results

Values are mean [minimum, maximum] across two fresh-index repetitions. CPU is
process user+system core-seconds; RSS is the sampled per-run process peak.
Acceptance and publication tail sum to searchable wall time; overlapping rows
or process-memory snapshots must never be summed.

| Configuration | Acceptance s | Acceptance average cores | Searchable s | CPU core-s to searchable | Peak RSS MiB |
|---|---:|---:|---:|---:|---:|
| H4 / B200 / commit 30s | 462.77 [460.80, 464.74] | 2.21 [2.21, 2.21] | 487.82 [486.78, 488.85] | 1023.09 [1016.64, 1029.54] | 662.44 [650.96, 673.93] |
| H9 / B200 / commit 30s | 383.19 [383.18, 383.19] | 2.79 [2.79, 2.80] | 398.22 [397.22, 399.22] | 1071.05 [1068.59, 1073.50] | 719.12 [706.57, 731.66] |
| H12 / B200 / commit 30s | 371.70 [370.94, 372.46] | 3.00 [3.00, 3.01] | 397.75 [394.99, 400.52] | 1116.61 [1116.35, 1116.88] | 772.95 [744.05, 801.85] |
| H12 / B1000 / commit 30s | 382.56 [379.23, 385.89] | 3.00 [3.00, 3.00] | 393.59 [391.26, 395.92] | 1148.97 [1139.83, 1158.11] | 851.31 [840.37, 862.26] |
| H12 / B200 / commit 10s | 370.84 [370.15, 371.52] | 3.01 [2.99, 3.03] | 376.86 [374.17, 379.55] | 1115.83 [1111.55, 1120.11] | 846.27 [840.91, 851.63] |

The evidence also preserves per-run PSS, process I/O deltas, cgroup throttling and
memory-event counters, approximately 10-second CPU/RSS/PSS bins, boot/publication/
lifecycle boundaries, thread/mmap/file counts, split populations and body bytes.
The count barrier can use metadata without fully loading query columns; it is
not a separately measured loaded-query idle state. Experiment 003 contains the
earlier boot/loaded/active-query measurements.
Body bytes divided by first-request-start to last-acknowledgement is an application
transfer rate including chemistry/backpressure, not network capacity. Input
serialization/setup and intentional boot idle are outside searchable timing and
reported separately. Setup-controller CPU is recorded separately. Main CPU totals
cover the service process, not the HTTP client/sampler; cgroup deltas additionally
include container-side measurement work. Uploads here are local file operations.

## Instrumentation and lifecycle

The overlay uses exclusive per-thread CPU clocks with async and worker-pool
attribution. The table reports a common interior snapshot window for each run;
boundary and same-window clock residuals remain explicit in JSON. Stage 0 retains
shared/unclassified runtime and some cleanup; grouped labels are not claims of
perfect fine-grained ownership. CPU values are not elapsed span durations.

| Stage | Baseline instrumented core-s | Selected instrumented core-s |
|---|---:|---:|
| shared_runtime_input_and_unclassified_including_some_cleanup | 1.879 | 2.303 |
| input_rest_routing | 0.085 | 0.092 |
| chemistry_normalization_and_preparation_overhead | 464.197 | 500.491 |
| numeric_descriptors | 96.265 | 101.923 |
| fingerprints | 30.546 | 33.218 |
| scaffold_matching | 21.766 | 24.199 |
| learned_cluster_and_tensorflow_workers | 422.565 | 451.508 |
| ingest_validation_envelope_and_wal | 1.666 | 1.789 |
| schema_and_document_mapping_including_validation_mapping | 7.653 | 8.041 |
| indexing_writer_commit_and_attached_workers | 3.512 | 3.377 |
| serialization_and_packaging | 1.356 | 1.416 |
| upload_and_publication | 0.469 | 0.804 |
| background_merging_instrumented_scopes | 2.242 | 4.455 |
| active_query_execution | 0.009 | 0.004 |
| instrumentation | 0.032 | 0.031 |

| CPU reconciliation, core-s | Baseline | Selected |
|---|---:|---:|
| Attributed interior window | 1054.243084 | 1133.651369 |
| Interpolated process CPU, same window | 1054.186804 | 1133.649745 |
| Same-window clock residual | -0.056281 | -0.001624 |
| Boundary plus reconciliation residual | 1.736916 | 2.498631 |

| Overhead control | Wall change vs matched control mean | CPU change vs matched control mean |
|---|---:|---:|
| Baseline | -0.02% | +3.21% |
| Selected | -1.18% | +1.82% |

These observed differences include ordinary run variability; do not subtract them
as an exact universal instrumentation correction. Owned allocation attribution
was not reprofiled for each configuration. RSS/PSS are shared process snapshots,
not stage-owned memory and not additive. Retained index bytes, mmap counts and
stage CPU answer different questions.

Baseline: observed 60.01s after publication, 0.180 process core-seconds, splits {'Published': 7, 'MarkedForDeletion': 10} at searchable and {'Published': 7, 'MarkedForDeletion': 10} at the observation end. Forced shutdown: True; exit code: -9.

Selected long observation: observed 2580.02s after publication, 6.990 process core-seconds, splits {'MarkedForDeletion': 30, 'Published': 8} at searchable and {'Published': 8} at the observation end. Forced shutdown: False; exit code: 0.

All 30 obsolete splits were first absent at the sampled boundary **2010.21 seconds (33.50 minutes)** after searchable completion. Transitions are sampled every 30 seconds, so this is an observation boundary, not an exact deletion timestamp. The eight retained published splits contain 8 internal Tantivy segments and 64 internal files, totaling 48,065,742 bytes.

The final node/index inventory has 79 distinct file inodes: 364,406,146 logical bytes and 119,922,688 allocated bytes, including sparse/runtime files. The process has 368 mappings, 202 file-backed mappings across 41 unique files, and 24 open descriptors; these counts include libraries and are not index-segment counts.

The long observation consumed 6.99 service CPU core-seconds versus 30.30 cgroup core-seconds, which also include container-side sampling and lifecycle HTTP probes. Most idle/cleanup service CPU remains grouped in stage 0; stage 12 alone is not the complete GC cost.

The long run's timestamped transitions establish which obsolete splits were
actually deleted. Short controls are not fully cleaned storage measurements.
Two-day split maturation means even a 43-minute observation does not establish a
permanent merge fixed point. File inventories deduplicate shared local inodes;
internal segment geometry is read from retained split metadata. Missing files
after shutdown are flagged, not assigned invented segment counts.

## Evidence and limits

[Machine-readable metrics](../evidence/005-tuning-metrics.json) preserve run IDs,
controls, stages, boundaries, CPU timelines, lifecycle transitions, inventory
counts, audits, binary/input/oracle hashes and retained raw-evidence checksums.
[Sanitized counter traces](../evidence/005-counter-traces.zip) and their
[archive checksum](../evidence/005-counter-traces.json) permit independent timing/
CPU reconstruction. Numeric resource/stage counters and request/split transitions
are retained; process IDs, memory addresses, local paths, logs and molecule
payloads are excluded.
Each member records its own hash and its original source hash.
Stored-audit NDJSON is losslessly compressed only after service/audit completion;
its decompressed SHA-256 is verified. Historical evidence is unchanged. Complete original process snapshots, logs and readback payloads remain outside
this documentation PR; checksums alone do not make those omitted fields
independently inspectable. No private artifact links are required.

These are local 100k, flat-schema results with two control repetitions and one
instrumented follow-up per selected/baseline configuration. Larger corpora,
object storage, nested-schema performance, candidate-first/typed exact and ANN
remain separate experiments in [tracking issue 5](https://github.com/rdkit-rs/quickwit-cheminee/issues/5).
