# Chemical parity is not physical-schema or algorithm parity

The benchmark matches chemical values and explicitly audits query results. It
**does not** hold storage layout, candidate routing, retrieval or query algorithms
identical. These are complete implementation comparisons, not an isolated
measurement of the underlying search engine.

## Verified effective schemas

The retained Cheminee control index `meta.json` was checked against source at
`f8d31a604203392f4dfba7d9a84120100b8426b5`; Quickwit's retained run configuration
was checked against measured `7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b`.

| Field | Cheminee descriptor_v1 | Measured Quickwit flat schema |
|---|---|---|
| Morgan | bytes, stored=true, fast=false, indexed=false | bytes, stored=true, fast=true, indexed=false |
| Pattern | stored-only bytes | stored-only bytes |
| Prepared SMILES | raw indexed/stored text, not fast | raw indexed/stored/fast text |
| 43 numeric descriptors | indexed, not stored; only exactmw fast; numeric fieldnorms enabled | indexed, not stored; only exactmw fast; numeric fieldnorms disabled |
| extra_data | indexed/stored JSON, not fast | indexed/stored JSON, not fast |
| other_descriptors | indexed/nonstored JSON, not fast | indexed/nonstored JSON, not fast |
| Stable record ID | searchable metadata property | additional indexed/stored/fast u64 field |

Quickwit's Morgan field is named by the fingerprint-specification hash. Its
stored=true is explicit in the measured config; examples which omit the flag
also inherit Quickwit's stored=true default. Thus current benchmark indexes have
both a fast-field and document-store representation of Morgan. Temporary decode
buffers and score tables are separate from persistent payload duplication.

The historical fixed-schema studies did not silently change Cheminee to fast
fingerprint scoring. Native preparation experiment 003 retained the same broad
flat field contract. Experiment 004 later moves numeric descriptors into one
stored/fast JSON object; it has correctness evidence, not matched performance.

## Actual scorer paths

Cheminee's `neighbor_search` encodes query fingerprints with TensorFlow and ranks
learned clusters. `build_similarity_query` combines selected cluster terms with
extra metadata/descriptor filters. `basic_search` collects up to 1,000,000
candidate document addresses. This cap is above this 100k corpus but matters at
larger scale. The benchmark passes 0.1% clusters for the default approximate
path and separately tests 100% clusters for an exhaustive probe.

For each candidate, `get_best_similarity` calls `searcher.doc<TantivyDocument>`
and extracts Morgan, SMILES and extra_data from stored fields before computing
Tanimoto. The bitvec implementation constructs AND/OR bit vectors and counts
ones. Results below threshold are removed, survivors are score-sorted, and the
REST handler truncates to result_limit. Stored-document retrieval and metadata
materialization occur before final ranking. Default cluster routing can omit
true threshold matches; valid scores do not establish complete recall.

Quickwit's `TanimotoWeight::scorer` opens `fast_fields().bytes(field)`, enumerates
all dictionary ordinals, decodes each fingerprint and builds a per-ordinal f32
score table. It validates exactly one fingerprint per document. Candidate
filters are then traversed and document ordinals select precomputed scores.
Restrictive filters therefore do not avoid initial dictionary-wide scoring.
The current kernel uses bytewise AND/OR popcounts over packed 256-byte Morgan
values. Exact threshold matches are counted; global top-k sorts by descending
score and ascending stable record_id. Root/leaf search fetches stored documents
for returned hits. The API returns those hydrated documents, including stored
fingerprints, so response sizes also differ from Cheminee's projection.

Native similarity does not use learned-cluster routing, even though ingestion
still computes cluster assignments for descriptor compatibility. Query caches
can accelerate repeated identical requests. Ordinary bytes fast fields in the
pinned Tantivy revision are dictionary plus ordinals, not a fixed-stride matrix.
A fast field permits column-oriented scoring without retrieving every stored
document; it does not by itself guarantee contiguous raw vector rows.

## Source evidence

- [Cheminee schema](https://github.com/rdkit-rs/cheminee/blob/f8d31a604203392f4dfba7d9a84120100b8426b5/src/schema/mod.rs#L13)
- [Cheminee routing and scoring](https://github.com/rdkit-rs/cheminee/blob/f8d31a604203392f4dfba7d9a84120100b8426b5/src/search/similarity_search.rs#L69)
- [Quickwit scorer](https://github.com/rdkit-rs/quickwit-cheminee/blob/7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b/quickwit/tantivy-rdkit/src/lib.rs#L205)
- [Quickwit request and response integration](https://github.com/rdkit-rs/quickwit-cheminee/blob/7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b/quickwit/quickwit-serve/src/cheminee_api.rs#L97)
- [Exact dependency pin](https://github.com/rdkit-rs/quickwit-cheminee/blob/7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b/quickwit/Cargo.lock#L11992): Tantivy 0.26.0, `057458bf14d6973c9c97594c1d99580b6af4c49d`; Cheminee uses Tantivy 0.22.0.

These observations describe existing benchmark paths. They do not authorize or
imply a modified Cheminee baseline. A future fast-field or fixed-vector comparison
must be a new experiment with explicit schema, algorithm, recall and lifecycle
boundaries.
