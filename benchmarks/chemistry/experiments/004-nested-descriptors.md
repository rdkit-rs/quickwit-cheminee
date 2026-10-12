# 004: nested descriptor correctness

Status: correctness complete; performance unmeasured. Backfilled 2026-10-12.

## Change and exact comparison

Quickwit `6bf1e29cdbf03409287b2f7d0e59a4c19534d8fa` adds explicit
`chemistry.descriptor_layout: nested`. All 43 numeric properties live under one
indexed, stored, fast JSON `descriptors` field. Default flat mapping remains
compatible. Fingerprints, scaffolds and learned clusters keep their prior fields
and algorithms. Derived client values are rejected, including dynamic mappings.
The common Cheminee/bindings/model revisions remain unchanged.

This is a schema feature and correctness study, **not an indexing benchmark**.
The preceding measured binary is `7d9a4f17a09cfb68b88f7d81cfa0aa2570ac677b` with
flat numeric fields, only exactmw fast, and numeric values not stored. No timing
claim in experiment 003 applies to nested storage or all-property sorting.

## Verification and results

Nine mapper tests, 352 nested REST golden checks, 82 additional range/Boolean/
sort/missing/null and actual graph/similarity prefilter checks, plus 352 legacy
flat REST checks passed. Local all-feature Clippy and formatting passed.

Example query forms: `descriptors.NumAtoms:>10`,
`descriptors.NumAtoms:[10 TO 20]`,
`descriptors.exactmw:[136.2 TO 10000]`. The colon is required. Property sorting
uses the fast JSON path. Migration requires a new index/reingestion and prefixed
client numeric paths; changing a schema cannot retrofit existing split columns.

Native numeric audit values match exactly. REST JSON transport showed one-ULP
differences for 18 of 344 sampled f64 values; integer values/types matched and
all query result oracles passed. This qualification is retained rather than
claiming bitwise float identity after JSON transport.

No Tantivy fork was required: Quickwit's query AST supports these fast JSON
paths. Bare QueryParser limitations in separate probes are not failures of this
production REST path. Correctness probes and small fixtures are not throughput
repetitions. CPU stages, peak memory, transfer rates and lifecycle performance
were not measured for the nested schema.

## Commands and public evidence

The code revision includes the descriptor REST audit and distributed chemistry
CI, which exercise actual HTTP/gRPC endpoints rather than mocked mapping.
Exact-head workflows:

- [Main CI](https://github.com/rdkit-rs/quickwit-cheminee/actions/runs/38178881701): passed.
- [DataFusion CI](https://github.com/rdkit-rs/quickwit-cheminee/actions/runs/38178881700): passed.
- [Distributed chemistry](https://github.com/rdkit-rs/quickwit-cheminee/actions/runs/38178881847): passed.
- [Dependency review](https://github.com/rdkit-rs/quickwit-cheminee/actions/runs/38178881740): unsupported repository dependency-graph setting; unchanged.

[Public findings](https://github.com/rdkit-rs/quickwit-cheminee/pull/3#issuecomment-6114473923)
separate this head from the flat performance baseline. Chemistry CI artifact
`cheminee-poc-evidence`, ID `11717940341`, 758,237 bytes, SHA-256
`e4ed28d682f12f21ef759ca68821e2fe036a03bdaf7db1ef0787820eaae00b5d`
is associated with the exact head. Artifact retention is finite (recorded expiry
2027-01-09). Local large diagnostic bundles are not published by this backfill.
