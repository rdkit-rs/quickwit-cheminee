# Independent error-domain design gate — 2026-10-16

Reviewer: independent `gpt-6-astra`, maximum effort. Decision: strong contract
**failed**. The proposed design below has not been implemented or validated.
No isolated optimizer fix was approved.

Each chemistry operator must validate live documents in its own explicit candidate
domain. Sibling Boolean clauses change matches and scores, not that obligation.
Deleted documents and documents outside explicit candidates remain excluded.

Two live native counterexamples are retained under `evidence/sdk-dsl`:

- `sibling-domain-probe.json`: unbounded malformed-fingerprint query fails 500;
  adding sibling `match_none` returns clean 200, exact zero. Explicit numeric
  candidates excluding that document succeed with exact two.
- `timestamp-domain-probe.json`: explicit timestamp candidates excluding the
  malformed document still fail 500 when healthy and malformed documents share a
  split. The leaf timestamp rewrite moves the candidate range outside the operator.
  The reviewer first identified this by source inspection; the implementation
  agent subsequently reproduced it over HTTP.

Recommended coordinated implementation:

1. Preserve chemistry obligations before lossy ES Boolean conversion, including
   impossible `minimum_should_match` in `elastic_query_dsl/bool_query.rs`.
2. At QueryAst compilation, retain the resolved original chemistry operands with
   their exact candidate subtrees. Wrap the normal optimized matching query with
   verification obligations. Construct each materializing chemistry scorer before
   returning a segment result; count-only paths must verify too. Warmup must retain
   fields from obligations eliminated from the matching query. Initially accept
   measured duplicate work rather than introducing shared mutable scorer caches.
3. Detect chemistry before planning. Conservatively bypass sibling-derived tag/time
   split pruning, required-term/negative-cache early success, and top-k/count
   shortcuts that skip verification. Ordinary queries keep their optimizations.
   Cached results may substitute only if they establish completed verification for
   the same immutable split, query and contract; initially bypass uncertain caches.
4. Preserve explicit candidate boundaries through `RemoveTimestampRange` in
   `quickwit-search/src/leaf.rs`; initially bypass that rewrite for chemistry-bearing
   requests. Retain any outer filtering separately.

Regression matrix: normal bytes-field ingestion permits malformed fixtures. Test
healthy and malformed documents together in one split and across separate splits,
with a timestamp field, tag field, indexed non-tag field and two executing leaves.
Test Tanimoto, containment and graph, count-only and top-k:

| Case | Required behavior |
|---|---|
| Unbounded malformed chemistry | Error |
| Sibling match-none in both orders | Error |
| Must-not, zero boost, impossible minimum-should-match | Error |
| Sibling tag or timestamp excludes malformed split | Error |
| Sibling absent indexed term; cold and primed caches | Error |
| Explicit numeric/timestamp candidates exclude malformed data | Exact expected matches and scores |
| Empty candidates and missing required segment column | Preserve documented structural error |
| Malformed document deleted | Success if remaining structural requirements hold |
| Healthy controls and ordinary queries | Preserve membership, scores, counts, pages and ordinary optimizations |

This blocks unrestricted composable-query contract and release approval. The Ruby
adapter cannot detect a clean successful response after skipped verification.
Documentation does not repair this guarantee. Local Compose and importer work can
proceed independently, but cannot be presented as a passed correctness gate.
