# Independent design gate review

Reviewer: `gpt-6-astra`, reasoning effort `max`, task `/root/design_review`.
Date: 2026-10-16. Scope: public PR3 `6bf1e29`; unpublished DSL unavailable.
No runtime tests or implementation edits were performed by the reviewer.

Verdict: **release blocked**. Priorities from the independent review:

1. P0: Staging-generation promotion must survive uncertain writes. Validate counts
   and unique IDs; prove compare-and-swap activation and rollback. Timeout means
   unknown outcome. Test late append, lost acknowledgement, restart and concurrent
   promotion. Existing WAL does not deduplicate document IDs.
2. P0: Prove completeness for every search path, including failures alongside
   successful/empty results. ES `eq` and `timed_out:false` do not prove completeness;
   strict partial-result rejection is unsupported by scroll.
3. P0: Pin chemistry preparation, RDKit, fingerprints and chirality policy. Test
   stereo, salts, tautomers, malformed candidates and Boolean error domains against
   independent exhaustive truth. Baseline chirality defaults false.
4. P0: Export the combined schema, deliberately allowlist operations, repair NDJSON
   annotations and expose detailed rejection counts. Missing counts block promotion.
5. P0: Separate offer and structure identity; prefer one offer per document. Prove
   correlation, record-ID uniqueness and large integer round trips.
6. P1: Verify pinned reproducible generation, distinct namespace, installation
   outside source, and real create/ingest/search/cleanup HTTP tests.
7. P1: Separate local Compose convenience from measured crash/HA recovery. Record
   bounded-cardinality diagnostics, reject/unknown counts, visibility lag and
   rollback outcomes without catalog bodies or secrets.

These findings are incorporated into the campaign checklist. They do not constitute
implementation approval, successful recovery or production readiness.
