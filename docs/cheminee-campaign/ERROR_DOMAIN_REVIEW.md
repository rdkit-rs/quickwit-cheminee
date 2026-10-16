# Relevance-based error contract — continuation decision

The parent delivered this superseding Astra decision on continuation from checkpoint
`2f6ebc3c39aaf2562b931a9829fca99c936ab1d3`. It replaces the global verification
proposal preserved below. Implementation and regression coverage remain pending.

Validate query syntax, options and chemical inputs eagerly. Stored-data errors are
fatal when unresolved errors could change membership, count or rank. Logically
excluded corrupt records do not require a global integrity scan. In particular,
valid chemistry AND `match_none` may return exact zero without stored verification.
Relevant failed splits must never imply an exact complete total.

Consequences for the retained evidence:

- The `sibling-domain-probe.json` exact-zero result is not itself a defect under
  this contract. Both clause orders must agree; invalid query inputs still fail.
- The timestamp-candidate probe remains a real bug: moving explicit candidates
  outside an operator broadens verification into explicitly excluded records.
- The previous unconditional verification-wrapper proposal is superseded. Do not
  implement it or disable all chemistry pruning merely to reproduce that proposal.
- OR and NOT need separate membership/count/rank reasoning. A clause irrelevant
  to membership may still affect ranking; no blanket short-circuit rule follows.

Required next validation covers both conjunction orders, OR/NOT, relevant and
irrelevant corrupt records, exact counts and rank, explicit candidate boundaries,
and pushdown invariance. Query-input validation must survive Boolean simplification.
Independent Astra max design and implementation reviews remain required.

Catalog refresh, generated installed Ruby/paging, measured Compose coexistence,
durability/HA/overload, observability, benchmark-based guidance and README comparison
remain authorized work. Publication, remote merge, deployment, contacting others,
credentials and paid infrastructure remain outside authorization.

## Current implementation slice and remaining gates

Independent Astra max review approves preserving ES operands through eager input
validation, then collapsing impossible minimum-should-match after every child has
built. It also approves recursive generic transformer hooks with chemistry nodes
opaque only to the leaf timestamp-range rewrite. These changes do not add a global
integrity scan or disable ordinary split pruning. Native query tests passed 162
cases; broader runtime validation is recorded separately as it completes.

Remaining relevance cases are not claimed fixed: materialized chemistry scorers
can still inspect a corrupt row excluded by a sibling filter in the same split;
empty/deleted-only candidates currently require stored columns before discovering
emptiness; and root timestamp extraction may round an exclusive subsecond lower
bound too far forward (source-derived risk, not yet reproduced). Tests must compare
explicit-candidate and sibling forms while preserving original scores and Boolean
logic. OR with match-all may determine membership/count but still leave rank
unresolved; use separate count-only and scored assertions.

## Historical review — superseded where it requires global verification

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
