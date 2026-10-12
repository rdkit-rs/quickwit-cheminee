# 002: historical batching and concurrency

Status: completed historical experiment; backfilled 2026-10-12.

## Change and headline

Only batch/concurrency/commit policy and a separate Cheminee Rayon limit changed.
Quickwit stayed at `681733774139d965c89f81cc8a8cb58d572ff674`; Cheminee and
bindings stayed at the revisions in [methods](../METHODS.md). The same historical
100k flat-schema workload and Intel/four-core/14 GiB/local-file setup were used.
There were 13 fresh 10k screens and five fresh 100k runs. Quickwit auto/B200/C1
was 2.10 times faster in service-to-searchable wall time than the force/B1000/C1
configuration. Multiple settings changed; this is not a single-variable effect.

## Repetitions and results

| 100k configuration | n | Searchable seconds mean (range) | Mean service cores | Docs/s from mean |
|---|---:|---:|---:|---:|
| Quickwit B200/C1 auto/30 s | 2 | 607.64 (590.56–624.72) | 1.98 | 164.57 |
| Cheminee B1000/C1 Rayon-2 | 2 | 722.91 (709.93–735.88) | 2.64 | 138.33 |
| Cheminee B1000/C1 default | 1 | 570.53 | 3.65 | 175.28 |

Quickwit service CPU averaged 1,203.80 core-s. Adding the separately measured
466.12 s / 1,681.43 core-s exporter and recorded setup gives **1,079.75 s**
end-to-end. Default Cheminee including setup was **573.96 s / 2,082.19 core-s**;
Rayon-2 Cheminee was 727.55 s. Rayon-2 still used 33% more CPU than Quickwit:
CPU matching did not succeed and no equal-CPU claim is justified.

| Repetition | Searchable s | Service CPU core-s | Peak RSS MiB |
|---|---:|---:|---:|
| Quickwit 1 | 590.56 | 1,184.44 | 204.96 |
| Quickwit 2 | 624.72 | 1,223.16 | 305.75 |
| Cheminee Rayon-2 1 | 735.88 | 1,924.60 | 3,023.43 |
| Cheminee Rayon-2 2 | 709.93 | 1,885.73 | 3,033.92 |
| Cheminee default 1 | 570.53 | 2,082.19 | 3,067.29 |

HTTP bodies were 160.30 MiB Quickwit versus 20.92 MiB Cheminee. These are
expanded versus raw inputs, not network capacity. Quickwit had 20 obsolete
splits plus one/two published splits after the short observation. Cheminee had
300 live segments. The 32-minute deletion grace was not observed to completion.

## Commands, correctness and rejected attempts

The effective Quickwit request is
`POST /api/v1/moses/ingest?commit=auto`, B200/C1, 30-second index commit timeout,
followed by the all-searchable count barrier. Cheminee uses B1000/C1;
`RAYON_NUM_THREADS=2` applies only to the explicitly labeled Rayon-2 rows.
No source optimization was made. Historical executable harness files are not
included here; the public source supplies the complete configuration matrix.

All five full runs accepted 100k/rejected 0 and passed complete stored-record
unique-ID/content audits. Both Quickwit repetitions also passed restart audits.
The Cheminee B1000/C2 screen failed with HTTP 500 LockBusy after one accepted
batch; 8k rows were unsent and no retries concealed the failure. All seven
Quickwit screens passed 10k audits. Two accidentally overlapping orchestration
attempts were excluded and rerun, as disclosed in the source report. No completed
run recorded an OOM. There were too few repetitions for a production distribution.

Fine-grained stage allocation/CPU ownership was not measured. The exporter and
service remain separate measured stages, and their nonconcurrent RSS peaks are
not added. Query performance was not newly swept by this batching experiment.

## Evidence

[Public source report and full screening matrix](https://github.com/rdkit-rs/quickwit-cheminee/pull/3#issuecomment-6106393236).
This immutable backfill preserves the historical boundary. It is separate from
[003](003-native-preparation.md), which receives raw SMILES directly and performs
all preparation in process on a different CPU host.
