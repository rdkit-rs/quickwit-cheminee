# Native local Compose experiment

Final discriminatory run: `compose-native-reviewed.json` (passed; optimized Python is refused).
1,000 synthetic offers form four equal groups: Acme target enantiomer, Acme opposite
enantiomer, Acme ethanol, Beta target enantiomer. Strict supplier+chiral identity
returns 250; disabling chirality returns 500; unfiltered identity returns 500.
Counts and first ten ordered IDs agree before and after graceful container restart.
This catches chemistry being ignored inside the supplier candidate domain.

The image is 305,602,041 bytes, built from the source-attributed native binary for
`8009925c` and pinned Ubuntu base; copied runtime hashes are retained. Compose uses
2 CPUs, a 768 MiB hard container ceiling, and the test index uses a 32 MiB indexing
heap. These are experimental bounds, not recommended production capacities.

One reused-host run, not a benchmark: one 1,000-document wait-for import took 6.012 s.
Twenty strict requests had median 24.16 ms and maximum 33.05 ms including HTTP.
No client concurrency, corpus diversity, tail quantiles or stage-cost attribution
was measured. Native code is a stripped debug build. No speed comparison follows.

| Phase | Process RSS MiB observed | Cgroup current MiB observed | Samples |
| --- | ---: | ---: | ---: |
| Idle | 140.62–140.62 | 20.61–22.46 | 6 |
| Import | 141.60–147.96 | 22.72–28.95 | 10 |
| Query | 146.00–146.00 | 26.04–26.04 | 1 |
| Restart | 118.83–146.25 | 15.53–26.31 | 25 |
| Post-restart query | 135.23–135.23 | 19.85–19.85 | 1 |

Largest observed process high-water: 149.70 MiB; largest sampled cgroup peak:
28.95 MiB; no sampled OOM/OOM-kill events. Cgroup charging and process RSS differ
substantially on this reused host: file-backed/shared pages may be charged elsewhere.
**The cgroup figure is not a standalone service RAM requirement.** Sampling can miss
short intervals, incurs measurement-process overhead, and restart resets some peaks.

Run1 exposed node-ready preceding searcher membership. Final run recorded three
HTTP500 startup read errors, then exact reads succeeded. The smoke retries only
that recognized read error with a deadline; ingestion is never retried. Node readiness
alone does not prove a catalog searchable. Earlier weak fixtures are retained as
historical execution evidence; only the final fixture challenges identity and chirality.

Elasticsearch coexistence, representative parallel load, abrupt loss/corruption,
HA, storage amplification, backup/cleanup and production tuning are unmeasured.
Under 1 GiB workspace free space prevented safely adding an Elasticsearch image.
No larger corpus run or publication occurred.
