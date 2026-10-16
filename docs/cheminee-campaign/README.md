# Cheminee importer campaign — recovered source and SDK preparation

Status: **no release gate has passed in this session**. This is a reviewable
preparation branch based on public PR3 `6bf1e29cdbf03409287b2f7d0e59a4c19534d8fa`.
It is separate from the now-recovered composable-query branch. The initial preparation snapshot
was followed by a [generated PR3 Ruby candidate](../../sdk/ruby/README.md), schema
fixes and focused tests. No package was published, deployment performed, or
production data touched. The historical decision entries below describe recovery
and the initial audit; current SDK validation is recorded separately.

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

9. Parent confirmed recovery archive access in its separate environment and supplied
   SHA-256 `d5ee440b440fb50a31554dc7280472a8e38464dcaa34fe4a0472e8ce56cb3f50`.
   That path is not shared with this environment. Requested a private text-readable
   transfer of the 27,904-byte Git bundle; exact DSL bytes are still unavailable here.
10. Prepared the actual PR3 generated SDK in `sdk/ruby`, with a pinned 7.11.0 JAR,
    locked transport/test dependencies, deterministic schema projection, template
    hashes and a read-only/manual artifact workflow. Inspected the old shipping
    workflow before selecting the same generated Faraday/DefaultApi pattern.
11. Independent Astra max implementation review found two concrete decoding defects:
    flattened mapping options were dropped and the fast-field schema described an
    internal enum instead of its wire JSON. Corrected both canonical server schemas
    and pinned generator templates. Added nested mapping and dynamic-index coverage;
    no runtime facade or monkeypatch. Also reject unsupported union-parent constraints,
    make unknown discriminators fail explicitly, and preserve boolean false in unions.
12. Focused verification now passes: three schema tests, seven projection tests,
    twelve installed-gem HTTP/model tests (153 assertions), and live non-native
    dynamic-index create/import/search/delete smoke. Six non-native chemistry and
    thirteen ingest route tests passed earlier in this same preparation session.
    Generation repeats byte-for-byte. These are scoped contract results, not native
    chemistry, DSL, refresh safety, performance, durability or HA release approval.

13. Recovery unblocked through private Library text transfer
    `libfile_cc9c0af0f2348191955b463111bbb550`. Decoded bundle is 27,904 bytes,
    SHA-256 `3143466d909bf0be52901afbae0497a576679e5e64592090a96c6bff22733bbe`.
    `git bundle verify` passed against the exact PR3 prerequisite. Fetched the three
    unpublished commits and created `/workspace/quickwit-cheminee-query`, clean at
    `276bd1ab7455d0141bd8d9427d00acb1bb7ad845`; ancestry from PR3 verified. Full
    archive integrity was reported by the parent, not independently checked here.
    The PR3 gem remains a separate candidate pending DSL integration/revalidation.

14. Integrated source on a separate local campaign branch, retaining the recovered
    branch unchanged. Added the existing composable POST search route to canonical
    OpenAPI and generated an explicitly unchecked JSON transport. Independent Astra
    max review approved a narrow `ExactSearch` composition adapter: strict failures,
    exact counts via size-zero search, concrete generation and numeric tie sort.
15. Closed concrete review gaps with tests: positive totals with zero searched splits,
    floating stored IDs, non-JSON inputs and malformed responses are rejected. Bounded
    reason codes, HTTP status and sanitized request IDs support diagnosis without
    document logging. Server conversion rejects top-level errors its ES-shaped
    response cannot represent, even in partial mode; native regression passed.
16. Native build prerequisites are now installed on pinned Ubuntu amd64 with verified
    RDKit packages. Disk exhaustion interrupted the first build. Preserved binaries,
    source and evidence, removed only this task's obsolete builder/intermediates,
    and resumed with an automatic 1 GiB disk reserve. This is build headroom, not
    measured production memory or durability. No scale benchmark was attempted.
17. Native core/query/mapper suites passed 185 tests. The broader document-mapper
    run exposed an old cross-field ordering assumption (228 passed, one failed).
    Independent review confirmed object-key traversal has no cross-field order
    promise. Changed only that test to assert exact contents for both input orders;
    kept array-order checks. Full native rerun is separate evidence.
18. Strong sibling-error-domain semantics remain an explicit gate gap: existing
    Boolean simplification and split pruning can avoid chemistry execution. The
    client does not rewrite queries to hide this issue, and documentation makes no
    global malformed-data validation claim. Cursor APIs remain unexposed pending
    distributed enumeration and merge-stability tests.

## Confirmed source hazards

| Contract | PR3 finding | Required evidence before release |
|---|---|---|
| NDJSON | Base annotation was wrong; corrected on the preparation branch and wire-tested | Generated Faraday sends exact newline-separated bytes; no JSON wrapping; response counts and rejections survive decoding |
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

- [x] Recover exact Git state through the authorized private bundle transfer; verify
  checksum, bundle, final SHA, clean status and ancestry from PR3. Preserve original
  worktree and bundle before integration. Full archive remains parent-verified only.
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

## Next integration gate

Exact source recovery is complete. Integrate the reviewed SDK preparation into a
new branch while retaining the recovered branch and bundle unchanged. Revalidate
the generated contract against composable queries, completeness and native chemistry.
The original benchmark corpus/index archive remains unavailable; performance, Compose,
catalog safety and HA require independent evidence and remain pending.
