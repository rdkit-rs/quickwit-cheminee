# CPU configuration diagnosis before tuning

This is source/configuration analysis of experiment 003, not another timing run.
The relevant runtime, validation and model files are unchanged between measured
`7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b` and nested head
`6bf1e29cdbf03409287b2f7d0e59a4c19534d8fa`.

The container has `cpu.max=400000 100000`, 14 GiB memory, affinity/effective cpuset
`0-4`, and no Docker cpuset pin. Five visible logical CPUs do not change the
four-core quota. Effective baseline scheduling capacity is 4000m. No runtime
thread overrides appear in retained launchers or container environment; a complete
historical per-process environment dump was not retained.

| Runtime component | Baseline width or behavior |
|---|---|
| Quickwit main Tokio runtime | 2 threads |
| Quickwit blocking/nonblocking actor runtimes | 3 / 1 threads |
| Quickwit small-task CPU pool used by chemistry validation | 2 workers |
| Quickwit merge concurrency / split uploads | 2 / 12 |
| Quickwit active measured ingest pipeline | one shard/pipeline; B200/C1 |
| Quickwit model sessions | shared; mutex held across encoder/ranking call per molecule |
| Cheminee global Rayon chemistry pool | default 4 threads |
| Cheminee Tantivy writer | 3 workers from the 50 MiB memory budget |

`run_cpu_intensive` uses the small-task pool sized `max(num_cpus()/3, 2)`.
The validation closure's Rayon parallel iterator runs inside that pool. Thus
four-core quota did not mean four chemistry workers. `RAYON_NUM_THREADS=4`
does not override its explicit `num_threads` setting.

`QW_NUM_CPUS=12` makes this pool four workers but also changes actor runtimes to
10 blocking / 2 nonblocking. It is a global capacity hint, not a dedicated
chemistry-worker control. The configuration study pins main Tokio threads to 2,
indexer scheduling capacity to 4000m, merge concurrency to 2 and uploads to 12,
but other pool changes remain a confounder. The kernel quota is unchanged.
`QW_NUM_CPUS=9` gives three small-task workers; 24 gives eight.

A single ingester holds its full-state/WAL lock while awaiting document
validation. More concurrent clients can queue behind that critical section.
Document mapping and single-segment writing are serial actor work; the latter
accounted for only about 3.5 core-seconds per 100k, versus roughly 98% of total
CPU in chemistry. TensorFlow's effective internal worker width was not directly
measured; a session mutex is not evidence that all model work uses one thread.

Baseline control means were 2.13 service cores Quickwit and 3.72 Cheminee.
Quickwit had zero quota-throttled periods in both control searchable intervals;
Cheminee was frequently throttled. This supports a useful-parallelism bottleneck,
not a claim that the container silently imposed a two-core quota. CPU scopes
cannot measure lock-wait wall time by subtraction.

A dedicated quota-sized chemistry pool/setting is proposed in [next work](NEXT.md).
No such control has been implemented as part of the existing-knob study.

Sources at the measured revision:
[small-task pool](https://github.com/rdkit-rs/quickwit-cheminee/blob/7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b/quickwit/quickwit-common/src/thread_pool/simple.rs#L99),
[validation dispatch](https://github.com/rdkit-rs/quickwit-cheminee/blob/7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b/quickwit/quickwit-ingest/src/ingest_v2/doc_mapper.rs#L98),
[actor runtimes](https://github.com/rdkit-rs/quickwit-cheminee/blob/7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b/quickwit/quickwit-common/src/runtimes.rs#L88),
[model synchronization](https://github.com/rdkit-rs/quickwit-cheminee/blob/7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b/quickwit/tantivy-rdkit-mapper/src/cluster.rs#L44).
