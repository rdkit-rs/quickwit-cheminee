# Cheminee importer campaign — recovered source and SDK preparation

> Continuation decision: relevance-based error semantics supersede the earlier
> global verification proposal. Valid chemistry AND match-none can return exact
> zero; eagerly reject invalid query inputs, and fail unresolved stored-data errors
> only where they can affect membership/count/rank. The reproduced timestamp
> candidate broadening is fixed in the bounded cases below; timestamp-sort pruning
> remains an unvalidated concern. See `ERROR_DOMAIN_REVIEW.md` before coding.


Status: **no full release gate has passed**. The recovered composable DSL and generated
Ruby candidate are integrated on the local campaign branch. Targeted native HTTP,
installed-gem, query and ingestion regressions pass as recorded below. Catalog
promotion, old-schema migration, broader error relevance, measured Compose/Elasticsearch
coexistence and HA remain open. No publication, deployment, or production write occurred.
Historical entries below retain the recovery sequence; they are not current blockers.

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

19. Native rerun passed all 229 document-mapper and 178 server tests; native Clippy
    passed with warnings denied. Distributed native HTTP harness passed 16 cases.
    Restarted its persisted tiny indexes and tested the installed gem: complete
    offset enumeration with score ties, strict counts and failed-leaf rejection.
    This is graceful restart evidence on one host, not crash recovery or HA.
20. Reproduced the sibling-domain gap over native HTTP: unbounded malformed
    fingerprint query fails 500; adding sibling `match_none` returns exact zero
    with HTTP 200. Explicit operator candidates excluding the malformed record
    return exact two. Strong sibling-error-domain gate is known failing.

21. A second native probe confirms candidate-domain broadening: a real timestamp
    field with healthy 2020 and malformed 2021 documents in one split still fails
    when explicit candidates restrict verification to 2020. Leaf timestamp rewriting
    moves this filter outside the operator. Independent Astra max review recommends
    a coordinated verification-obligation design, not an isolated simplifier patch;
    see `ERROR_DOMAIN_REVIEW.md`. Both correctness failures remain open.

22. Continuation adopts relevance-based errors, superseding decisions 18/20 and the
    global-obligation portion of 21. Valid chemistry AND match-none can return exact
    zero without scanning excluded corruption. Query inputs must validate eagerly;
    unresolved errors affecting membership/count/rank must prevent completeness
    claims. Timestamp candidate broadening remains a defect. Astra max reviewers
    are reviewing targeted fixes and the revised Boolean regression matrix.

23. Native continuation fixes preserve invalid operands until eager validation,
    then collapse impossible queries before stored reads; timestamp rewrites now
    preserve explicit chemistry candidates. Native query162 and timestamp9 tests
    passed; the independent109-request probe changed from23 failing cases to zero
    failed assertions. Timestamp candidates now return exact1 instead of500, while
    unbounded corruption still fails500. Installed Ruby native smoke and Clippy
    passed. Remaining relevance cases and operational gates stay open. See
    `evidence/relevance-continuation/validation.json`.

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
to the public base. The recovered DSL has bounded fresh reviews recorded below;
those reviews do not close every release gate.

## Gate order and release checklist

Unchecked items are whole release gates; scoped successes and remaining limits are
recorded in the continuation evidence, not implied absent by an unchecked box.

- [x] Recover exact Git state through the authorized private bundle transfer; verify
  checksum, bundle, final SHA, clean status and ancestry from PR3. Preserve original
  worktree and bundle before integration. Full archive remains parent-verified only.
- [ ] Run outstanding validation on recovered code, recording commands, feature
  flags and failures. Historical 174 aggregate tests and 16 HTTP cases are supplied
  checkpoint evidence with overlap, not fresh totals. Fresh scoped suites are
  recorded below; full workspace all-features Clippy was attempted and stopped
  for disk headroom, so workspace validation remains incomplete.
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

Exact source recovery and local SDK integration are complete; the recovered branch
and bundle remain unchanged. The targeted timestamp and eager-validation fixes passed; finish the remaining relevance-based regressions
before calling the full contract gate passed. Native HTTP and installed Ruby smoke
evidence is available under `evidence/sdk-dsl`; it is scoped functional validation.
The original benchmark corpus/index archive remains unavailable; performance, Compose,
catalog safety and HA require independent evidence and remain pending.

## Continuation: selective verification and ambiguous writes (2026-10-16)

The bounded planner copies only necessary term/range/presence predicates from a
Boolean node's must/filter clauses into chemistry candidates. It retains the original
clauses and wraps existing candidates to preserve implicit should requirements.
Input validation precedes narrowing. Planning expansion has byte/copy limits and
reserves the serialization depth required by downstream timestamp/cache wrappers.
These are safety limits, not measured workload recommendations.

Empty/deleted-only scorer candidates no longer require chemistry columns, while
matcher setup and candidate errors remain eager. This is scorer-level coverage:
old physical schemas can still fail during leaf compilation or warmup before the
scorer; migration support is not established.

Timestamp pruning now conservatively preserves subsecond matches, including legacy
negative metadata. Precise pre-epoch/extreme dates survive leaf rewriting as RFC3339
when numeric unit inference cannot represent them exactly. The first HTTP attempt
exposed two pre-epoch failures; the corrected rerun passed all 68 cases. The existing
109-request probe also passed 105 assertions with 4 observation-only OR cases. These
counts overlap test domains and must not be summed into a unique-case claim.

Source review found automatic ingest replay after Internal/Unavailable, ambiguous
remote no-shards failures and omitted acknowledgements. The correction retries only
proven pre-write rejections, reconciles returned IDs before recording successes,
and explicitly reports unresolved replication acknowledgements. Remote no-shards is
conservatively terminal for compatibility with older peers; local no-route remains
retryable. Unknown outcomes still quarantine a staging generation. They cannot be
replayed blindly or promoted merely because an observed count currently matches.

Independent Astra max reviews and runtime evidence are under
[evidence/selective-and-ingest](evidence/selective-and-ingest/). The real follower-WAL
lost-ACK test complements router ledger tests; it is not durability/HA or exactly-once
proof. Broader count-only OR relevance, old-schema warmup, and timestamp-sort pruning
remain open. Record-ID/score ordering is the tested SDK path. Original 100k corpus
and indexes remain unavailable; historical benchmark claims are unchanged.

24. Final `.pre.contract1` candidate regenerated twice identically from source
    `8009925c`, built and installed. Exact rebuilt runtime passed 68 selective HTTP
    cases, 105 assertions/109 relevance requests (4 observations), native installed
    client smoke and the 21-check catalog journal experiment. The live schema is
    semantically equal to the retained export. [Attributed final evidence](evidence/selective-and-ingest/README.md)
    includes hashes, limitations and independent Astra max reviews. The importer
    example is bounded to 10,000 offers and cooperating writers on one host; it
    establishes neither HA nor production catalog promotion safety.

25. Package a local native runtime (305,602,041 image bytes) and exercise
    `docker-compose.yml.example` with a persistent volume. The discriminatory
    1,000-offer fixture checks chiral identity against same-supplier nonmatches and
    opposite enantiomers, including chirality-disabled and unfiltered controls,
    before and after graceful restart. Node readiness precedes searcher membership:
    record bounded read startup retries separately, never replay writes. Capture both
    process RSS and cgroup accounting because shared-file charging makes them differ
    materially. The 768 MiB ceiling and 32 MiB per-index test heap are experimental
    bounds; the server's 2 GB default indexing heap is unsuitable for this ceiling.
    [Resource and correctness evidence](evidence/local-compose/README.md) is not a
    benchmark or HA proof. With under 1 GiB workspace free space, Elasticsearch
    coexistence and full workspace CI remain blocked by headroom. No scale run starts.

26. Separate current chemistry declarations from physical split resolution. Keep
    candidate field IDs physical, validate current inputs eagerly, and defer invalid
    old chemistry columns until a live candidate needs verification. Pure schema
    warmup filtering does not catch I/O errors. The expanded mapper matrix and39
    native HTTP checks pass; independent Astra max review approves this bounded
    path. Compatible-column corruption and arbitrary migration remain open.
27. Match timestamp cutoff quantization to the metadata writer and retain unknown
    bounds conservatively. A cold baseline returned wrong top IDs with correct exact
    counts; the replacement passes18 deterministic timestamp HTTP checks and five
    units, including offsets, tie ordering, unknown bounds and count obligations.
    Separate commits and [retained evidence](evidence/schema-timestamp/README.md)
    make both fixes reviewable. Earlier open-gate statements above describe their
    historical checkpoints; the [current ledger](REMAINING_GATES.md) governs status.
28. Continue full workspace validation under a 640 MiB disk guard. Retain the default
    TensorFlow download HTTP 403, existing-TensorFlow 2.15.1 disk stop, and subsequent
    krb5-src const-qualifier compiler failures (including explicit C17). Scoped
    native Clippy passes; full workspace CI does not. Compress and verify the
    retired runtime context before removing its uncompressed copy; preserve
    Library v4 and all source/evidence. No image or corpus reconstruction is implied.
29. Exercise one synthetic searcher SIGKILL and rejoin with broad/selective/empty/
    novel exact graph oracles. Final 62 sampled requests all succeed; 4.186 seconds
    describes membership convergence, not downtime. Shared local storage, warmed
    sequential requests and 16 repeated molecules do not establish deployment HA
    or performance guidance. Independent Astra max review accepts this scope only.
30. Prepare an explicitly unexecuted Elasticsearch override and observer with bounded
    Docker calls, phase/freshness checks, frozen sampling and final container checks.
    Python/configuration checks and independent preparation review pass. Actual
    coexistence remains open. Preserve the next count-only OR design without
    presenting unimplemented relevance behavior as supported.

31. Disk/process audit identifies the existing checksum-verified Kerberos CI
    wrapper that the raw Cargo retries missed. Correct the diagnosis: those
    failures were avoidable process error; the proper wrapped check remains
    unrun. No new large build was started for the audit.
    [Diagnostic packet](DISK_PROCESS_DIAGNOSTIC.md) distinguishes actual headroom,
    transient growth, overlay reclamation and checkpoint cost from estimates.
    Backend resume errors have no established causal link to disk.

32. Apply the process audit before another heavy phase: offline dependency preflight,
    checksum-verified cached Kerberos input, exclusive cooperating-job lock, durable
    launch state, survivor inspection and separate admission/emergency thresholds.
    The workspace phase is refused at current headroom. Tiny-process tests and
    independent Astra max reviews validate this bounded guard, not build capacity.
    [Runbook](../../quickwit/scripts/ci/CAMPAIGN_RUNBOOK.md) records reuse, cleanup
    measurement and retry rules. No new heavy build or Docker change was performed.

33. Integrate the independently reviewed Ruby and Compose handoffs, preserving
    their source commits and scopes. Verify text-transfer file hashes and exact Git
    prerequisites; pass combined lightweight checks and bounded retained-server Ruby
    smoke. V6 checkpoint retains the integrated source without claiming live Compose
    resource measurements or a pinned Ruby wire-suite pass.
34. Resume catalog recovery locally after the separate worker never dispatched.
    Add real-journal/process tests with a shared fake-peer acceptance ledger: 16
    tests/86 assertions cover ambiguous writes, interrupted promotion/rollback and
    cooperating publisher contention. Production importer code is unchanged.
    Existing runtime inspection confirms JSON extension directory and SONAME mismatch;
    preserve the pinned-suite blocker rather than force ABI aliases or change the lock.

35. Withdraw the original worker pinned-JSON attribution: activated spec3.1.0
    masked loaded JSON2.7.2. Retain separately the corrected JSON3.1.0 worker
    proof (20/392, seed10109), verify matching local interpreter/library hashes,
    and harden wire acceptance with actual JSON version and loaded-file provenance.
    Compatible extension bytes remain missing locally; no ABI aliases or installs.

36. Verify the small worker JSON artifact and restore it into an isolated gem root.
    ActualJSON3.1.0 local wire20/392, journal16/86 and native smoke now pass without
    builds/containers/aliases. Fix the guard's real-run false positive on Faraday
    middleware with relative load-path identification and a regression test. Keep
    full-workspace admission blocked by the measured4.32GiB headroom shortfall.
