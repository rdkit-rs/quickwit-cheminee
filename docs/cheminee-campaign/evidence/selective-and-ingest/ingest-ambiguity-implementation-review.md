# Ingest acknowledgement correction: implementation review

Independent Astra review, 2026-10-16, of commit `8009925c6b9757edc77ef8e6111309503028e7c5` under `/workspace/quickwit-cheminee-pr3-inspection`. The hashes below identify the reviewed content. The test runs preceded one final diagnostic-only addition in the ingester; that addition was inspected and checked by Clippy, as distinguished below. This review supersedes the blocking findings in `/workspace/recovery/ingest-ambiguity-review.md` for the bounded server correction only.

**Verdict: no remaining blocking defect found in this correction.** The source and tests support the scoped claim that the patched router does not automatically replay these ambiguous persistence outcomes. The change is suitable for further catalog workflow work. This is not approval to promote a catalog generation, release the campaign, or claim exactly-once ingestion, crash durability, or HA.

The implementation addresses the earlier replay paths:

- `quickwit/quickwit-ingest/src/ingest_v2/workbench.rs:436` uses an explicit retry allowlist. Local no-route, per-subrequest WalFull, and known pre-dispatch overload rejection remain eligible. Internal, transport Unavailable, timeout, Unspecified, remote NoShardsAvailable, and NodeUnavailable are terminal.
- The conservative remote-NoShardsAvailable decision is justified: older/current replica producers can use that reason after an append I/O error. Making it terminal avoids a wire-schema change or a claim that every replica producer now distinguishes phases. `workbench.rs:401` also maps these remote ambiguous reasons to public Internal; local no-route retains its distinct rejection classification.
- `workbench.rs:227` validates the returned leader and unique expected IDs before recording successes. Contradictory, duplicate, or foreign acknowledgements terminate the submitted RPC's IDs without inflating success counters. Missing IDs become terminal even after an earlier WalFull rejection, while coherent acknowledged siblings remain intact. The router invokes this check at `router.rs:288` before applying outcomes or routing updates.
- `quickwit/quickwit-ingest/src/ingest_v2/ingester.rs:711` records already-reported replica failures, then fills only unresolved pending IDs with explicit NodeUnavailable. This closes the producer's omitted-response path without replacing explicit pre-write rejections or fabricating a success.
- The existing shared persist deadline remains in place. Timeout still does not cancel an already dispatched remote append; the correction stops replay rather than claiming cancellation.

**Evidence examined and independently exercised**

| Evidence | Result and scope |
| --- | --- |
| `/workspace/recovery/ingest-ambiguity-suite2.log` | 157 ingest-v2 tests passed, including the new real-follower lost-ACK fixture. This run preceded the final call-counter/Unspecified additions. |
| `/workspace/recovery/ingest-ambiguity-final-tests.log` | Recompiled test target and passed 157 tests, zero failed, 24 filtered out, after those additions. |
| `/workspace/recovery/ingest-ambiguity-independent-tests.log` | Reviewer independently reran the current compiled executable: 157 passed, zero failed, 24 filtered out, in 0.85 seconds. This was an independent execution, not an independent rebuild. |
| `/workspace/recovery/relevance-ingest-final-clippy.log` | Contains successful completion of the combined check including quickwit-ingest; no `warning:` or `error:` entries. The reviewer inspected this recorded run rather than rerunning Clippy. |
| `/workspace/recovery/ingest-final-log-clippy.log` | Successful completion after the final bounded leader/subrequest warning was added. This final change adds diagnostics only; the independently executed test binary predates that warning. |
| Reviewer `git diff --check` on the four ingestion files | Exit 0, no whitespace errors. |

Independent reproduction command:

```sh
docker exec -w /workspace/quickwit-cheminee-pr3-inspection/quickwit \
  cheminee-native-builder \
  ./target/debug/deps/quickwit_ingest-e0fe7800b27bc12b ingest_v2::
```

The evidence has meaningful coverage rather than only checking enum assignments:

- `router_timeout_tests.rs:216` injects Internal, transport Unavailable, NodeUnavailable, remote NoShardsAvailable, Unspecified, and missing acknowledgement after recording the append. Each case asserts terminal Internal, no success, exactly one persist call, and exactly one occurrence of each submitted DocUid. The deadline fixture separately verifies a detached append completing after the router's timeout. These are router-policy tests with an append ledger, not real storage or network tests.
- `ingester.rs:2401`, `lost_replica_ack_preserves_real_wal_and_reports_unknown_outcome`, uses a real leader and follower in process. Its stream wrapper replaces the actual follower's ReplicateResponse with a transport error after the response is produced; initialization acknowledgements pass through. The assertions prove the follower WAL contains exactly the document plus commit marker, the leader WAL is empty, and the leader returns one explicit NodeUnavailable for the submitted ID. This establishes the post-append producer path; it is not a distributed TCP-failure test.
- Workbench tests cover omission after a prior retryable WalFull, duplicate success, success/failure conflict, foreign ID, wrong leader, and preservation of an independently acknowledged success. The positive router retry test now uses a proven pre-dispatch CircuitBreaker rejection.

**Nonblocking follow-ups and operational limits**

The reconciliation diagnostics now include bounded submitted IDs, leader identity, and `outcome_unknown=true`, without document bodies. The final diagnostic addition at `ingester.rs:721` also records leader and subrequest identity when unresolved replica outcomes are emitted. This closes the observability follow-up identified during review without changing retry behavior.

The public SDK README now warns about failed transport and missing/inconsistent acknowledgements after dispatch. The packaged README template still mentions only timeout ambiguity; carry the broader wording into the next artifact generation. Generic HTTP 500 is not itself an idempotency contract, and external clients/proxies must not blindly retry an uncertain batch.

The compatibility claim is limited: patched routers conservatively handle ambiguous reasons from older ingesters. Traffic handled by an unpatched router still has the old retry behavior. The tests do not prove mixed-router deployment safety.

WAL DocUid deduplication, request-level idempotency, replica recovery after a lost acknowledgement, restart/crash durability, publication guarantees, and catalog activation/CAS were not implemented or established here. The real lost-ACK test intentionally leaves a stored follower write with an unknown client outcome. A catalog importer must quarantine that staging generation, avoid replay into it, and use a new unique generation from the complete frozen snapshot. These remain distinct from approval of this bounded correction.

Reviewed SHA-256 values:

```text
3645355c2f70aac5a8930c7c76b017eaa23458ea363309ae12cad769fbd71806  quickwit/quickwit-ingest/src/ingest_v2/ingester.rs
8d21baafc8dca38ce80a0951a27c18c740a432a30137c1208d59598b7e8cd509  quickwit/quickwit-ingest/src/ingest_v2/router.rs
8df046b5a02189290eef9ee2d0a0c1f5855388318009ac4704001c0a938290ef  quickwit/quickwit-ingest/src/ingest_v2/router_timeout_tests.rs
b50a01cc2912d3fbfbd2aa0c0f52947e1474697fed8651887af26f193c40d7d5  quickwit/quickwit-ingest/src/ingest_v2/workbench.rs
9ea1ddcabec2ba84a8071ff67d51fcb8da1791174c30b10305ad7763bbe290ce  quickwit/target/debug/deps/quickwit_ingest-e0fe7800b27bc12b
b5543db3815ef7c919018c59c9b77f295d82ec95ca3780eba9577786db2e5fd3  /workspace/recovery/ingest-ambiguity-final-tests.log
181f8cd42cc5ef2d8262db09c2d10c614efe4f6e60e6efec475c1deae1a4503a  /workspace/recovery/ingest-ambiguity-independent-tests.log
82af75611f7c553129b22a63b6b91fd8bd1dad91b2f620b3735a3d9118dc1b1c  /workspace/recovery/relevance-ingest-final-clippy.log
78f62d91e98e9b6c79ea963d7e8360d671d36f729b5875aeea6f87bb5099240a  /workspace/recovery/ingest-final-log-clippy.log
```

No repository files were edited by this reviewer. Only this review and the independent test log were written outside the repository.

