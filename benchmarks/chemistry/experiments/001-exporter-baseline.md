# 001: historical exporter baseline

Status: completed historical experiment; backfilled 2026-10-12.

## Change and headline

Quickwit `681733774139d965c89f81cc8a8cb58d572ff674` corrected an ingestion
persistence timeout/replay defect from `7ff976b4a2c500ef3db18554eb0363a295bcdf5b`.
Fresh final-head runs then compared the full descriptor contract. Quickwit still
required an external Cheminee preparation exporter. Full Quickwit wall time was
1,762.90 s including exporter and settle, versus Cheminee 573.92 s. CPU was
2,875.07 versus 2,012.77 core-seconds. Service-only Quickwit is not the full path.

## Revisions, workload and commands

Cheminee `f8d31a604203392f4dfba7d9a84120100b8426b5`; bindings
`0ae060c9cfc14626172070989fee890b16454373`. Use the historical 100k MOSES input,
flat descriptor_v1 schema and package/model versions in [methods](../METHODS.md).
Intel Xeon Platinum 8573C, four-core quota, five visible CPUs, 14 GiB, local
file storage. No remote storage or concurrent engines.

One fresh 100k run per engine: B1000/C1. Cheminee bulk requests commit normally;
Quickwit used `POST /api/v1/moses/ingest?commit=force`, one-second commit timeout.
The exporter calls Cheminee `batch_doc_creation`; it is part of the required
Quickwit path. After the searchable barrier, observe stable file inventories
(three five-second comparisons, 120-second bound) and another 20 seconds idle.
These are recorded procedures, not a claim that the unavailable historical
harness can be reconstructed byte-for-byte from this backfill.

## Correctness and stages

Both engines accepted 100,000/rejected 0. Full restart readback found 100,000
unique IDs, no missing IDs, duplicates or content mismatches. The defect
reproduction previously produced 8,000 rows for 4,000 IDs. Three paused-clock
regressions fail before the correction and pass after it. This is not an
exactly-once guarantee for arbitrary client retries or power loss.

| Observation | Cheminee | Quickwit |
|---|---:|---:|
| Active service peak RSS MiB | 2,761.38 | 283.74 |
| Loaded restart idle RSS MiB | 139.06 | 69.20 |
| Post-query recovery RSS MiB | 416.92 | 123.22 |
| Settled engine allocated MiB | 168.93 | 404.57 |
| Live geometry | 300 committed segments | 1 published split |

Quickwit's exporter separately took 466.12 s / 1,681.43 core-s and peaked at
2,290.16 MiB RSS. Its prepared staging file was 204,287,270 bytes; do not sum
nonconcurrent process peaks. The short settle did not wait out the 32-minute
obsolete-split grace. Cache, WAL, obsolete files and staging remain real costs.
Fine-grained thread CPU ownership was not collected in this historical study.

Quickwit first graph queries were 14.889–16.268 s; exact similarity 2.685–3.186 s.
Repeated queries benefit from result caching. Cheminee default approximate
similarity was roughly 150–165 ms warm, with some threshold recall only 54/123,
2/5 or 3/8. Its exhaustive attempt timed out at 60 s. Quickwit rejected a
non-fast NumHeavyAtoms range. Those are different query contracts, not an
unqualified equal-recall speed comparison.

## Evidence and limitations

The [public source report](https://github.com/rdkit-rs/quickwit-cheminee/pull/3#issuecomment-6105612933)
contains detailed tables and methodology. Historical raw traces and exact
commands are not attached to this backfill; source-comment figures are retained
as historical observations, not new reruns. [Final-head CI](https://github.com/rdkit-rs/quickwit-cheminee/actions/runs/38109308153)
and [chemistry CI](https://github.com/rdkit-rs/quickwit-cheminee/actions/runs/38109308243)
passed. Dependency review was unsupported by repository settings; no settings
were changed. No 1M-molecule benchmark was completed.
