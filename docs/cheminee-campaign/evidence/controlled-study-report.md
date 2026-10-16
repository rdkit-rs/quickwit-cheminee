> **Recovered historical report — not rerun or independently revalidated here.**
> Source: Library `libfile_470ec6694a7c8191abbbc7bcb86622c9`, version 23,
> recovered through text reads on 2026-10-16. The original report follows unchanged.
> Statements about “fresh” measurements, preserved files and local deliverables
> describe the original study workspace. Its corpus, raw evidence and binary
> archive are **not available in this checkout**. Relative links below point into
> that missing original bundle and will not resolve here. See the
> [current recovery status](README.md) before relying on reproduction claims.

# Controlled Cheminee / Quickwit-Cheminee study

Completed 2026-10-14 UTC. Single node, local storage, four CPU quota, 14 GiB memory, sequential engines, identical immutable 100k MOSES molecule/metadata input. All planned engine measurements and final audits completed.

**Nesting did not reproduce the historical 6:17 versus 8:40 gap.** With frozen tuned settings, Quickwit flat averaged 385.24s and nested 395.88s: +10.64s (+2.76%). Flat with equivalent stored/fast numeric fields averaged 390.94s; nested added 4.95s (+1.26%). The matched-field difference changes sign in the unflagged paired subset, so these small samples do not establish a precise layout-only penalty.

**Standalone was the faster loader in this tested budget.** Its tuned mean was 308.46s, 22.08% less elapsed time than tuned nested Quickwit. Its supported merge/GC added a separately measured 3.06s on average. Quickwit used substantially less ingestion process memory: mean sampled peak RSS 979.3 MiB versus standalone 2986.0 MiB. Query behavior has important tradeoffs below; no single overall winner is implied.

This is a fresh published-method reconstruction. The private Library archive `libfile_46443053feb48191bdab2fdda71126be` resolved in metadata but produced no readable bytes through the supported materializer. Its supplied 519.95s / 1140.35 core-s / roughly 657 MiB figures remain unverified here. The published 376.86s flat result used a different source commit and experiment. Their difference is not a causal nesting A/B, and this study does not establish the private run’s settings or explain its entire elapsed time.

**Pins and experimental control.** Quickwit PR3 `6bf1e29cdbf03409287b2f7d0e59a4c19534d8fa`; Cheminee `f8d31a604203392f4dfba7d9a84120100b8426b5`; ledger `c7698e8b5e1a51f8aa13d290a7640a4896c95fb6`. Shared RDKit adapter `0ae060c9cfc14626172070989fee890b16454373`, RDKit 2026.09.1, Rust 1.96.1, TensorFlow CPU 2.15.1, model 0.1.6. Exact lockfiles, image/package versions, native asset hashes, binaries, source status and commands are retained. Cheminee’s documented dependency override does not change service application source. No composable-query changes, source merge, deployment or source publication occurred.

Corpus SHA-256: `9a63bf25bc02ba3c965bb050cd74ba1a059bc362b8fb210b8febb6a326ce2e5e` (20,032,857 bytes), exactly matching the ledger selection. Both engines ingested raw SMILES and metadata, not offline prepared chemistry. Four 1k smoke cases and flat/nested golden REST checks passed before measurement.

Each engine received five configurations × two valid 10k screens, then one 100k calibration for each of its two leaders. The equal calibration amendment preceded all 100k service runs; one connectivity-overlap screen was retained, excluded and replaced. Settings froze before the 24 measured runs. Standalone selected batch 5000 / Rayon 4, against baseline batch 1000 / Rayon 4. Quickwit selected CPU hint 12 / batch 200 / commit 10s, against baseline hint 4 / batch 200 / commit 30s. The same Quickwit settings served every schema; hint 12 never increased the four-CPU quota. “Best” means best within this equal tested budget, not a global optimum.

**Ingestion.** Three fresh independent indexes per cell, forward/reverse/forward order. Means below include all planned repetitions; bracketed bounds are observed minima/maxima, not confidence intervals. CPU is service-process core-seconds through searchability; RSS is the mean of one-second-sampled per-run peaks in that interval.

| Configuration | Acceptance s | Searchable s [range] | CPU core-s | Peak RSS MiB |
|---|---:|---:|---:|---:|
| Standalone baseline | 353.47 | 355.26 [351.82, 357.41] | 1319.24 | 3229.0 |
| Standalone tuned | 307.13 | 308.46 [299.50, 315.15] | 1123.66 | 2986.0 |
| Quickwit flat baseline | 503.74 | 515.26 [514.30, 516.10] | 1111.64 | 674.8 |
| Quickwit flat tuned | 378.53 | 385.24 [380.85, 387.98] | 1160.06 | 896.9 |
| Quickwit matched-flat baseline | 496.10 | 505.26 [487.21, 514.46] | 1093.58 | 656.0 |
| Quickwit matched-flat tuned | 384.08 | 390.94 [385.73, 398.15] | 1174.66 | 1010.2 |
| Quickwit nested baseline | 509.52 | 526.35 [515.19, 546.52] | 1121.33 | 663.7 |
| Quickwit nested tuned | 390.66 | 395.88 [394.95, 396.91] | 1197.31 | 979.3 |

All 24 measured ingestions accepted and recovered all 100,000 records without rejects. The searchable barrier follows acceptance and includes API/count-response parsing; standalone hydrates basic hits whereas Quickwit returns a count. Publication tails are explicit in the raw summaries. Thirty-second baseline commit timing introduces quantization. Setup/build is excluded: the successful Quickwit build took 654.13s, standalone about 221s with shared build caches; failed attempts are retained, and these are not independent clean-build speed comparisons.

Tuned nested versus production-flat adds 3.21% process CPU and 9.19% sampled peak RSS. Against matched-flat it adds 1.93% CPU; RSS is -3.06%. Thus the production-flat contrast includes added storage/fast-field functionality as well as nesting.

Four primary ingestions overlapped environment/transport notifications and remain flagged. Using only common unflagged repetitions gives two pairs per key tuned contrast: nested minus flat +12.06s (+3.15% mean paired change), nested minus matched-flat +4.41s (+1.15%; individual differences −2.37s and +11.19s), and nested minus standalone +91.23s (+29.94%). Original processes remained alive in observed evidence; that is not a claim that notifications could not affect timing. Query-only events and the parent-reported 23:44 communication error are recorded separately.

**Value and semantic parity.** Independent preparation paths matched all 100,000 rows in 4,900,000 field comparisons: all 43 numeric descriptors, canonical SMILES, Pattern/Morgan fingerprint bytes, metadata, scaffolds and learned clusters. Exact numeric equality held before REST transport. All 29 final stored readbacks passed. The 12 primary nested/matched-flat readbacks checked 51,600,000 numeric values; the additional nested lifecycle readback checked another 4,300,000. Integer transport was exact and floating transport within one ULP. Standalone and legacy-flat do not store all numeric descriptors; their stored audits therefore cover fewer fields, with full preparation equality and indexed probes for all 43 descriptors on eight deterministic IDs reported separately. Scaffolds/clusters are prepared and indexed but not fully stored/read back in Quickwit.

Nine full query suites contain 4,221 requests, with zero correctness failures and 12 expected HTTP 400 legacy-flat NumAtoms/tpsa range errors. Twenty-seven process-cold/warm suites contain 486 additional passing requests. A post-audit verified unique IDs and descending similarity scores across all 4,695 successful preserved responses. Graph truth is exhaustive direct RDKit matching without a fingerprint screen, with identity excluded, chirality false, tautomer expansion off and scaffold routing off. Shared metadata subsets keep graph result sets below 5,000, under Quickwit’s 10,000 returned-hit cap. Exact Tanimoto thresholds, filtered intersections, scores and top-k/ties use independent integer intersection/union truth.

Fingerprint containment demonstrably is only a screen: the extended superstructure query screened 23 candidates but had only 2 direct graph matches (filtered subset 2 versus 1); benzene screened 78,763 versus 77,547 true matches. No screening false negatives appeared in these six frozen queries. Both engines’ audited graph results matched graph truth, not merely screen counts.

Standalone’s approximate cluster routing is separate from exact search. On the four nonempty frozen top 10 truth sets, mean tie-aware recall was 85.0% at 0.1% effort (minimum 60%), and 87.5% at 1% and 10% effort (minimum 70%). Results were identical across the tested baseline, tuned and merged query indexes. Three request repeats per query are not independent corpus samples; empty truth sets receive no artificial perfect-recall credit. The 100% effort exact checks passed. Quickwit PR3 uses exact Tanimoto here; no ANN latency is substituted for exact latency.

**Query cost.** Each family restarts the process, then makes five identical warm requests; OS page cache is retained. The means weight the three independently built indexes equally. These cold/warm probes have no notified request overlaps. Basic is the frozen descriptor-range request, graph is the frozen filtered substructure request, similarity is exact. CPU tick resolution is 0.01s; RSS below is a post-response snapshot, not peak. Quickwit returns stored documents including fingerprints and, for nested/matched-flat, 43 descriptors; standalone returns a smaller payload. These are API end-to-end costs, not equal-payload kernel comparisons. Warm identical requests can hit query caches and do not represent novel traffic.

| Configuration / probe | Cold s | Warm s | Cold / warm CPU core-s | Cold / warm RSS MiB |
|---|---:|---:|---:|---:|
| Standalone tuned / range | 0.0765 | 0.0559 | 0.127 / 0.098 | 336.9 / 350.3 |
| Standalone tuned / graph | 0.8285 | 0.7614 | 0.853 / 0.787 | 336.1 / 349.9 |
| Standalone tuned / exact similarity | 8.7774 | 7.9142 | 9.377 / 8.511 | 1063.5 / 1217.9 |
| Standalone after merge / range | 0.0601 | 0.0464 | 0.103 / 0.085 | 281.6 / 283.0 |
| Standalone after merge / graph | 0.7780 | 0.7426 | 0.797 / 0.766 | 287.5 / 292.7 |
| Standalone after merge / exact similarity | 1.1213 | 0.9027 | 2.533 / 2.195 | 1054.5 / 1076.5 |
| Quickwit flat tuned / range | 0.7033 | 0.6407 | 2.593 / 2.412 | 342.5 / 366.5 |
| Quickwit flat tuned / graph | 11.5221 | 0.6028 | 13.243 / 2.295 | 349.7 / 366.7 |
| Quickwit flat tuned / exact similarity | 1.5375 | 0.0104 | 1.553 / 0.019 | 331.7 / 336.4 |
| Quickwit matched-flat tuned / range | 1.1977 | 1.1295 | 4.203 / 3.998 | 346.3 / 435.0 |
| Quickwit matched-flat tuned / graph | 12.4166 | 1.0527 | 15.483 / 3.795 | 345.5 / 462.7 |
| Quickwit matched-flat tuned / exact similarity | 1.5024 | 0.0104 | 1.533 / 0.019 | 333.1 / 337.5 |
| Quickwit nested tuned / range | 1.2311 | 1.1542 | 4.303 / 4.053 | 349.2 / 456.4 |
| Quickwit nested tuned / graph | 11.8576 | 0.9563 | 14.543 / 3.397 | 349.0 / 447.4 |
| Quickwit nested tuned / exact similarity | 1.5563 | 0.0099 | 1.583 / 0.017 | 332.0 / 337.0 |

Standalone explicit merge materially changes its exact-similarity result: cold 8.777s becomes 1.121s and warm 7.914s becomes 0.903s. Comparing only the unmerged standalone would miss a supported inexpensive improvement. In these probes merged standalone has lower cold end-to-end latency; Quickwit’s identical warm exact-similarity request is much faster. Payload and cache caveats prevent turning those ratios into general search-engine speed claims. Baseline and per-run ranges remain in the machine-readable latency analysis.

**Maintenance and storage.** Three copied standalone tuned indexes each reached one live segment and 100,000 verified records. Mean merge/GC time was 3.059s (range 2.938–3.234), 3.010 core-s; copy/setup was measured separately. Mean allocated bytes fell from 158.30MiB to 73.27MiB. Original indexes remain preserved. Ingestion plus this separate maintenance duration is not an observed continuous pipeline time.

Standalone’s retained baseline has 300 live segments and tuned has 60; total directory bytes include unreferenced segment files. For the first baseline, live component bytes were 97,790,136 versus 2,394,964,175 unreferenced bytes. The first tuned index had 92,385,266 live versus 72,874,514 unreferenced bytes. Do not call the whole retained baseline directory a live-index footprint.

| Fresh Quickwit lifecycle | GC-observed seconds | Obsolete splits removed | Final published splits / internal segments | Published split bytes MiB | Allocated total MiB after observation |
|---|---:|---:|---:|---:|---:|
| flat tuned | 2580.03 | 30 | 9 / 9 | 45.96 | 114.63 |
| nested tuned | 2580.02 | 40 | 1 / 1 | 77.80 | 178.28 |

Both obsolete sets first appeared fully absent at about 2010.2s after searchability; boundaries are sampled every 30s. The normal 32-minute grace and 10-minute collector interval were unchanged. Flat retained nine live segments; nested merged from ten published splits at searchability to one. Service CPU during the 43-minute observation was 5.87 core-s for flat and 10.08 core-s for nested. Their post-observation storage difference therefore also reflects geometry and added stored fields, not pure JSON layout. Inventories de-duplicate hardlinked inodes and distinguish logical from allocated sizes, including local cache/WAL files. These are two single fresh lifecycle observations, not three-repeat storage estimates or a permanent fixed point: split maturation can take two days.

**Scope and evidence.** This establishes preparation/value parity and exact results for the tested common semantics at 100k, with explicit feature and ANN gaps. It does not establish full product equivalence, million-row behavior, disk-cold latency, crash/power-loss durability, distributed/object-storage behavior or a globally optimal configuration. Standalone’s source candidate caps are 100k for graph and 1M for similarity; Quickwit’s returned-hit cap is 10k, distinct from exact totals. Restart readback passed. All nine Quickwit baseline runs exceeded the harness’s 40-second shutdown grace and required SIGKILL after the timed measurement and observation had ended; every subsequent stored readback passed. This establishes a bounded-shutdown limitation, not a permanent hang or an ingestion/value failure. Tuned Quickwit runs did not need the fallback; the long lifecycle runs used a separate 330-second grace. Standalone terminated via SIGTERM without SIGKILL. Raw flags and exit codes are retained. Process RSS excludes much filesystem cache; cgroup traces record the full memory boundary and observed OOM counters remained zero.

The 1M decision is documented: projected raw input plus two full preparation outputs, 25% margin and 2 GiB retention reserve already exceeded available space before 1M indexes/WALs/archive. No 1M performance is extrapolated. Only reproducible study-owned compilation/toolchain caches were reclaimed; binary/model hashes were verified unchanged. Original retained run evidence and other tasks were not reset. Engine-managed GC is captured through before/after inventories and traces; deleted intermediate file versions are not reconstructed.

The portable evidence archive contains all WALs, inputs, raw requests/responses, resources, full audits, index metadata, configs, locks, pins, binaries/model assets, published methods, failure/notification records and scripts. Large Quickwit split objects and standalone Tantivy segment components remain intact in the original workspace and are omitted only from the portable tar. metrics/retained-index-inventory.jsonl records their paths, sizes and SHA-256; copying those verified blobs restores the original indexes. The portable bundle alone supports fresh re-ingestion/reproduction and review of complete stored readbacks, but does not reopen the original binary indexes without those retained blobs. `artifacts/EVIDENCE-MANIFEST.json` records ordered parts, hashes and extraction details after packaging. Library bulk transfer is blocked before upload preparation by the executor proxy (HTTP tunnel 403); local deliverables remain available and the existing Library checkpoint is updated separately. No successful bulk Library upload is claimed. Three full-index compression attempts stopped at their disk reserves (2 GiB, 2 GiB, then a post-measurement-only 512 MiB); redundant incomplete copies were hash-inventoried and removed, with all unique source evidence retained. A complete binary-index archive cannot coexist with the originals within this workspace. The portable replay/audit bundle therefore uses a 2 GiB reserve and retains bulk index blobs separately. The measured protocol is unchanged; archive-capacity-adjustment.json and archive-attempt-1/ through archive-attempt-3/ document the packaging adaptation.

Read [PROTOCOL.md](PROTOCOL.md), [CAPABILITIES.md](CAPABILITIES.md), [REPRODUCE.md](REPRODUCE.md), [ingestion summaries](metrics/summary.json), [paired sensitivity](metrics/connection-sensitivity.json), [query latency/CPU/RSS](metrics/query-latency-sensitivity.json), [response/ANN audit](metrics/expanded-response-audit.json), [screen versus graph truth](metrics/pattern-screen-audit.json), [lifecycle analysis](metrics/lifecycle-analysis.json), [index geometry](metrics/index-geometry.json), and [provenance verification](metrics/provenance-verification.json). Published historical tuning is retained at [experiment 005](ledger/benchmarks/chemistry/experiments/005-runtime-tuning.md).
