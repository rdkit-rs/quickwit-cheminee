# Chemistry benchmark ledger

This ledger separates measured experiments by code, schema and timing boundary.
It is a workload-specific engineering record, not a general product ranking.
Milestones are tracked in [issue 5](https://github.com/rdkit-rs/quickwit-cheminee/issues/5).
Reports are append-only once reviewed: corrections should be new dated addenda
that cite the affected experiment. Repetitions belong to their experiment.

## Chronological index

| Experiment | Changed | Headline and limits |
|---|---|---|
| [001: exporter baseline](experiments/001-exporter-baseline.md) | Ingestion timeout/replay correction; final fresh baseline | Full Quickwit path included a required exporter; service-only time understates cost. |
| [002: historical batching](experiments/002-historical-batching.md) | Batch size, concurrency and Cheminee Rayon width | Quickwit auto/B200/C1 improved service latency; full preparation remained external. |
| [003: native preparation](experiments/003-native-preparation.md) | Full in-process descriptor preparation and reuse | 15% less CPU and 79% less peak RSS than matched Cheminee, but 48% longer searchable latency. Flat schema. |
| [004: nested descriptors](experiments/004-nested-descriptors.md) | Explicit nested fast JSON descriptor layout | Correctness and CI passed; no nested-schema performance measurement. |
| [005: runtime configuration](experiments/005-runtime-tuning.md) | CPU hint, batching and commit timeout; two controls per setting | Selected setting 22.7% faster to searchable, with 9.1% more CPU and higher RSS; full 43-minute lifecycle observed. Flat schema. |
| [006: eager query costs](experiments/006-eager-query-costs.md) | Result/predicate caches disabled; repeated control and instrumented queries | Empty metadata filters still decode and score the full dictionary. Candidate-first comparison pending. |

Experiment 005 uses the same flat-schema revision as 003. Do not compare its
settings against unmeasured nested-schema timings or attribute schema changes
to tuning.

## Reading the evidence

- [Physical schema and scoring differences](SCHEMA-AND-SCORING.md)
- [Common methods and provenance](METHODS.md)
- [CPU configuration diagnosis](CPU-CONFIGURATION.md)
- [Experiment template](TEMPLATE.md)
- [Proposed next experiments](NEXT.md)
- [Native baseline metrics](evidence/003-native-metrics.json)
- [Runtime tuning metrics](evidence/005-tuning-metrics.json)
- [Eager query-cost metrics](evidence/006-eager-query-metrics.json)
- [Eager query counter traces](evidence/006-eager-query-traces.zip)
- [Sanitized timing and CPU traces](evidence/005-counter-traces.zip)

Public source comments and CI links are cited in each report. Small sanitized
metric files preserve values and boundaries. Experiment 005 includes sanitized raw counter traces. Complete original logs,
readback payloads, instrumentation binaries and historical harness bundles remain
outside this ledger; their absence limits independent replay.
No private artifact links are required to read this ledger.

Quickwit chemistry is one executable with in-process mapping and search. It
loads RDKit and TensorFlow libraries; it requires no separate preparation
service. Optional distributed Quickwit services and remote storage are separate
deployment choices. The historical exporter was a benchmark-path limitation,
not the architecture of the completed native implementation.
