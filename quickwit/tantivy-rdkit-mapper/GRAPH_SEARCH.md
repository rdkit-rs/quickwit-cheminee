# Distributed molecular graph search

Cheminee routes are `POST /v1/indexes/{index_id}/search/basic`, `identity`,
`substructure`, `superstructure`, and `similarity`. Their standalone OpenAPI
schema is `GET /v1/openapi.json`; they also appear in Quickwit's full registry.
The original `/api/v1/{index_id}/cheminee/search/similarity` fingerprint endpoint
and its `/smiles` variant remain available.

Graph requests contain `spec`, `smiles`, `extra_query` (default `*`),
`result_limit` (1–10,000, default 100), `use_chirality` (default false),
`include_identity` (default true), `ranking` (default `best_match`), and
`prepared_smiles_field` (default `prepared_smiles`). The prepared field and
contract must match the index's chemistry mapping. SMILES queries require
`native-chemistry` at the root; graph queries require it on every worker too.
An unavailable native feature or incompatible index contract fails explicitly.

| Route | Predicate | `best_match` score and order |
| --- | --- | --- |
| identity | RDKit matches in both directions | 1, then `record_id` ascending |
| substructure | document contains query | `1 / (1 + extra heavy atoms)`, descending |
| superstructure | query contains document | document / query heavy atoms, descending |
| similarity | Morgan radius 3, 2048-bit Tanimoto | Tanimoto descending |

Every chemistry tie uses ascending numeric `record_id`, including worker-local
collection and global merging. IDs are returned as strings to retain u64
precision. Callers must provide unique stable IDs within an index. Graph rankings
also accept `stable_id` (constant score 1), `fewest_extra_heavy_atoms` for
substructure, and `greatest_query_coverage` for superstructure. Inapplicable
rankings are rejected. `include_identity=false` excludes bidirectional graph
matches from containment results. This deliberate default differs from legacy
Cheminee, which excludes identical canonical SMILES in containment searches.

Similarity accepts the existing typed SMILES request, including
`tanimoto_minimum`. It evaluates every fingerprint in the filtered search domain;
there is no TensorFlow model, candidate clustering, or approximate recall loss.
Basic accepts ordinary `query`, `extra_query`, `result_limit`, optional
`sort_field`, and `sort_ascending`. It uses ordinary text scores unless a sort
field is selected, then appends the stable ID tie. Basic hits are stored documents.

`num_hits` counts all verified/filter-matching documents, independently of the
return limit. Split failures return an error instead of partial results. There
is no arbitrary candidate shortlist before graph verification. The reusable
Tantivy `GraphQuery` asks a native verifier to evaluate each distinct prepared
SMILES among live candidate documents in a segment before its scorer exposes
matches to collectors. Metadata filtering remains in the explicit candidate query;
adjacent Boolean filters are not automatically pushed into it. This initial exact path does
not use fingerprint, descriptor, or scaffold screening. Morgan containment is
never a graph predicate. A future screen must prove that it cannot discard a
valid match; RDKit Pattern fingerprints are the relevant family for graph screens.

## Normalization contracts and reindexing

The RDKit version is pinned to `2026.09.1`. The fingerprint format remains
`morgan-r3-2048-lsb0-v1`, with chirality and feature invariants disabled. These
preparation identifiers are explicit, distinct index contracts:

* `sanitize-only-v1`: preserves the existing PR2 fingerprint-only workflow.
* `cheminee-fragment-tautomer-neutralize-v1`: fragment parent with
  `skipStandardize=true`, RDKit canonical tautomer, then Cheminee's custom atom
  neutralization. It preserves Cheminee's exceptions for aromatic charged atoms
  and negatively charged SP3 atoms. The result undergoes a sanitized SMILES round trip, initializing ring caches
  consistently before fingerprinting and graph matching.
* `cheminee-fragment-neutralize-v1`: the same fragment-parent and custom
  neutralization stages with tautomer canonicalization disabled.

Both ingestion and query preparation use the same implementation. Changing a
preparation identifier changes the fingerprint field's contract hash and requires
reindexing source SMILES. Query-time chirality controls graph matching; it cannot
restore stereochemistry removed by canonical tautomer preparation. Use the
preserve-tautomer contract when that distinction matters. The canonical mode
matches canonical representations; it is not exhaustive tautomer-aware subgraph
matching. RDKit's standard canonicalization defaults and enumeration limits are
part of the versioned behavior, matching Cheminee at
`f8d31a604203392f4dfba7d9a84120100b8426b5`. No chemistry repair or tautomer
expansion option is silently approximated. Those operations are unsupported.
Molecules reaching the native 1,000-match limit during custom neutralization
are rejected instead of receiving partial neutralization.
Plain SMILES are supported; names, whitespace and CXSMILES extensions are rejected.
Arbitrary CXSMILES properties and conformers are not preserved.

Graph search additionally requires the mapped prepared-SMILES field to be stored
and fast, with the raw normalizer, for example:

```json
{"name":"prepared_smiles","type":"text","indexed":false,"fast":true}
```

Existing splits with a stored-only prepared field must be reindexed before graph
search; changing the current mapping does not retrofit old splits. Fingerprint
search continues to work without this new fast field or native worker linkage.

The pure `tantivy-rdkit` crate owns query/scorer mechanics and ranking contracts.
`tantivy-rdkit-mapper` owns RDKit preparation and graph verification. Quickwit's
adapter serializes the prepared query and filter into its distributed query AST.
Native molecule handles are constructed within a segment verification call and
are dropped there. Shared queries contain only immutable strings, enums, and
contracts; there is no shared mutable RDKit molecule or new unsafe code.

Exact graph evaluation costs one parse and graph check per distinct prepared
molecule among live candidates per searched segment, plus candidate iteration.
The verification cache occupies memory proportional to encountered distinct values;
accepted document IDs and scores are also materialized before the infallible
scorer is returned. Broad queries can use more memory than the previous dictionary
score table. Entries outside explicit candidates and deleted documents are not
verified. Large-scale latency and memory benchmarking remain future work. See
[composable operators](../../docs/internals/composable-chemistry-queries.md) for
text/JSON syntax, scoring contexts, and the sibling-filter limitation.

## Reproduction

Use Ubuntu 26.04, the checksum-pinned S3 APT installer in `ci/install-rdkit.sh`,
and Rust 1.96. The existing CI krb5 compatibility wrapper remains unchanged.

```sh
cargo test --locked -p tantivy-rdkit-mapper --tests
cargo test --locked -p quickwit-query --lib
cargo test --locked -p quickwit-doc-mapper --features native-chemistry chemistry --lib
cargo test --locked -p quickwit-serve --features native-chemistry cheminee_api --lib
cargo test --locked -p quickwit-serve --features native-chemistry ensure_schemas_resolve --lib
cargo build --locked -p quickwit-cli --features native-chemistry --bin quickwit
python3 -m venv /tmp/chemistry-python
/tmp/chemistry-python/bin/pip install -r tantivy-rdkit/poc/requirements.txt
/tmp/chemistry-python/bin/python tantivy-rdkit/poc/graph.py --binary target/debug/quickwit --work-dir /tmp/graph-evidence
ldd target/debug/quickwit
```

The harness uses a root with no searcher service and two independent leaf worker
processes, shared filesystem split storage, and an exhaustive Python RDKit oracle.
It checks both normalization contracts, graph directions, chirality, salts,
tautomers, ranking, stable ties, filters, limits, totals, exact similarity, typed
client success/errors for all five routes, and 10,051 earlier stereochemical
false positives before a valid top-1 result. The Python wheel is an independent
oracle; server chemistry uses the pinned dynamically linked APT libraries.
