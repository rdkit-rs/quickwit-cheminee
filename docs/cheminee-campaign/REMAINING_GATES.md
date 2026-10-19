# Remaining acceptance gates

Continuation base: `c15204119d29285511ac1a5563732a6a714a3315`.
The original history is preserved in draft PR #6. Merge, package release and
deployment remain held; scoped passing evidence is not approval of the whole release.
See [Opus integration](OPUS_REVIEW_INTEGRATION.md) for the earlier review disposition.
The 2026-10-19 [dependency preflight](DEPENDENCY_PREFLIGHT.md) now precedes any
benchmark trial. Head `618e70c8` completed all four PR workflows successfully,
including 2,908 workspace tests (6 skipped, no retry); this does not certify the
new dependency-remediation candidate, whose full CI remains pending. Resource
admission remains blocked. No optimization trial has started.

| Gate | Objective acceptance criteria | Current state |
| --- | --- | --- |
| Old physical schemas | Current declarations/inputs fail eagerly; ordinary candidate IDs use physical schema; incompatible chemistry is fatal only for live candidates. Mapper matrix and real HTTP schema update retain old/new mapping UIDs, untagged candidate filter and strict exact counts/hits. | Bounded gate passes: commit `2882a340`, native mapper/core tests and 39 HTTP checks, Astra max approval. Compatible-column corruption and arbitrary migrations remain open. |
| Timestamp top-K pruning | Both directions/signs, ties/secondary order, unknown endpoints and i64 nanos extremes never discard a better hit. Preserve CountAll/aggregation obligations and offsets. Deterministic multi-split test plus strict HTTP verifies IDs, not totals alone. | Bounded gate passes: commit `8a895900`, five native units and 18 HTTP checks, Astra max approval. Cold wrong-ID baseline reproduced. |
| General relevance | Count-only OR, nested NOT/should/MSM, both clause orders and failed leaves follow membership/count/rank relevance; invalid syntax/chemistry stays eager. Actual corrupt-column I/O cannot be silently skipped when relevant. | Open; four prior cases are observations only. Independent scoped count-only rewrite design retained; not implemented or accepted. |
| Workspace validation | Required format/policy and full workspace all-features Clippy complete successfully, with command/features/toolchain/status retained. No disk-exhaustion run counts as passed. | Current scoped native Clippy and format/policy pass. Full all-features default stopped at TensorFlow download HTTP 403; retry with existing TF 2.15.1 stopped at 640 MiB disk guard (exit -15). Raw retries then failed in krb5-src, including C17. Diagnostic inspection found these bypassed the existing CI compatibility wrapper: avoidable process error. Subsequent PR #6 CI at original head `dca8e59f` passed wrapped workspace all-features Clippy and 2,904 nextest tests (6 skipped, one retried scheduler flake), plus REST/DataFusion. Overall CI failed on nightly import ordering and a 100 ms ingest-test timeout in the separate worker job. Revised-head Rust/native validation remains pending. Offline dependency preparation passes; the reviewed campaign guard refuses workspace admission at current headroom. |
| Profiling and developer guidance | Selective/broad/empty/novel exact query oracles; end-to-end and stage costs, concurrency/memory, batch/page/depth comparisons. Recommendations derive from retained measurements. | 16-row synthetic broad/selective/empty/novel latency/RSS samples retained; no stage profiling or batch/concurrency recommendations. Historical 100k corpus/index bundle unrecovered. |
| Compose + Elasticsearch | Pinned local images/config, native importer/query/restart correctness; simultaneous idle/import/query/peak RSS and cgroup/OOM accounting with shared-page caveats; retained disk/recovery headroom. | Historical unoptimized `8009925c` single-node smoke passed using older scripts; current runtime/harness and coexistence remain unmeasured. Optional pinned-image override and dual-container sampler prepared/config-checked only. No image pull within current headroom. |
| Catalog/HA/durability | Node/process loss, restart, uncertain ACK, incomplete/stale refresh, corruption, bounded overload, promotion/rollback and cleanup preserve independently checked contents. Separate accepted/persisted/published/searchable barriers. | Historical single-host HTTP journal smoke passes 21 cases. Revised focused local journal/process suite passes 20 tests/107 assertions, with fake-peer acceptance visible across forks; this is separate evidence, not new server durability validation. Searcher SIGKILL synthetic probe returns correct results through survivor/rejoin; shared local storage only. No server fence, distributed CAS, storage/power-loss or HA approval. |
| Observability/release | Bounded labels, request/import correlation, sanitized support artifact; version/schema provenance and independent Astra max implementation/readiness acceptance. | Generated gem and bounded source scopes reviewed; broader campaign/release review open. No publication/merge/deployment authorized. |

Disk note: old `.onboarding` Rust library/metadata/incremental caches were inventoried
and removed while retaining executables, source, tools and evidence. They belonged to
the base snapshot: deletion created overlay whiteouts and recovered no writable
headroom. Do not repeat that strategy. Manifest is retained in recovery evidence.
