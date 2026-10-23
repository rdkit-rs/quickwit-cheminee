# Composable chemistry operators (review branch)

Status: local implementation for review; do not merge or deploy until the independent
frozen-code benchmark and this change have been reviewed. No benchmark measurements
are supplied by this implementation branch.

## Architecture and scope

Quickwit's `QueryAst` is the single typed representation, including the existing
`TanimotoQueryAst` and `GraphQueryAst` and the new `FingerprintContainsQueryAst`.
The Elasticsearch-compatible JSON subset and Lucene-style text parser construct
these exact same types. Their existing Boolean, range, visitor, transformer,
contract validation, fast-field warmup, and split-pruning machinery is reused.
No RDKit code or grammar changes are added to upstream Tantivy. Tag pruning retains
an unknown chemistry conjunct alongside candidate tags, so nested negation cannot
treat the necessary candidate condition as sufficient for a chemistry match.

The pure `tantivy-rdkit` adapter implements packed-bit scoring and candidate
iteration. `tantivy-rdkit-mapper` retains RDKit preparation and graph matching.
Existing SMILES preparation endpoints and graph/similarity routes remain available.
These composable operands take **prepared** query data: a packed fingerprint or
SMILES already normalized under the declared contract. Graph validation rejects
noncanonical prepared SMILES. Raw SMILES, SMARTS, inferred contracts, Pattern
fingerprints, automatic graph screens, ANN, arbitrary scoring scripts, and a general
chemistry language are outside this change. This is a Quickwit extension, not an
Elasticsearch chemistry feature or a claim of full Elasticsearch compatibility.

## Operators

| JSON clause | Text field | Match and score |
|---|---|---|
| `tanimoto` | `_tanimoto` | Exact Morgan Tanimoto >= inclusive `minimum`; score = Tanimoto |
| `fingerprint_contains` | `_fingerprint_contains` | Exact bit subset test; score = 1 |
| `molecular_graph` | `_molecular_graph` | RDKit graph predicate and existing graph ranking |

Each operand contains `spec`, and optionally `candidates` (default match-all).
`candidates` is a **typed QueryAst**, not an Elasticsearch DSL clause. It filters
before verification, and its score is discarded. Put selective filters here to
reduce chemistry work. A sibling Boolean filter is semantically equivalent for
matching, but is not automatically pushed into the chemistry operator.

Containment requires `fingerprint_hex` and `direction`, either
`document_contains_query` (all query bits in document) or `query_contains_document`
(all document bits in query). It does not prove graph containment. In particular,
Morgan containment can reject true molecular substructures, so it is **not a
recall-safe prefilter for exact graph search**. Combining it with graph verification
explicitly asks for the intersection of the two predicates.

Graph operands require `prepared_smiles`, `prepared_field`, `predicate`
(`identity`, `substructure`, or `superstructure`), `ranking`, `use_chirality`, and
`include_identity`. Substructure means the document contains the query;
superstructure means the query contains the document. Existing normalization,
chirality, identity, and ranking behavior is preserved; see
[graph contracts](../../quickwit/tantivy-rdkit-mapper/GRAPH_SEARCH.md).
Graph queries require native chemistry on every executing worker.

## Text and JSON equivalents

Use ordinary JSON inside a single-quoted Lucene operand. Escape **each backslash
and single quote** for the outer text grammar after serializing JSON. Quotes,
parentheses, charges, and other chemical punctuation then remain operand data.
Unquoted operands, phrase slop, prefix modifiers, unknown operand members, and
invalid enums are rejected. Ordinary Boolean grouping, NOT, OR, and boosts remain
available. These field names are reserved for chemistry operators.

For example, exact graph matching with a nested numeric descriptor range:

```text
_molecular_graph:'{"spec":{"format":"morgan-r3-2048-lsb0-v1","rdkit_version":"2026.09.1","preparation_id":"sanitize-only-v1"},"prepared_field":"prepared_smiles","prepared_smiles":"CC","predicate":"substructure","ranking":"best_match","use_chirality":false,"include_identity":true}' AND descriptors.amw:[0 TO 300]
```

```json
{
  "bool": {
    "must": [{
      "molecular_graph": {
        "spec": {
          "format": "morgan-r3-2048-lsb0-v1",
          "rdkit_version": "2026.09.1",
          "preparation_id": "sanitize-only-v1"
        },
        "prepared_field": "prepared_smiles",
        "prepared_smiles": "CC",
        "predicate": "substructure",
        "ranking": "best_match",
        "use_chirality": false,
        "include_identity": true
      }
    }, {"range": {"descriptors.amw": {"gte": 0, "lte": 300}}}]
  }
}
```

These forms use scoring AND (`bool.must`): the matching range contributes its
existing constant score of 1. They agree on both scores and membership.
`bool.filter` suppresses that contribution and is not score-equivalent to plain
text AND. A zero boost on a text clause suppresses its score. To apply
the range before graph work, move it into the operand:

```json
"candidates": {
  "type": "range",
  "field": "descriptors.amw",
  "lower_bound": {"Included": 0},
  "upper_bound": {"Included": 300}
}
```

For a similarity operand, replace the graph fields with `fingerprint_hex` (512
hex characters encoding a nonzero 2048-bit Morgan fingerprint) and `minimum`
(a finite number in [0,1]). For bit screening, use `fingerprint_hex` and
`direction`. `quickwit/quickwit-query/tests/chemistry_operators.rs` contains executable
text/JSON examples, with deliberately synthetic bit vectors for hand-checkable scores.

## Ranking, errors, limits and distribution

* `must` and matching `should` clauses add scores using the existing Boolean query
  semantics. Candidate scores never contribute. `filter` and `must_not` do not
  contribute scores. Similarity is never silently treated as ANN or post-top-k
  rescoring. Mixing text and chemistry scores is an explicit uncalibrated sum.
* Top-k is a collector/request limit, not a leaf predicate or candidate shortlist.
  Verification considers all live candidates; total hit counting follows the
  selected API's existing total-hits settings independently of page size.
* For chemistry-ranked deterministic results, explicitly request `_score`
  descending, then `record_id` ascending, and globally unique stable numeric IDs.
  Standard Quickwit/ES-compatible search APIs retain their existing default sort
  behavior; the new operators do not override it. Existing Cheminee endpoints
  already append the stable ID sort. A generic request without this sort has no
  chemistry-specific stable tie guarantee. Duplicate IDs likewise lack that guarantee.
  This fork's ES-compatible response omits the separate `_score` member; with this
  explicit sort, the score is returned as `sort[0]` and the stable ID as `sort[1]`.
* Existing Quickwit per-leaf collection and root merge use the same requested sort
  tuple. Thus per-split top-k is sufficient for global top-k. No new distributed
  coordinator, hidden reranker, or changed merge protocol is introduced.
* Missing/incompatible fingerprint or graph schema fails validation, even when
  schema leniency is enabled. A live candidate with a missing, malformed, or
  multivalued chemistry value fails the segment. A missing entire segment fast-field
  column currently fails even if candidates are empty. This is an unresolved
  relevance-contract gap, not a desired integrity-scan guarantee. Values outside the explicit
  candidate domain and deleted documents are not chemistry-validated. Missing
  descriptor values follow existing range behavior (no match).
* Standard search endpoints retain their partial-result/error reporting. Quickwit
  search defaults `allow_failed_splits` to false; the ES-compatible endpoint defaults
  to allowing partial results, so use `allow_partial_search_results=false` and
  inspect shard failures for exhaustive results. Existing Cheminee routes retain
  their stricter error behavior.
* Fingerprints remain fixed-width; spec identifiers remain 1..128 printable ASCII
  bytes; thresholds and native graph contracts retain their existing validation.
  Text operands additionally cap decoded JSON at 64 KiB. JSON requests retain
  the API body/serde nesting limits; this is not a new unbounded query language.
  Standard API result limits remain in force. No per-operator top-k is supported.

## Execution and memory

The old implementation scored every dictionary value before iterating candidates.
The new implementation walks live candidate document IDs, validates their single
value, and memoizes verification per encountered dictionary ordinal. Repeated
molecules in a segment are checked once. Both errors and accepted scores are
resolved before exposing a scorer because Tantivy's `DocSet` cannot report errors.
This is candidate-first **materialized** execution, not lazy per-hit verification.
Memory is O(distinct candidate values + accepted candidate documents) per segment.
Broad matching queries can therefore use more memory than the old dictionary-only
score table. Selectivity, memory, and latency need separate measurements; no speedup
is claimed here. No arbitrary shortlist may remove valid matches.

## Review questions

1. Is a reserved field plus quoted JSON operand an acceptable initial text syntax,
   or should a later ergonomic SMILES/function grammar replace it?
2. Should generic endpoints enforce the chemistry tie sort and reject partial split
   results, or keep these explicit request/client responsibilities?
3. Is candidate-first materialization's accepted-document memory cost acceptable?
   A fallible streaming adapter would require a separate Tantivy API design.
4. Should a future version introduce a versioned Pattern-fingerprint contract and
   independently prove recall-safe screening before pairing it with graph matching?
5. Should raw-SMILES preparation for composable queries move into a root-only
   preparation pass? This change deliberately reuses prepared AST contracts.

## Verification commands

From `quickwit/`, with the pinned RDKit development/runtime libraries available:

```sh
cargo test --locked -p tantivy-rdkit -p quickwit-query --lib --tests
cargo test --locked -p tantivy-rdkit -p tantivy-rdkit-mapper -p quickwit-query -p quickwit-doc-mapper --features quickwit-query/native-chemistry,quickwit-doc-mapper/native-chemistry --lib --tests
cargo build --locked -p quickwit-cli --features native-chemistry --bin quickwit
python3 tantivy-rdkit/poc/composable.py --binary target/debug/quickwit --work-dir /tmp/composable-fresh-run
```

The HTTP harness uses a root with no searcher service and two native leaf processes,
multiple unmerged splits, stable ties, exact totals at top-1, all three operators,
AND/OR/NOT, filter scoring, embedded candidates, and malformed requests. Its tiny
molecules have hand-checkable graph results; fingerprint results use a separate
Python bit oracle over indexed bytes. This does not replace an independent
normalization oracle or a large-data benchmark. Workspace prerequisites and actual
run results are recorded separately in the handoff evidence.

The follow-up harness also uses four matches per split, ties spanning both leaves,
and `from=2,size=4` for graph and similarity ordering. Per-leaf request counters are
checked around those queries specifically. A separate ordinary bytes-field index
admits a malformed fingerprint so that one split fails during leaf verification
beside a healthy split. Strict ES-compatible search returns HTTP 500; explicit
`allow_partial_search_results=true` and the default return healthy hits with one
failed shard. The partial response's total counts successful splits only (even
though its existing relation is `eq`); it is not an exhaustive chemistry total.
The segment-level tests exercise missing, multivalued, and malformed values for
graph, Tanimoto, and containment, both outside explicit candidates and retained
behind deletions, plus absent columns with empty candidates. The graph execution
tests use a deterministic fallible verifier; the HTTP graph checks use RDKit.

New containment ASTs require updated workers; old workers reject the new variant.
Mixed-version rolling upgrades are not validated by this change.
