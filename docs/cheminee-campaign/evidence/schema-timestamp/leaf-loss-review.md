# Independent Astra max process-loss review

Recorded from `/root/design_review`'s final review, 2026-10-16. The reviewer made
no source edits and injected no additional failures.

Scoped pass for `schema-fix-leaf-loss-final.json`: 62/62 requests returned HTTP 200
with asserted expected IDs and exact counts. Harness hash matches; independent
live checks confirmed all four fixture splits, expected results, three ready nodes,
and restored PID 121343 running the recorded binary.

4.1856 seconds measures membership convergence. No sampled search outage occurred.

Remaining gaps:

- No request attribution or synchronization proves the killed leaf had an in-flight
  query. Queries were sequential and warmed.
- Saved samples omit actual IDs, shard vectors and error bodies. Stronger independent
  auditing needs those retained values.
- Recovery exceptions now preserve evidence. A transient cluster-check failure still
  aborts restoration verification; subsequent recovery checks should retain their
  own outcome even when the main probe failed.
- The empty query is tag-pruned, not physical empty-candidate verification.
- RSS/HWM and timings are tiny-fixture observations, not capacity or latency estimates.

No blocker to preserving this bounded result. It does not establish storage durability,
replicated deployment HA, cold-cache failover, or recovery of interrupted queries.
