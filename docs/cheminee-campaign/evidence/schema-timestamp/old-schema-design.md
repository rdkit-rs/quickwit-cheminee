# Old physical schema: independent implementation design

Reviewed 2026-10-16 against `c15204119d29285511ac1a5563732a6a714a3315` in `/workspace/quickwit-cheminee-pr3-inspection`. Read-only source review; no new runtime result is claimed. This refines `/workspace/recovery/selective-relevance-review.md` under the accepted relevance-based contract.

**Implement a narrow separation between current chemistry declarations and physical split requirements.** Validate query inputs/current declarations eagerly; validate old split chemistry fields only after finding a live verification candidate. This can close missing/incompatible chemistry-schema failures for proven-empty candidate domains. Compatible-but-damaged column I/O, general OR relevance and timestamp-sort pruning remain separate gates.

## Evidence and invariant

`quickwit/quickwit-search/src/root.rs:254` already compiles the original query against each current index mapper before candidate narrowing (`:282`). `quickwit/quickwit-doc-mapper/src/doc_mapper/doc_mapper_impl.rs:666` then serves both root and leaf compilation, but supplies only `split_schema` to `BuildTantivyAstContext`. The production leaf passes `index.schema()` and `with_validation=false` (`quickwit/quickwit-search/src/leaf.rs:737`). All three chemistry AST constructors currently use that schema; their `InvalidChemistry` errors deliberately survive disabled ordinary-schema validation (`quickwit/quickwit-query/src/query_ast/mod.rs:247`). Thus an old split fails during compilation before its empty candidate set can be proved.

Existing scorer tests at `quickwit/tantivy-rdkit/tests/composable.rs:345` construct queries directly against a newer schema, bypassing this mapper compilation path. They establish candidate-first scorer behavior, not production old-schema compatibility.

The invariant is: a valid current chemistry request with no live candidate in a physical segment yields no chemistry matches there; a live candidate needing missing/incompatible chemistry data fails that segment. Invalid query/spec/options/native capability/current declarations remain errors even beneath `match_none` or impossible minimum-should-match. Ordinary candidate queries continue to use the physical schema and its field ordinals.

## Small coordinated patch

1. Add a separate borrowed current chemistry schema to `BuildTantivyAstContext` (`quickwit-query/src/query_ast/mod.rs:205`). `DocMapper::query` supplies `&self.schema`; `for_test` initializes both schema references to the same schema. Keep `schema` as the physical schema for ordinary AST compilation, required terms, warmups and candidate field IDs. Change only fingerprint-contains, Tanimoto and graph constructor schema arguments to the current chemistry schema. Their candidate ASTs still receive the unchanged context. No serialized query or HTTP schema change is needed.

2. Factor pure physical-contract helpers from `FingerprintQuery::new` (`tantivy-rdkit/src/lib.rs:188`), `MoleculeFields::from_schema` (`tantivy-rdkit/src/schema.rs:40`) and `GraphQuery::new` (`tantivy-rdkit/src/graph.rs:72`). Reuse them in constructors and scorers. Fingerprints require the exact requested named bytes/fast field. Graph requires that fingerprint contract plus exact prepared text/stored/fast/raw field. A string column alone does not establish raw normalization. Retain the graph fingerprint spec or derived name through query clone and weight construction; it is currently discarded.

3. In both scorers, keep candidate weight/scorer errors visible, skip deleted candidates, and return empty only after reaching `TERMINATED`. Then validate `reader.schema()` before opening chemistry columns (`lib.rs:260`, `graph.rs:124`). Keep graph matcher setup before the empty return. Preserve all subsequent column/cardinality/value/score checks. Validate each segment independently. A typed column accessor must not substitute for exact schema validation: Tantivy can resolve an absent name through `_dynamic`.

4. Separate chemistry warmup collection from ordinary range fields in `quickwit-doc-mapper/src/query_builder.rs:34`. Add chemistry warmups only when their exact physical contract is compatible, using the same pure helpers; graph only needs to warm the prepared column it reads. Always visit candidate subtrees, including incompatible outer chemistry. Warmup omission is not a success verdict: live-candidate scorer validation remains authoritative. Preserve ordinary warmups and physical field IDs. Keep `validate_graph_contract` (`chemistry.rs:291`), native graph input validation, and the `InvalidChemistry` exception under `with_validation=false` intact.

Tantivy's `fastfield/readers.rs:33,79` resolves unknown names through `_dynamic` and rejects named non-fast fields. `quickwit-search/src/leaf.rs:411` invokes that resolver during warmup, before scorers. This is why constructor deferral alone is insufficient.

## Adjacent warmup cases to resolve or explicitly leave open

Two additional gaps are source-inferred and need regressions before claiming arbitrary old-schema candidate compatibility:

- A term-set candidate on an ordinary field added only in the current schema compiles to no physical terms with validation disabled, but `query_builder.rs:274` still returns `field does not exist` while collecting its warmups.
- A range on a current fast field that was non-fast in an old schema becomes a nullified physical query, but `QueryFastFields` still requests its warmup; Tantivy then rejects the non-fast field.

The narrow correction is for these warmup collectors to reflect established physical compilation semantics: omit absent term-set fields and non-fast/unresolved range fields when they cannot supply a compiled physical predicate. Root validation must still reject invalid current declarations, and valid dynamic/JSON paths must retain their warmups. Test each independent of chemistry first, then as chemistry candidates. Do not hide general I/O or parsing errors to achieve this. If deferred, list these cases as remaining blockers, not as covered by the chemistry-schema fix.

## Mapper/scorer regression matrix

Use a valid current `DocMapper` and real old-schema RAM index. Call **`mapper.query(old_schema, ast, false, None)`**, then execute its returned query. Build the index with physical field ordinals deliberately different from the mapper. Use no-merge deletion fixtures and assert `max_doc > num_docs > 0` to make deleted-only cases non-vacuous.

| Dimension | Minimum cases and oracle |
| --- | --- |
| Operators | Tanimoto, both fingerprint containment directions, and native graph. |
| Physical fingerprints | Missing exact field, wrong type, non-fast; all must compile with valid logical declarations. Empty/deleted-only domain returns zero; live domain errors. |
| Physical prepared field | Missing, wrong type, not stored, non-fast, nonraw. Include raw prepared text with missing/wrong fingerprint to prove graph checks its full contract. Same empty/live oracle. |
| Domains | Explicit `match_none`; ordinary term/range with no live matches; deleted-only term; one live match; all documents; candidate chemistry that itself errors. Preserve nested candidate errors when that candidate is needed. |
| Compatible control | Reordered ordinals with valid data returns known IDs/scores; candidate term postings use old physical field IDs. Declared-but-unpopulated chemistry fields still fail for live candidates. |
| Warmups | Incompatible chemistry absent from warmup; ordinary candidate postings/ranges retained. Missing exact prepared field plus a tempting `_dynamic` value cannot satisfy graph. Compatible chemistry remains warmed. |
| Eager inputs | Bad hex, out-of-range threshold, invalid spec, malformed SMILES/native-spec mismatch, mismatched current graph mapping, current nonraw/non-fast declaration. Reject beneath dead Boolean branches and impossible minimum-should-match, in both clause orders. Keep non-native capability rejection. |
| Warm/cache behavior | Empty result repeated; live-error request before and after empty request; scoring and count-only. Errors must never become cached empty success. |
| Ordinary evolution sentinels | Current-only term-set field; formerly non-fast range field. Verify ordinary zero first, then chemistry candidate zero, or retain explicit failing evidence. |

The mapper suite must inspect the returned warmup metadata. Native HTTP supplies the actual warmup execution proof. Keep the existing strict direct-constructor and failing graph-matcher setup regressions.

## Bounded native HTTP fixture

Real schema evolution is available through `PUT /api/v1/indexes/{id}` (`quickwit-serve/src/index_api/index_resource.rs:299`). Preserve the full config and supply a fresh mapping UID; `quickwit-config/src/index_config/mod.rs:681` permits mapping changes while preserving timestamp and tokenizer constraints.

Create disposable no-merge indexes with old mappings and live old documents, publish, update to a valid current native chemistry mapping, then ingest known current molecules. Retain split IDs and mapping UIDs proving old and new physical generations coexist. A plain exact `match_all` count must include both. Use an **untagged** exclusion field with no timestamp bounds: the existing harness tags `family`, which could prune the old split before leaf compilation and produce a misleading pass. Assert expected shard totals as well as zero failures on successful responses.

Cover at least missing chemistry fields, non-fast fingerprint, nonraw prepared text, and missing exact prepared field with a dynamic-name trap. Mapper tests cover the remaining physical variants. For each applicable operator run strict `track_total_hits=true` requests at size zero and with hits:

- Explicit candidate selecting no old live rows: exact zero on an old-only selection, and known current IDs/count when current rows qualify.
- Equivalent necessary sibling predicate in each clause order versus explicit candidates: same IDs/count/scores with no failed shards.
- Unbounded/live-old candidate, relevant `OR(match_none, chemistry)` and pure NOT: fail with the physical-contract cause; strict HTTP must not report partial success. Inspect one unchecked response to ensure its failed-shard metadata survives.
- Invalid query input under empty candidates/dead Boolean scopes: HTTP 400. Stored physical incompatibility with relevant live rows: strict HTTP 500, consistent with `SearchError::from(TantivyError)` (`quickwit-search/src/error.rs:127`).

Run cold and repeated/warm requests and retain exact binary hash, request/response/status, expected oracle, split/mapping identities and logs. Do not use count-only `OR(match_all, chemistry)` as a passing oracle while the broader OR gate is open. Deleted-only physical retention is a mapper requirement unless the HTTP fixture proves the old segment remains present after deletion.

## Scope limit and observability

Compatible chemistry columns are still warmed concurrently with candidate postings (`leaf.rs:304`). A damaged file can fail before candidate emptiness is proved; `FastFieldReaders::open` also reads shared columnar metadata. Closing that broader I/O guarantee requires staged reads or a separately bounded storage-failure contract. Skipping incompatible-schema warmups does not establish it.

Keep physical failures attributable to the requested field/contract and failed split, with no raw molecule/document logging. Existing structured failed-shard reporting is sufficient for this patch; no new general retry or metrics framework is needed. Approval should name the tested old-schema variants and candidate forms only, leaving full relevance/campaign readiness open.
