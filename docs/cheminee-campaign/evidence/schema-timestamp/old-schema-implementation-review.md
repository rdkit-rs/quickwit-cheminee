# Independent review of the old-schema implementation

Follow-up: `old-schema-final-review.md` records the completed bounded review and closes the specific pending checks below. This file preserves the earlier review state.

Reviewed 2026-10-16, WIP over `c15204119d29285511ac1a5563732a6a714a3315`. The reviewed source hashes are retained in `old-schema-implementation-reviewed-files.json`. No source edits were made by this reviewer. The concurrent timestamp-pruning patch is outside this review.

**The core implementation follows the agreed design; no semantic blocker was found in its schema separation, physical checks or warmup filtering. Old-schema end-to-end acceptance remains pending the checks below.** This is a scoped implementation review, not complete relevance or campaign approval.

## Source findings

`BuildTantivyAstContext::chemistry_schema` is supplied from the current mapper and used only by the three chemistry constructors. Candidate ASTs, ordinary clauses, required terms, query terms and warmup field IDs still use `context.schema`, the physical split schema. The constructors retain strict current-schema checks; `validate_graph_contract`, native input validation and the `InvalidChemistry` exception under disabled ordinary-schema validation remain intact. I found no current-schema field-ID leak.

`validate_fingerprint_field` performs exact-name bytes/fast validation. Graph retains its spec through cloning and weight construction and checks both the requested fingerprint identity and prepared text/stored/fast/raw contract. Both scorers validate the physical segment after candidate scorer construction, deleted-document skipping and the empty-domain return. Graph matcher setup remains before that return. Existing candidate errors and per-value errors continue to propagate. Checking the exact schema before a typed fast-field lookup also prevents `_dynamic` from substituting for the declared chemistry field.

The chemistry warmup `is_ok()` calls are limited to pure schema validation; they do not catch I/O errors. An incompatible physical contract omits only its chemistry column warmup, while current constructor validation still occurs before a usable query is returned. Candidate traversal continues even for incompatible outer chemistry. A live candidate rechecks the physical contract before reading its column, so omitted warmup does not turn a required invalid field into an empty result.

The ordinary warmup adjustments are also narrowly justified. With validation disabled, absent/non-fast range fields already compile to empty under existing schema-evolution semantics; their warmups can be omitted. Eager current-schema validation remains strict. Absent term-set fields are skipped only with validation disabled. Non-indexed term-set fields no longer request an inverted dictionary; their fast-column warmups are still collected by `TermSearchOnColumnar`. No global error suppression was introduced.

## Evidence inspected and rerun

- `old-schema-mapper-test5.log`: initial mapper matrix passed. It uses `DocMapper::query(old_schema, ..., false, None)`, real physical indexes, an absent/live ordinary candidate, seven physical variants and three operators. Deliberately unequal `family` field ordinals plus the valid positive control are meaningful protection against ID leakage.
- `old-schema-mapper-suite.log` and its status JSON: **231 native mapper tests passed**, including the new absent-term-set/non-fast-range sentinel; exit zero, no disk-headroom stop.
- I independently executed the retained native mapper test binary's chemistry subset: **5 passed**, zero failures, in `old-schema-independent-mapper.log`. This is an independent rerun of the compiled binary, not a separate compilation.
- `git diff --check` passed.

## Required follow-ups before closing the bounded gate

1. **Refresh and run the existing scorer regression oracle.** `tantivy-rdkit/tests/composable.rs::graph_and_fingerprint_require_columns_only_for_live_candidates` still expects `missing ... fast field`. For its old schema the new physical validator now fails earlier with `index does not contain the requested fingerprint specification`. This is a source-predicted test mismatch, not an independently observed failing run. Update the expected contract error intentionally and rerun the core scorer tests, preserving deleted-only, nested-candidate-error and failing-matcher setup assertions.

2. **Strengthen the mapper matrix's warmup boundary assertions.** It currently asserts candidate postings but does not explicitly assert omission/presence of chemistry fast fields. Assert that incompatible chemistry fields are absent, compatible fields remain, and ordinary candidate warmups survive. Add prepared wrong-type/not-stored and dynamic-name trap variants. These directly protect the contract checks introduced here. Preserve eager invalid-current-declaration tests; the current new matrix's malformed hex/SMILES assertions cover inputs only.

3. **Complete actual native HTTP warmup execution.** Keep old and new mapping UIDs/splits, an untagged ordinary exclusion field, no timestamp pruning, live old rows, strict exact counts and hit IDs, and cold/repeated requests. Show irrelevant old incompatibility succeeds while live-old verification fails with its physical-contract cause. Mapper execution alone does not invoke production asynchronous warmup.

Compatible-but-damaged column I/O remains a separate limitation: chemistry columns still warm before candidate evaluation, and shared columnar metadata can be read when opening the segment. General OR relevance, broader schema evolution, timestamp top-K correctness, full workspace validation and operational/release gates are not approved by these results.
