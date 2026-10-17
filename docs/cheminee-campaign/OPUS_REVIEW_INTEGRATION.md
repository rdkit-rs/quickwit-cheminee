# Opus review integration

Review: [PR #6 comment](https://github.com/rdkit-rs/quickwit-cheminee/pull/6#issuecomment-6235593589),
against `dca8e59f44e5d2cf6770b0076a5092b097aa237d`, stacked on
`6bf1e29cdbf03409287b2f7d0e59a4c19534d8fa`. This follow-up is a draft-review
candidate, not release approval. Merge, publication and deployment remain held.

## Decisions and disposition

1. Restore retries only with a per-subrequest, per-attempt proof that no append
   was initiated on either leader or follower. Generic transport errors do not
   establish that proof. Preserve ambiguous outcomes as terminal.
2. Make the tested JSON behavior a runtime dependency and make missing journal
   state an error. Keep explicit initialization and withdrawal decisions visible.
3. Make resource verdicts sensitive to process incarnation and actual build
   storage. Historical runtime evidence must retain its original source revision.
4. Keep broader contract, replication and performance work as explicit gates;
   passing Ruby or harness tests does not validate a revised server binary.

| Finding | Disposition and evidence boundary |
| --- | --- |
| B1 | Implemented new `NoShardsAvailableBeforeAppend` and `NodeUnavailableBeforeAppend` protobuf reasons at the leader's pre-append refusal sites. Only these new reasons gain retries; legacy ambiguous reasons remain terminal. Added both-reason healthy-leader retry and safe-refusal-then-unknown terminal tests, updated existing refusal tests. Protobuf regenerated with the existing build-script binary. Rust tests are **not run** locally; CI required. |
| B2 | Generated gem and generator template require JSON `>= 3.1, < 4`. Installed-gem wire tests reject duplicate response keys. Tests reject multibyte UTF-8 bytes tagged `ASCII-8BIT` before HTTP/index creation. Documentation requires explicit validated UTF-8 conversion, not lossy conversion. |
| B3 | Explicit `CatalogGeneration.create` initializes state; opening requires directory, lock, scope, identities and active state, rechecked under every operation's lock. Loss before/after opening fails before writes in tests. An older internally valid journal rollback remains undetectable without an independent durable fence. |
| B4 | Measurement Compose disables automatic restart. Smoke/admission/resource checks retain ID, RestartCount and StartedAt for Quickwit and observed Elasticsearch, including gaps around the explicit restart. Unit fixtures reject unexpected count/start changes. Revised live smoke and resource run remain unrun. |
| M1 | Reject conflicting offer supplier/observed-at values and preserve nanosecond timestamp precision with `iso8601(9)`; catalog regressions pass. |
| M2 | Rejected-document rendering uses UTF-8 replacement instead of panicking. Added a Warp route test for mixed invalid/valid NDJSON with a mocked ingest backend. This is not a live persist test; Rust execution remains pending. |
| M3 | Guard checks the device of cwd, Cargo home and Cargo-metadata-resolved target against the measured filesystem, records paths and enforces observed growth budget during/following execution. Focused Python tests pass. |
| M4 | Durable initial state precedes the lock pointer; fsync state, directory and lock. Missing previous state produces explicit operator-review refusal. Focused Python tests pass. |
| M5 | Corrected SDK counts, live-smoke default version and JSON evidence status. Root/local/resource docs attribute historical unoptimized Compose evidence to `8009925c` and older scripts. No current-runtime claim. |
| M6 | Guard tests isolate unrelated compiler detection and retain a dedicated proc-fixture detector test; 19 tests pass in the normal namespace. |
| R1 | **Open release/HA blocker.** Delayed/lost replica ACK can leave shard lifecycle inconsistent. Requires real two-batch WAL/replication recovery tests and reviewed close/reconcile behavior. This change does not establish replicated recoverability. |
| R2 | **Open release blocker.** REST lacks machine-readable `not_persisted` versus `unknown` outcomes and a generated error schema. B1 is internal retry safety only. Clients must continue treating write errors as unknown and must not blindly replay. Requires actual HTTP error-path tests and server/schema/client revision together. |
| R3 | Added `order: :record_id` enumeration, used by catalog audits. Score order remains available/default; docs warn split-local text scores can change after merges. Pin an immutable generation; this is not snapshot/cursor support. |
| R4 | Empty supplier snapshots now require named `allow_empty_suppliers` authorization. Nonempty shrink thresholds remain application policy; no unmeasured universal threshold is imposed. |
| R5 | **Open raw API limitation.** Unchecked ES responses can overstate count/completeness; GET/status/schema coverage is incomplete. Strict `ExactSearch` remains the supported fail-closed adapter. Do not remove defensive checks merely because one current producer leaves errors empty; no arbitrary ES/Searchkick compatibility claim. |
| R6 | **Open native API semantic gap.** Request-level timestamp bounds are outside chemistry candidate narrowing. Need malformed/out-of-window native HTTP cases and a reviewed error-domain decision before changing this behavior. ES/Ruby AST filtering is separate. |
| R7 | **Open measurement gate.** Eager candidate vectors/cache scale with live candidates. Representative corpus recovery, stage costs, concurrent memory and broad-query profiling remain absent. No speedup, memory target or ANN substitution inferred. |
| R8 | **Documented example limitation.** Catalog example mapping is not native structure search; it does not track canonical structure identity/preparation versions. Stable offer identity does not establish structure identity. Production chemistry importer remains a separate gate. |
| R9 | Added swap-inclusive limits equal to memory limits. PID/thread concurrency, Compose recreate, non-wait-for WAL replay and coexistence remain unmeasured; configured bounds are not validated capacity. |
| R10 | **Open operational limitation.** Exact audit equality conservatively quarantines normalization differences/read failures. Needs a tested normalization contract and explicit recovery process; equality was not relaxed and unknown writes are not replayed. |

The resource harness also replaces its hardcoded expected source revision with a
required full 40-hex `--source-commit`, recorded and compared with runtime provenance.

## Verification and provenance

Focused local results for this revision's changes (Ruby 3.3.8, actual JSON 3.1.0
native extension, installed generated gem):

| Check | Result |
| --- | --- |
| `sdk/ruby/wire_test.rb` | 24 tests, 420 assertions; seed 5782 |
| `sdk/ruby/examples/catalog_generation_test.rb` | 20 tests, 107 assertions; seed 22021 |
| `sdk/ruby/loaded_json_check_test.rb` | 9 tests, 10 assertions |
| `sdk/ruby/projection_test.py` | 7 tests |
| Pinned OpenAPI Generator 7.11.0 generation twice | byte-identical output; built and installed gem |
| `quickwit/scripts/ci/test_campaign_phase.py` | 19 tests |
| `docs/cheminee-campaign/resource-measurements/test_harness.py` | 11 tests |
| Python syntax, Ruby smoke syntax, `git diff --check` | pass |

The coordinator independently reran the final wire (24/420) and catalog
(20/107) suites with seeds 41038 and 41039, and the final 11-test resource harness. These
are overlapping runs, not additive test totals.

The SDK schema provenance remains honestly attached to server
`8009925c6b9757edc77ef8e6111309503028e7c5`; regeneration updates template/support
hashes, not the exported server revision. No current-head export or live Ruby
smoke has been fabricated. The manual preparation workflow still needs a real
run, complete catalog/JSON-guard coverage, dependency activation verification,
committed-output comparison and reproducible OS-package handling.

Original-head GitHub CI subsequently passed wrapped all-features workspace
Clippy and 2,904 nextest tests (6 skipped; one scheduler test passed on retry),
plus REST/DataFusion checks. Overall original-head CI failed nightly import
ordering (fixed here) and a separate worker's 100 ms ingest-test timeout. The
timeout is not established as harmless merely because another job passed it.
Dependency-review failure concerns repository capability, not a demonstrated
vulnerability; repository settings were not changed.

Local free disk is below 1 GiB and below the build guard's admission threshold.
No new Rust build, native test, current-head HTTP server, Compose/Elasticsearch
run or HA test was attempted. Stable rustfmt parsed changed Rust files, but
nightly formatting and compilation remain CI gates. Existing generated protobuf
tooling ran successfully without a Cargo build. Scoped design review supports
the narrow B1 distinction. A further source check found no API/field mismatch
in the retry and Warp route tests; the terminal-unknown test proves workbench
state, not actual dispatch counts. Neither review replaces execution or final
independent implementation/readiness review.

Mixed-version caution: the original PR3 router retried all Persist failures,
including unknown enum values. Do not claim old routers fail closed. Upgrade
routers to the corrected behavior before relying on these semantics; no
mixed-version or exactly-once guarantee is established by the new enum values.

Before release: resolve R1/R2 and applicable native/contract gaps, obtain passing
revised-head CI and native/runtime evidence, refresh schema provenance against
that server, complete independent Astra review, and obtain separate publication
approval. See [remaining gates](REMAINING_GATES.md) for the wider campaign.
