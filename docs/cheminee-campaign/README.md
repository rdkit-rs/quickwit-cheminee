# Cheminee importer campaign — recovery-blocked preparation

Status: **no release gate has passed in this session**. This is a reviewable
preparation branch based on public PR3 `6bf1e29cdbf03409287b2f7d0e59a4c19534d8fa`.
It is not the recovered composable-query branch. No server behavior was changed,
gem generated, package published, deployment performed, or production data touched.

## Sequenced decisions (2026-10-16)

1. Preserve unpublished work. The required final commit is
   `276bd1ab7455d0141bd8d9427d00acb1bb7ad845`, branch
   `cheminee/composable-query-review`. The Library handoff
   `libfile_5c71df73a9e08191b0930d55a07d44a5` resolves to a 7,569,368-byte tar.gz,
   but its supported download helper fails. A host-only network probe identifies
   HTTP CONNECT 403 from the execution-environment proxy. Refreshing the transfer,
   explicitly enabling network access, and running outside the sandbox did not
   recover bytes. Archive hash, gzip integrity, Git bundle, and final tree remain
   unverified. Do not apply this preparation branch as a replacement for that work.
2. Inspect a separately named PR3 checkout while blocked. Its HEAD matched the
   supplied public base exactly. No AGENTS.md was found in the workspace. The
   selected saved environment contains other RDKit repositories but no prior
   Quickwit checkout, controlled-study directory, or supplied corpus at the named
   locations. It has Docker and Java; Ruby and Cargo are absent from PATH.
3. Recover benchmark text independently. Read all 5,905 lines of Library checkpoint
   `libfile_470ec6694a7c8191abbbc7bcb86622c9`, version 23, in six chunks. Reassembled
   JSON parses and is 248,516 bytes with its final newline, matching metadata size.
   This is text reconstruction, not binary-hash verification. Preserve the embedded
   [report](evidence/controlled-study-report.md),
   [archive manifest](evidence/controlled-study-archive-manifest.json), and
   [source/provenance audit](evidence/source-audit.json). The seven binary archive
   parts and original indexes are not recovered. No expensive benchmark was rerun.
4. Move catalog correctness before performance. Stable supplier IDs do not imply
   upserts or WAL deduplication. Unknown write outcomes must block activation.
   Evaluate immutable staging generations with validated counts and unique IDs,
   an atomic compare-and-swap activation pointer, and retained rollback generations.
   This is a proposed application contract, not an existing server feature.
5. Preserve the generated shipping experience. Inspected the existing server
   [Ruby workflow](https://github.com/rdkit-rs/cheminee/blob/main/.github/workflows/generate_ruby_gem.yaml):
   tag-triggered server build/spec export, Ruby/Faraday generation, client commit/tag,
   then RubyGems publication. Prepare build artifacts without those external writes.
   Pin a released generator (not the existing client's 7.11.0-SNAPSHOT), templates,
   dependencies and source revision. Do not claim tooling is pinned until its
   checked-in digest is verified and generation reproduces byte-for-byte.
6. Export from server code. Start with `quickwit_serve`'s combined `build_docs()`;
   deliberately select public chemistry and importer lifecycle operations, retain
   transitive schemas, and reject missing references. Chemistry-only schema surfaces
   omit ingestion/index management. Do not use the old gem's stale checked-in spec.
   Use `QuickwitCheminee` as a distinct proposed namespace; generated class names
   and call examples must be confirmed by generation. No global Searchkick patches.
7. Independent `gpt-6-astra`, max-effort design review completed against PR3. It
   blocks release on catalog promotion, incomplete search, chemistry semantics,
   actual wire serialization, and independent offer identity. Implementation and
   readiness approval remain pending; a source review is not a runtime test.
8. Keep the publication hold. No credentials, remote branches/tags, packages,
   infrastructure, or production catalogs may be created/changed by this work.

## Confirmed source hazards

| Contract | PR3 finding | Required evidence before release |
|---|---|---|
| NDJSON | Ingest annotation advertises `application/json` string and omits `detailed_response` | Generated Faraday sends exact newline-separated bytes; no JSON wrapping; response counts and rejections survive decoding |
| Accepted batches | HTTP 200 may contain rejected records; legacy v1 lacks accepted/rejected counts | Mixed-validity batch; absent counts treated as unknown; promotion forbidden with rejection or unknown acceptance |
| Uncertain writes | Document UIDs do not deduplicate WAL appends; timeout may precede late append | Lost acknowledgement, late append, duplicate submission, interruption and restart; no blind write retry |
| Partial results | ES conversion can emit `relation: eq`, `timed_out: false`, nonzero `_shards.failed` and empty failure details | Fail closed by default; deliberate partial mode visibly incomplete; check every page and top-level errors |
| Scroll | Strict `allow_partial_search_results=false` is unsupported | Do not use scroll for completeness proof without a tested strict alternative |
| Graph identity | `use_chirality` defaults false; preparation and fingerprint contract required | Explicit stereo/salt/tautomer policy; malformed candidates; independent exhaustive RDKit truth |
| Pagination | Legacy five routes cap returned hits at 10,000 and expose no cursor/offset | Distinguish returned hits from total; test unpublished DSL separately; no invented cursor support |
| Nested metadata | Nested descriptors do not establish correlated arrays of offers | Cheap offer and available offer on different suppliers must not cross-match |

Source hashes are recorded in `evidence/source-audit.json`. These findings apply
to the public base; the unpublished DSL needs fresh review after recovery.

## Gate order and release checklist

- [ ] Recover archive bytes through an authorized reachable transfer; verify archive
  integrity and any included checksums, inspect paths before extraction, verify Git
  bundle and exact final SHA, check clean status and ancestry from PR3. Preserve
  archive, bundle and patches before applying preparation changes.
- [ ] Run outstanding validation on recovered code, recording commands, feature
  flags and failures. Historical 174 aggregate tests and 16 HTTP cases are supplied
  checkpoint evidence with overlap, not fresh totals; workspace CI remains unrun.
- [ ] Prove Boolean truth and missing-field behavior; malformed chemistry candidates
  under AND/OR/NOT, clause reordering and limits; explicit candidate error domains
  versus sibling filters; failed leaves, empty results, counts and deterministic ties.
- [ ] Use one offer per document until correlation is proven. Keep supplier/source
  offer key, structure identity, provenance and observed-at time separate. Test
  salts and stereochemistry preservation and u64 record-ID round trips/uniqueness.
  Scraped availability is dated information, never a live-stock guarantee.
- [ ] Test repeated batches, changed price, withdrawn offer, partial scrape, stale
  update, concurrent activation, ambiguous acknowledgement, late append and restart.
  Incomplete scrapes must preserve the previous complete generation. Define accepted,
  persisted, published and searchable barriers separately. Prove activation/rollback
  atomicity and pointer recovery before claiming safe refresh or exactly-once effects.
- [ ] Correct server schema annotations; export from exact source and record schema
  SHA-256, server SHA, features, preparation/RDKit identity, generator/template hashes,
  gem version and dependency lock in the immutable build manifest.
- [ ] Build and install the generated gem outside its source directory. Load it
  alongside `Cheminee`. Real HTTP tests must cover create-index, raw SMILES and
  nested metadata ingest, mixed rejects, all five legacy searches, DSL searches,
  incomplete results, typed errors and sanitized request-ID diagnostics.
- [ ] Give Steven one verified initialization/import/filtered-search example and
  migration examples for changed GET/POST routes, defaults and contracts. Add a
  narrow helper only if wire tests show generated methods cannot meet a real need.
- [ ] Pin Compose images/build inputs with distinct names, ports and volumes beside
  Elasticsearch. Test readiness, start/import/search/restart and bounded overload.
  Measure idle/import/query/peak cgroup memory and process RSS separately; publish
  neither a memory target nor ARM64 support without execution evidence.
- [ ] Profile selective/broad/empty/novel exact queries and client end-to-end latency.
  Attribute RDKit, parsing and payload decode costs before optimization. Re-test
  broad behavior and error domains after candidate or reuse changes.
- [ ] Measure batch size/concurrency, timeout/retry behavior, page size/depth and
  stable tie ordering against generation changes. Record any cursor expiry and
  consistency contract only if supported and tested.
- [ ] Independently test HA node loss, acknowledged-data recovery, storage corruption,
  overload, rollback and cleanup. Single-node restart evidence is insufficient.
  Bound metric labels; keep request/import IDs in sanitized traces, not labels;
  avoid raw queries/catalog bodies and secrets in routine diagnostics.
- [ ] Obtain independent Astra max implementation and readiness reviews. Record
  unresolved findings and unsupported cases. Scale beyond 100k only after measured
  disk/recovery headroom and earlier gates pass. ANN never substitutes for exact truth.
- [ ] Obtain separate external-publication approval. No automated push/tag/release
  step should be enabled until that approval; server API changes require corresponding
  gem revisions and a compatibility table pinned to tested server revisions.

Breaking request/response shapes, defaults, completeness guarantees, preparation
semantics or error behavior require an explicitly documented compatibility break
and migration tests. Server and gem version matching alone is not compatibility
proof. No arbitrary Elasticsearch or Searchkick compatibility is promised.

## Immediate unblock

Provide authorized byte access to the existing DSL handoff (the download host is
blocked by the environment proxy), or place the intact archive in `/workspace/recovery`.
This is a transfer dependency, not a request for permission to publish or merge.
Until then, exact recovery, generated-gem integration, Compose, new benchmarks and
HA validation cannot be honestly marked complete.
