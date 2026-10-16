# Independent review: Ruby candidate 0.9.1.pre.contract1

Reviewed 2026-10-16. Scope: the final generated and installed local Ruby package, its provenance, documentation, manual preparation workflow, and bounded native smoke evidence. No source files were changed by this review.

**Verdict: no blocking defect found in this local SDK candidate. It is suitable for continued importer integration and bounded workflow testing. This is not approval of production catalog promotion, complete chemistry/error relevance, campaign readiness, deployment, or publication.**

## Exact artifact

- Gem: `/workspace/recovery/quickwit-cheminee-0.9.1.pre.contract1.gem`
- Gem SHA-256: `43208077f9e1907390e306cff34cd901970c964557d4c6119516f4a4319036a9`
- Server source: `8009925c6b9757edc77ef8e6111309503028e7c5`
- Running native binary SHA-256: `0f12ffeff21f33173cdc9dbde85646a9466cc077cc50ae70faa81479ee83db29`
- Packaged provenance SHA-256: `f6d51b82ebfaaac0fe8af2dc2f0b8cdf2bb3aa8a78bf7853f319bd849673751d`

The recorded source revision concerns server/schema provenance. Generator, templates, support code, dependency lock and schema have separate content hashes. The native binary is a debug build; neither reproducible native compilation nor identical gem archive timestamps is claimed.

## Independent verification

`sdk-contract1-independent-verification.json` records the artifact audit. All 452 files in each of the two retained generation trees and the repository generated tree match byte-for-byte. I recomputed the schema projection and checked the full/projected schema, generator configuration, projection script, pinned generator JAR, dependency lock, templates and support hashes. The package contains exactly the 296 files selected by the gemspec, with safe regular-file paths. Every packaged file matches the generated tree and the installed gem. The packaged provenance agrees with the source manifest. The opt-in ExactSearch implementation hash is `d9051923d5ed71fe0b8a9156fadb15f672b148f9b5003937f7f917e5f89afa31`.

I reran the final installed gem's HTTP tests outside the source tree with an empty `RUBYLIB`: **16 tests, 319 assertions, zero failures/errors/skips**. Evidence: `sdk-contract1-independent-wire-final.log`. This covers the wire contract and controlled malformed/partial responses; it does not establish chemical truth. Activated dependency versions are checked against the retained lock. Consumer dependency requirements are bounded compatible ranges, so the locked graph is the tested graph, not a promise about every future resolver result.

I independently fetched the live native OpenAPI document and compared parsed JSON with the retained schema. They are semantically identical; raw byte hashes differ and must not be described as byte-identical exports. I hashed `/proc/PID/exe` for all three active fixture processes, which match the rebuilt binary above. The current Rust source tree has no differences from the recorded server commit. Evidence: `sdk-contract1-independent-runtime.json`, supported by `contract1-final-provenance.json` and `contract1-native-build.log`. This closes the earlier smoke run's pre-commit runtime attribution gap.

I reran `native_smoke.rb` using the final installed package against those restarted fixtures. It passed graph/Tanimoto counts and tied-ID enumeration across pages, plus strict search/count rejection of a failed fingerprint leaf. Unchecked responses demonstrate why their apparently exact total is insufficient: the test checks failed/successful/total shards and healthy IDs. Evidence: `sdk-contract1-independent-native.log`. This is four bounded check groups on tiny persisted fixtures, not exhaustive semantics, general snapshot pagination, crash recovery, HA or performance evidence.

## Documentation and workflow

The repository README, pinned packaged README and manual workflow default consistently name `.pre.contract1`. The README distinguishes scoped native success from remaining release gates, explains unknown ingestion acknowledgements and quarantine, preserves absent counts as unknown, and warns against blanket write retries. ExactSearch's immutable-generation and unique numeric-ID assumptions are explicit. The generated unchecked API remains visibly distinct from the strict adapter. Logging guidance avoids routinely exposing bodies/catalog content while retaining status, headers and bounded diagnostics. The campaign's stale opening timestamp-broadening statement has been corrected.

The preparation workflow is manually dispatched and prepares artifacts without publishing. It pins relevant generation inputs, repeats generation, and tests the installed gem. It has **not been executed in GitHub**; local successes do not certify that workflow's hosted execution.

## Remaining gates

- Full `cargo clippy --workspace --all-features --tests -- -D warnings` is **incomplete**, terminated with exit `-15` for disk headroom. `workspace-all-features-clippy-status.json` records the stop. Scoped earlier Clippy results do not replace it.
- Broader OR error relevance, old-schema compilation/warmup and timestamp-sort pruning remain open. The retained final probes report 68 selective cases and 105 assertions across 109 relevance requests; four requests are observations, not passing oracles.
- Catalog generation examples, their final experiment and production promotion/rollback safety are outside this package audit. Compose/Elasticsearch coexistence, durability, HA, benchmark recommendations and full campaign readiness are not approved.
- Publication authorization remains false. No release approval follows from this review.

Earlier Ruby attempts with incomplete environment configuration or filesystem/container failures are not passes. The exact final artifact's successful independent reruns above supersede those attempts for this bounded SDK check without erasing them.
