# PR #6 qualification checkpoint — 2026-10-22

This is a test-infrastructure change on top of `b449225b`; it does not change
application dependency versions or clear security findings. No benchmark,
production mutation, merge, deployment or release is part of this checkpoint.

## Decisions and evidence

1. Reconfirmed the existing remote head and review inventory before editing.
   General, chemistry, DataFusion and dependency workflows at `b449225b` passed.
   Those results do not qualify the new test infrastructure or a future head.
2. Preserved the existing source recovery and vendored LRU repairs. The current
   environment is the restored low-capacity workspace, not a fresh runtime host.
   About 663 MiB remained free on `/workspace`, only about 24 MiB above the
   campaign floor. No full local server rebuild was admitted. Small isolated
   parent builds used the separate `/tmp` filesystem and existing cached sources.
3. Compared Chitchat 0.11.1 with registry LRU 0.17.0 against the repaired vendored
   LRU. The normalized Linux host graph matched all 51 packages. Both builds
   completed offline with retained locks. Final Rust sources were checked equal
   to the disposable build copies. Build monitoring observed at most 439.2 MiB
   process-group RSS and 314.9 MiB allocated shared target storage across these
   runs; these are observations, not production capacity targets.
4. The real UDP probe passed baseline/baseline, candidate/candidate,
   baseline/candidate and candidate/baseline. It verified convergence,
   deletes, tombstone collection, receipt and rejection of stale heartbeats,
   same-identity recovery and generation restart. Total elapsed time was
   67.574 seconds; sampled peak aggregate peer RSS was 20,971,520 bytes.
   These are compatibility-test costs, not throughput or query benchmarks.
   The initial attempt was deliberately interrupted because orchestration had
   selected pre-final binaries; its failed receipt is retained, not counted.
5. Added a real HTTP published-index probe and 17 focused passing negative and
   lifecycle tests. Earlier rehearsals exposed missing directory preparation,
   the nested original-source contract, and the gap between HTTP readiness and
   a populated searcher pool. All three were fixed. Startup now checks node
   identity, generation and services; reopen retries only the exact observed
   no-searcher startup error on a read-only query. Oracle failures and writes
   are never retried. Independent Astra max reviews covered design and source.
   The fourth same-binary rehearsal passed all five corpus checkpoints through
   four server lifetimes (384 original and 96 appended documents), including
   complete source, exact counts and ordered pagination. All shutdowns exited
   cleanly. Its cached October 16 binary has unknown revision; this validates
   the harness, not baseline-versus-PR compatibility.
6. The CI pair builder builds the exact pre-repair `c774b166` and PR head with
   descriptor-v1, forces Git build metadata regeneration, restores the head,
   and records binary hashes. The HTTP probe requires embedded revision matches
   for different-binary qualification. CI uploads synthetic HTTP receipts and
   logs, not binaries, indexes or private artifacts. New-head CI is required.
7. The renewed, scoped protobuf source comparison completed without executing
   payloads, changing code, suppressing advisories or downloading sources.
   Its receipt SHA256 is
   `ab3ffc8be1457acfcb7dfbf0fdab4d24cdb5a2b0e18917b6d50821069056ee94`.
   The reviewed 3.7.2 change guards unknown-group depth; 2.27.1 already rejects
   nested StartGroup. The retained prototype addresses a different known-message
   oneof/map depth gap. This comparison is not a security-clearance result.

## Limits and remaining gates

The Chitchat harness uses accelerated timers, three peers, and the production
UDP transport. It does not qualify Quickwit's gRPC catchup, two-hour production
history grace, 500-entry history eviction boundary, or rolling-upgrade HA.
The HTTP probe tests clean shutdown and published split reopen, not interrupted
WAL recovery, ambiguous acknowledgements, replication, corruption or overload.
Tantivy compression-specific eviction and native TensorFlow/generated protobuf
compatibility remain separate gates.

The retained dependency findings are tied to RustSec database
`999ec89d5d3f10f20be14750ec8c2d8b44e0ac9b`: 11 package matches across 10 advisory
IDs, not an October 22 fresh audit. The two LRU defects are technically repaired;
original registry advisory identities remain visible by policy. Full dependency,
native/tooling and backend admission is still open. A new dependency CI result
must identify its own database and findings rather than inherit these totals.

No missing performance benchmark is filled by compatibility elapsed times.
Controlled benchmarks remain blocked by the existing admission requirements.
No fast/cheap/HA or production-index compatibility claim should be promoted from
an unknown cached binary or a same-binary rehearsal.

See [index probe instructions](INDEX_RESTART_COMPATIBILITY.md) and
[Chitchat probe instructions](lru-parent-compatibility/README.md) for commands,
retained locks, expected receipts and exact claim boundaries.

## Fresh dependency CI follow-up

After the first checkpoint commit, `bf8b4afa` dependency CI failed against
RustSec `59ef7abf8ce56ea80fe7eba97ba3835449009fa4`: 14 matches, one new relative
to the PR base (RUSTSEC-2026-0382, rustls-webpki 0.103.15). The follow-up precisely
updates rustls-webpki to 0.103.16 and both webpki-roots/root-certs to 1.0.10,
covering RUSTSEC-2026-0381/0382/0383. All other locked dependency edges are
unchanged. Explicit transport and TLS tests are added to CI. Fresh audit and
runtime qualification are still required; the older eleven-match observation
must not be presented as a fresh scan. See the dependency preflight for the
trust-store changes and remaining gates.
