# Planned experiments and delivery gates

Track completion in [issue 5](https://github.com/rdkit-rs/quickwit-cheminee/issues/5).
These are planned changes and validation gates, not test passes or measured gains.
Keep each comparison in its own experiment record, including regressions and
inconclusive outcomes. Existing code and historical evidence remain identifiable.

1. Experiment 005 is complete at the frozen flat-schema revision: configuration-only
   controls and repetitions, passed stored/query audits, instrumented overhead
   comparison, and observed merge/deletion lifecycle. Changing `QW_NUM_CPUS`
   changes multiple pools; it does not isolate chemistry worker count.
2. The [experiment 006 eager baseline](experiments/006-eager-query-costs.md) now
   measures query costs before optimization: candidate selection, dictionary decode,
   distance work, eager dictionary-wide RDKit verification, collection, hydration
   and shared runtime. Distinguish result-cache hits from warm execution and
   restarted processes from cold storage. The [experiment007combined optimization](experiments/007-candidate-first-exact.md)
   completes candidate-first exact scoring with query-local memoization in fallible
   setup, matched repetitions, and bounded held-out C4 probes. Source publication
   remains pending. Decode and RDKit
   errors remain errors. Measure materialized candidates, unfiltered regressions,
   exact counts, threshold boundaries and stable tie order; never truncate work
   silently. A dedicated chemistry pool or model batching remains a separate
   indexing proposal with its own compatibility and concurrency evidence.
3. The [experiment008standalone USearch gate](experiments/008-usearch-feasibility.md)
   passes the bounded external-payload/topology fixture. Production integration,
   ARM64 runtime and remote lifecycle remain unverified. Before freezing the
   vector format, carry its requirements into the adapter:
   externally owned canonical payload, graph-only serialization, destruction of
   builders, fresh-process reopen, shuffled insertion order, concurrent scratch
   leases, deletion/filter masks and mismatched-component rejection. Member keys
   must be final segment DocIds, not insertion slots. Copy results before releasing
   native scratch. ANN failure must not block delivery of exact vector search.
4. Implement generic typed Tantivy segment storage and exact scoring, with clean
   Quickwit adapters. Production packed u1 x 2048/Tanimoto and a small f32 x 768
   storage/exact fixture establish the intended scope; float ANN and Vagus are
   outside it. Persist version, element, dimensions, stride, bit/byte order,
   presence/counts, segment/field identity and integrity. Keep chemistry preparation
   and RDKit/fingerprint profile validation at integration boundaries. Existing
   indexes keep their readers; migration requires explicit reindexing.
5. One canonical persisted vector payload per field/document in an immutable
   segment serves exact and optional ANN. Avoid duplicate stored vectors,
   supplied-vector source copies and embedded hotcache payload bodies. Capturing
   raw SMILES before preparation is compatible with one derived fingerprint.
   Reject conflicting supplied-vector/source-retention configuration. Project
   returned fingerprints from canonical rows. Measure graph edges, temporary
   buffers, WAL, replicas and external caches separately. Fixed rows can exceed
   dictionary storage on duplicate-heavy corpora.
6. Validate storage lifecycle before ANN integration: final DocId remapping,
   sorted/unsorted merge, deletion compaction, restart, packaging, checksummed
   required files before publication, failed upload/publication and GC. Register
   components explicitly. Reader open should read headers, with payload warmup
   explicit; synchronous distance callbacks cannot await remote storage. Account
   for in-flight, resident, pinned and native scratch memory; eviction does not
   free owners still pinned by work.
7. Bind optional graph topology to payload, segment, profile, metric, format and
   build parameters; rebuild after remapping. Navigation may traverse filtered or
   deleted nodes, but results may not include them. Empty eligible masks bypass
   ANN. Define mixed graph/exact-only segment fallback and report effective modes.
   Exact is default; result limit and per-request effort are independent. Effort
   is neither a recall guarantee nor a strict work/deadline bound. An async timeout
   does not cancel native work: retain its ownership and resource accounting until
   completion. ANN totals are unknown/lower bounds without separate exhaustive
   counting. Cache identity includes mode, effort, profile, filters, counts and
   generation. Preserve generation-qualified hit addresses through hydration.
8. Compare unchanged Cheminee, eager Quickwit exact, candidate-first exact,
   typed-vector exact and ANN separately. Use independent exhaustive truth,
   tie-aware recall, held-out queries, selective filters, concurrency, graph
   construction/rebuild and lifecycle costs. Morgan ANN must not make RDKit graph
   predicates incomplete. Lucene's flat-payload/topology separation and
   ordinal/DocId/live-doc/merge contracts are useful prior art; its packed-bit
   Hamming search is not a matched Tanimoto timing control.
9. Scale the single-node local-storage corpus only after measuring disk and
   build/merge headroom. Preserve baselines and evidence. The ceiling is 100 million
   molecules, not a promise that they fit: their 256-byte fingerprints alone occupy
   25.6 GB decimal. Select the largest practical representative sample, keep the
   same records/query set across variants, and publish selection/hash/rationale.
   Do not infer performance equivalence across different machines. Keep ARM64 and
   AWS/S3 compatibility in design; deployment and object-store performance tests
   are deferred beyond the current local benchmark scope.
10. Benchmark nested fast JSON descriptors separately at matched code, document
    flags and resources. Experiment 004 supplies correctness evidence only; its
    performance remains unmeasured.
