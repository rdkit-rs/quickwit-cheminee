# Native follow-up

The two-crate native SMILES path and packaging contract are documented in [tantivy-rdkit-mapper](../tantivy-rdkit-mapper/README.md). The assessment and measured results below describe the original PR #1 packed-fingerprint prototype.

# Cheminee worker-local similarity proof of concept

This private workspace crate demonstrates exact binary Morgan/Tanimoto scoring inside Quickwit split workers. It has no native RDKit dependency and is not a Cheminee or RX replacement. Quickwit remains responsible for splits, storage, publication, search distribution and result merging. The integration requires a maintained Quickwit source extension; this is not a runtime plugin or a drop-in replacement Tantivy crate.

## Inspected versions

| Component | Inspected revision |
| --- | --- |
| Cheminee 0.1.52 | `f8d31a604203392f4dfba7d9a84120100b8426b5` |
| Quickwit 0.9.1, implementation base | `962685f5a334f6c9d8516d2d7c1fdd08891b687c` |
| Quickwit main, inspection only | `d140cfc4bbcc37b73354a9d0e4f4b1a44639bb04` |
| Quickwit's pinned Tantivy 0.26.0 | `057458bf14d6973c9c97594c1d99580b6af4c49d` |
| Existing Cheminee dependencies | Tantivy 0.22.0, RDKit bindings 0.4.12, similarity model 0.1.6 |
| POC chemistry oracle | official RDKit Python wheel 2025.3.1 (`rdBase.rdkitVersion=2025.03.1`) |
| Build used | Rust 1.96.1, protoc 29.3, Linux, unoptimized dev binary without debug symbols |

The [0.9.1 release](https://github.com/quickwit-oss/quickwit/releases/tag/v0.9.1) and [architecture documentation](https://quickwit.io/docs/overview/architecture) were checked on 2026-10-09. The public documentation labels itself 0.9.0; release source is authoritative for this prototype. Main-only capabilities are not assumed available in the release. No claim of an upstream maintenance SLA is made.

## Existing semantics and feasibility

Paths below are relative to Cheminee at the inspected revision: [source tree](https://github.com/rdkit-rs/cheminee/tree/f8d31a604203392f4dfba7d9a84120100b8426b5/src).

| Behavior and source | Existing behavior | Quickwit path and remaining work |
| --- | --- | --- |
| Identity: `search/identity_search.rs`, `structure_matching.rs` | Descriptor/scaffold query, maximum 100,000 ordinary Tantivy hits, pattern-fingerprint equality, then bidirectional RDKit substructure checks with a chirality option. This is richer than a SMILES string comparison. | Existing API can filter descriptors or an explicit normalized identity key. Preserving graph identity needs exhaustive external verification or an in-worker graph predicate. Not implemented here. |
| Substructure/superstructure: `search/structure_search.rs` | Directional descriptor/scaffold filtering; maximum 100,000 candidates; directional pattern-bit containment; RDKit graph verification. Excludes equal canonical SMILES; tautomer/identity handling belongs to the surrounding API. | Property filters work through ordinary query AST. Safe bit screening and graph verification must occur before leaf top-k for guaranteed complete results. Native RDKit worker integration remains unproven. |
| Similarity: `search/similarity_search.rs`, REST similarity handler | Model-ranked clusters selected by search percentage; maximum 1,000,000 hits per tautomer; union by local document address; maximum Tanimoto over query tautomer fingerprints; threshold and descending score; response truncated to limit. Cluster screening is approximate, and the cap can lose recall. | This POC implements exact single-fingerprint Tanimoto over the property-filtered corpus. It deliberately does not reproduce approximate cluster selection, tautomer expansion or Cheminee preparation. Multi-fingerprint max scoring is a later bounded extension. Generic vector similarity is not equivalent. |
| Text/properties: `search/basic_search.rs`, `schema/mod.rs` | Tantivy QueryParser, TopDocs and Count; integer/float descriptors, JSON metadata with expanded dots; raw stored SMILES. Only `exactmw` is a numeric fast field in that schema. | Quickwit query syntax and typed mappings cover most primitives. Rebuild mappings; test tokenizer, numeric and nested-JSON differences rather than copy strings blindly. Candidate scoring is disabled inside this POC so BM25 cannot affect chemistry scores. |
| Layout | Fingerprints are stored bytes, not fast fields. Results fetch stored documents before chemistry verification. Segment ordinal/document ID is used for ordering and deduplication. | Reindex packed fingerprints into bytes fast fields. Use durable application record IDs: document addresses change across merges, splits and generations. Existing Tantivy directories cannot simply be registered as Quickwit splits. |
| Ranking/pagination: `search/mod.rs`, REST handlers | Structural/basic hits are ordered by segment/document address; similarity ties have no durable application tie-break. Limits do not provide a stable snapshot cursor. | Standard Quickwit distributed score collector can merge exact local top-k once the chemistry predicate/scorer executes before collection. POC uses score descending, unique numeric record ID ascending; no pagination endpoint. Future cursor must include generation and both sort keys. |
| Ingest: `indexing/mod.rs`, `search/compound_processing.rs` | Optional chemistry repair, fragment-parent selection, tautomer canonicalization, neutralization, descriptors, pattern/Morgan fingerprints, scaffold and learned-cluster assignments. | Keep RDKit preprocessing in a batch producer or a small compatibility service. Quickwit ingest transforms are not RDKit chemistry. Version the entire preparation policy and model. The fixture only sanitizes/canonicalizes SMILES. |
| Updates/deletes: bulk handlers and index manager | Local writer adds and commits; bulk delete builds a chemical/SMILES query and commits delete operations. No globally enforced unique record ID is established by this layout. | Quickwit is append-oriented with asynchronous delete/rewrites; it does not provide a transactional upsert substitute. Build immutable generations or explicitly design replay-safe incrementals and delete completion. POC offers neither. |
| Merges: `indexing/segment_manager.rs` | Application owns local Tantivy writer/segment merge lifecycle. | Quickwit must own merge planning, downloading, execution, upload and publication. Do not retain a second Cheminee segment manager over its data. |

There are no custom Tantivy Query/Scorer/Collector implementations to lift unchanged from the inspected Cheminee search code: the chemistry work follows ordinary query collection. The new crate moves one such operation into a real Tantivy query and scorer.

## Implementation map

* [`src/lib.rs`](src/lib.rs): packed fingerprint contract, schema check, `TanimotoQuery`, weight and scorer. No custom collector is needed.
* [`../quickwit-query/src/query_ast/tanimoto_query.rs`](../quickwit-query/src/query_ast/tanimoto_query.rs): serializable `tanimoto` AST and worker-side query construction. AST parser/visitor/transformer recurse through the candidate query.
* [`../quickwit-query/src/query_ast/mod.rs`](../quickwit-query/src/query_ast/mod.rs): chemistry incompatibility stays an error even when legacy split query validation is disabled. Silently treating an incompatible split as match-none would lose recall.
* [`../quickwit-doc-mapper/src/query_builder.rs`](../quickwit-doc-mapper/src/query_builder.rs): fingerprint fast-field warmup and candidate-posting warmup. [`tag_pruning.rs`](../quickwit-doc-mapper/src/tag_pruning.rs) delegates safe pruning to the candidate query.
* [`../quickwit-serve/src/cheminee_api.rs`](../quickwit-serve/src/cheminee_api.rs): Warp HTTP models, Utoipa-derived schema, validation and root request translation. No chemistry reranking in the coordinator.
* Existing [`leaf.rs`](../quickwit-search/src/leaf.rs), [`collector.rs`](../quickwit-search/src/collector.rs), [`root.rs`](../quickwit-search/src/root.rs): warm up, search splits, retain per-split top-k and merge global results using the same ordering.
* Existing indexer [`uploader.rs`](../quickwit-indexing/src/actors/uploader.rs), [`publisher.rs`](../quickwit-indexing/src/actors/publisher.rs), [`merge_pipeline.rs`](../quickwit-indexing/src/actors/merge_pipeline.rs): unchanged storage/publication ownership.

Each split retains its best k under the global total order. Any omitted local hit has at least k better hits in its own split, so it cannot belong to global top-k. This argument requires the complete chemistry predicate/score to run before local collection, consistent scoring and tie ordering, complete successful split coverage, and globally unique record IDs. The typed endpoint fails incomplete searches with 503. Exactness here means the defined f32 fingerprint score, not exact graph identity or parity with Cheminee's approximate candidate selection.

External verification is correct only if it receives every safely screened candidate, or uses a proven score bound and continues fetching until no unseen candidate can enter top-k. Taking a fixed BM25 page and reranking is insufficient. Pattern-bit containment is only a screen, never the graph answer. An in-worker RDKit predicate is architecturally possible through this same query path, but requires validated serialization, chirality/tautomer policy, native build compatibility, thread safety, bounded CPU, cancellation and memory tests. It has not been implemented or benchmarked. Independent RDKit bindings and Ubuntu 26.04/RDKit 2026.09.1 packaging work was left untouched.

## Fingerprint and HTTP contract

Format `morgan-r3-2048-lsb0-v1` is a 2048-bit binary Morgan fingerprint, radius 3, no chirality, no feature invariants, bytes ordered with bit n at `bytes[n/8] & (1 << (n%8))`. Hex input has exactly 512 characters. It is not a sparse/count fingerprint or an RDKit pickle. Producer and query must use the same RDKit version and preparation policy. Their nonempty, graphic-ASCII identifiers (maximum 128 bytes each) select a field named `morgan_` plus lowercase SHA-256 of:

```text
morgan-r3-2048-lsb0-chiral0-features0-v1\0{rdkit_version}\0{preparation_id}
```

The separators are actual NUL bytes. Labels prevent accidental schema mixing but cannot verify that a producer truthfully implemented the claimed preparation. Store one fingerprint per document in a bytes field with `fast: true`, `input_format: hex`; store a unique `u64` `record_id` with `fast: true`. Missing, multivalued or wrong-width indexed fingerprints fail the query. The current scan validates even deleted documents, so a poisoned segment can remain unavailable until rewritten. All-zero query fingerprints are rejected; an all-zero candidate scores zero. This explicitly differs from undefined zero-union division in the old function.

`POST /api/v1/{index_id}/cheminee/search/similarity` accepts `spec` and `fingerprint_hex`, plus omitted defaults `tanimoto_minimum: 0.4`, `result_limit: 100`, `extra_query: "*"`. Optional means omittable, not nullable. Unknown fields and null values are rejected. Limit is 1–10,000; threshold is finite 0–1 inclusive. There is no candidate cap. Index wildcards are forbidden. The response contains full matching count, hits, successful split count and elapsed time. Hit `record_id` is a decimal string; the stored document retains its numeric ID. Clients handling the numeric document ID must preserve integer precision.

`GET /api/v1/cheminee/openapi.json` exposes the dedicated derived OpenAPI 3.0.3 schema with stable operation ID `chemineeSearchSimilarity`; it is also merged into the existing full API schema. Typed failures use `{ "message": "..." }`. Invalid input is 400, missing index 404, incomplete split execution 503. With no searcher available, the existing root service currently returns 500. Body limit is 32 KiB. The generated schema documents these and existing capacity/timeout/transport errors. No unimplemented chemistry routes are advertised.

## Resource and deployment assessment

Quickwit uploads immutable splits and publishes searchable metadata separately; an uploaded file alone is not a visible index. Merges write replacement splits and publish replacement metadata. Query freshness follows publication, not merely producer acknowledgement. Delete rewrites and garbage collection need maintenance capacity. Use a concrete generation during a query; application-level atomic generation promotion and readiness checks remain necessary for consistent catalogs. Avoid using a mix of old/new versions as an implicit upsert mechanism.

A practical initial deployment candidate is one modest always-on search/coordinator host with persistent SSD cache, control-plane/metastore service and janitor, plus a separately scheduled batch indexer with scratch disk. For a distributed durable setup, use PostgreSQL for the metastore and object storage for splits; shared local file storage in this harness is only a test arrangement. Start capacity experiments around 2–4 vCPU and 8–16 GiB for the search host and 4–8 vCPU/16–32 GiB for batch indexing, then resize from measurements. These are test budgets, not demonstrated minimums or a cost-saving claim. Single searcher is a single point of availability failure. PostgreSQL, metadata service, membership and query ingress still consume resources while indexing is idle. Indexers may stop only after pending ingestion/checkpoints/publication and necessary merges finish; stopping indexers is not proof the whole system scales to zero.

Molecular queries often lack a useful time constraint and fan out to every split. Taxonomy/tenant tags can prune only when semantically safe. Small splits multiply planning, storage requests and merge overhead. Large splits increase per-task warmup and scoring memory. Quickwit's hotcache reduces opening work, but does not contain an entire chemistry column. Object-store range GET request counts, transferred bytes, repeated retries, cache eviction and merge read/write amplification must enter the cost model. A warm persistent cache is a capacity choice, not free statelessness.

This POC scores every unique fingerprint dictionary entry and validates cardinality for every document before candidate iteration. CPU is O(unique fingerprints × 256 bytes + documents); additional score storage is about 4 bytes per unique fingerprint per concurrent scorer, excluding warmed/compressed columns and Quickwit overhead. At one million unique fingerprints the uncompressed fingerprints alone are 256 MB per split. Several concurrent splits or requests multiply residency. Selective text filters do not avoid this initial scan yet. This is the central performance risk; use a lazy dictionary cache or safe popcount bounds only after correctness-preserving measurements. Do not assume log-search cache sizing predicts chemistry workloads.

Warm queries may reuse metadata, columns and result caches. Cold worker restart needs split discovery and data downloads; actual cold object-store latency was not measured. Batch ingest additionally consumes RDKit CPU, model memory, indexing buffers, upload bandwidth and temporary merge scratch. A small always-on query host may still fail latency targets on broad cold searches. Compare total monthly cost including object requests, PostgreSQL and burst merge compute before choosing Quickwit.

If exhaustive chemistry scans make this uneconomic, the bounded alternative is a versioned immutable Cheminee/Tantivy snapshot built by an intermittent batch job, copied from object storage to one query machine's local SSD and atomically activated. That preserves existing chemistry code with much less fork maintenance, at the cost of local full-index storage, slower cold start and coarser freshness. It does not require an unrelated search-engine rewrite.

## Reproduction and measured results

From `quickwit/`, install the toolchain in `rust-toolchain.toml` and protoc, then:

```sh
cargo test -p tantivy-rdkit -p quickwit-query --lib --tests
cargo test -p quickwit-doc-mapper chemistry_tests --lib
cargo test -p quickwit-serve cheminee_api --lib
cargo build -p quickwit-cli --bin quickwit
python3 -m venv /tmp/cheminee-poc-python
/tmp/cheminee-poc-python/bin/pip install -r tantivy-rdkit/poc/requirements.txt
/tmp/cheminee-poc-python/bin/python tantivy-rdkit/poc/run.py --binary target/debug/quickwit
```

Use `CARGO_BUILD_JOBS=4 CARGO_PROFILE_DEV_DEBUG=0` on a constrained build host. Harness prerequisites: free ports 17480–17502, disk for a three-process local cluster, and a fresh work directory. It disables telemetry, uses only public/synthetic molecules, retains inputs/configs/logs/results/schema/generated client under the reported artifact directory, and stops its own processes. It does not provision cloud resources or use private production data. Top-level Python dependencies and RDKit are pinned; record resolved transitive versions when promoting this into release CI.

Run on 2026-10-09: 620 accepted molecules (first 512 public RDKit NCI records, 96 synthetic molecules, edge cases), one deliberately invalid SMILES rejected. Public source SHA-256: `91e71c015f14939837f2943dcc904f7c87e5a3a0124d82b05c28ad2f23004def`; generated NDJSON SHA-256: `87493e23d1a694fa773a29de334bd72a68b759a17b0ffc7c25c583059859d2f9`.

* 168 exhaustive RDKit oracle checks: 7 queries × 3 thresholds × 4 property filters × 2 limits. IDs, counts and f32 scores matched.
* Seven initial published splits; eight after adding 10,050 duplicate fingerprints with distinct IDs. Top-1 returned ID 0 while full count was 10,051, proving the result limit is not a candidate limit.
* Root ran metastore/control-plane/indexer/janitor only; two separate searcher processes served leaves. Removing both leaves made a new query fail with 500 rather than execute chemistry in the coordinator.
* Malformed indexed fingerprint caused 503; incompatible preparation caused 400. Invalid values, nulls, unknown fields and missing index were checked.
* OpenAPI validation and repeated deterministic generation passed. `openapi-python-client 0.29.1` generated a real client that received a typed 200 response and typed 400 error.
* Local filesystem, dev binary: first measured query 90.9 ms, median of the 168 mixed queries 65.8 ms, maximum 149.9 ms. These are small-corpus functional timings, not cold-S3 measurements, warm-cache percentiles, production throughput or a Cheminee speedup comparison.

The harness intentionally disables merges to force multi-split coverage. Merge/delete behavior, restart recovery, replay/lost acknowledgement, saturation, cold-cache RAM peaks and million-molecule performance remain unmeasured. Native Cheminee end-to-end parity is not established by the fingerprint oracle.

Local Rust validation: 160 query tests, 3 reusable scorer tests and 3 chemistry API tests passed. The full mapper suite had 222 passes and one failure in `test_concatenate_multiple_field`; the same ordering assertion failed on the unchanged pinned upstream base. Both new chemistry mapper tests passed. The final CLI build succeeded. Rust formatting succeeds, but `make fmt` fails the existing license-header gate on the three new Rust source files: that gate demands a comment block, conflicting with the task's explicit no-new-code-comments constraint. The checker and existing licensing were not weakened or removed. The focused GitHub workflow is supplied for repeatable distributed/client validation; local results do not establish its remote status.

## Staged decision gates

1. Keep this slice isolated: review query semantics, generated contract, mixed-version failure behavior and measured evidence. Do not migrate production.
2. With the independent bindings work ready, produce identical prepared molecules/fingerprints from current Cheminee and the proposed producer. Test salts, isotopes, charges, aromatic forms, tautomers, stereoisomers, empty/invalid structures and errors. Add max-over-tautomers deliberately; compare approximate legacy results separately from exhaustive truth.
3. Expand a deterministic public/synthetic corpus to 100k and 1M distinct molecules. Vary split count, k, threshold and filter selectivity; collect cold restart versus warmed p50/p95/p99, concurrency, RSS, CPU, cache bytes, GET counts/bytes and merge amplification. Re-run after merge and delete. Require stable IDs and identical scores/counts to the exhaustive oracle. Set latency/cost acceptance targets before paying for cloud tests.
4. If identity/substructure is essential, prove the native graph predicate in workers before claiming feasibility for the whole product. A sidecar remains suitable for normalization, not arbitrary capped reranking. Reject the Quickwit approach if verification resource bounds or maintenance burden fail the agreed limits.
5. Build the smallest RX adapter only after semantics pass: SMILES query preparation, array standardization/conversion, metadata ID preservation, and its actual bulk contract. RX currently expects large bulk completion to be durable. Add batch IDs, per-document outcomes, replay/lost-ack recovery, generation readiness and explicit promotion. Current raw ingest plus `commit=force` is not evidence of these guarantees. Generate and test the real Ruby client from the agreed schema then; the Python smoke test proves this POC's wire contract only.
6. Shadow read traffic against immutable generations, evaluate rollback and freshness, then request separate approval for any production migration. No production services, credentials, independent RDKit branches or package releases were changed by this work.
