# Persist timeouts during native chemistry ingestion

Native molecule validation can take longer than the former six-second persist-attempt timeout. The router previously abandoned its response future and submitted the same document batch again, up to five times. A remote or protected server task can still append after its caller stops waiting. Document UIDs are carried through validation but do not provide WAL deduplication. A slow single-node request could therefore append the same IDs five times and still return a timeout.

The router now gives its persistence phase one shared 30-second budget, equal to the previous five six-second attempts. A slow persist operation retains its original response future until that deadline. Definitive transient rejections still permit retries, bounded by both five attempts and the shared deadline. Expiration marks only pending subrequests as timed out; acknowledged subrequests remain successful. An explicit timeout returned by an ingester is also terminal for that subrequest, because its append outcome is unknown.

The persistence deadline applies to `auto`, `wait_for`, and `force` commit modes. Publication tracking for `wait_for` and `force` remains outside that deadline, as before. The default outer timeout for `auto` remains 35 seconds. This change does not disable chemistry validation, change batch contents, bypass publication acknowledgement, or add durable document-ID deduplication.

A timeout remains an uncertain outcome: a late append can become searchable after the error. Do not interpret it as proof that no documents were written. A client resubmission creates another ingestion request and may duplicate documents; this change is not an exactly-once guarantee, nor does it change existing transport-error retry behavior. Callers requiring retry-safe application IDs still need an explicit idempotency contract.

Deterministic paused-clock regression tests in `quickwit-ingest/src/ingest_v2/router_timeout_tests.rs` model a server task that survives caller cancellation. They check delayed acknowledgement, late append after deadline, and explicit lost-acknowledgement timeout, including exact document UID sequence and uniqueness. The existing router retry test covers a definitive `NoShardsAvailable` rejection followed by success.

Run the ingestion crate tests with:

```sh
cd quickwit
cargo test --locked -p quickwit-ingest --lib
```
