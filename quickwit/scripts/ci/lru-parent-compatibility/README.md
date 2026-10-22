# Chitchat LRU parent compatibility gate

This isolated harness compares Chitchat **0.11.1** with the original registry
LRU **0.17.0** against the same parent with the candidate's vendored LRU 0.17.0.
The application baseline is `c774b166`; the LRU repair was introduced at
`b449225b`. CI tests the checked-out PR head with that repair.
The harness itself is new test code and is compiled identically for both sides.
It does not change the application's manifests or lock.

All peer communication uses Chitchat's production `UdpSocket`, including its
serializer, compression and decoder. A passive wrapper counts messages and
records received SYN digests. This is the same socket wrapped by Quickwit's
`CountingUdpTransport`. JSON stdin only controls a peer's own key/value state,
requests snapshots, or requests a normal gossip handshake. No remote node state
is injected with an internal API or an in-memory transport.

## Build admission and reproducibility

Copy `Cargo.toml`, `peer.rs` and `observed_udp.rs` into two separate disposable
directories. Do not build in this source directory. Copy the retained
`baseline.lock` or `candidate.lock` to the corresponding directory as `Cargo.lock`.
These locks were resolved from `c774b166:quickwit/Cargo.lock`; the recorded Linux
host graph matched across all 51 packages after normalizing only source paths.
In the **candidate copy only**, append:

```toml
[patch.crates-io]
lru = { path = "/absolute/path/to/candidate/quickwit/vendor/lru-0.17.0" }
```

Use the existing cached Cargo registry/git sources and an isolated Cargo home.
Resolve offline once with `cargo metadata --offline --format-version 1` for each
copied manifest; restrict metadata to the recorded host target when unused target
packages are absent from the cache. Retain the resolved locks and metadata. Verify
the graph has Chitchat 0.11.1 and LRU 0.17.0, and compare every resolved package,
dependency and feature after normalizing only the harness root paths and the LRU
source identity. Compare shared registry versions/checksums against the baseline
application lock as well. A same-parent test with unrelated dependency updates is
not this gate. Record the Cargo/rustc versions, target, source hashes, original LRU
archive checksum, vendor provenance validation and exact commands.

Build serially with `cargo build --offline --locked`, one build job, dev debug
information disabled, and incremental compilation disabled. A shared disposable
target directory can reuse common dependencies. Copy and hash the baseline
executable before compiling the candidate, because both binaries have the same
name. Never substitute the old cached Quickwit executable for either build.

The current workspace has a 671,088,640-byte free-space floor and about 24 MB of
headroom. Put build targets, runtime evidence and copies on the separate `/tmp`
filesystem. The source change is small; a full application build is not admitted
by this gate. First check build growth at 500 MiB. Stop a build at 1.5 GiB aggregate
growth, 2 GiB aggregate process RSS, either filesystem floor, or its explicit time
limit. These are admission caps, not measured requirements or a capacity promise.
Preserve failed logs and update estimates from the first admitted run.

## Execute

After both exact builds pass provenance/graph validation:

```sh
python3 quickwit/scripts/ci/lru-parent-compatibility/run_udp.py \
  --baseline /tmp/cheminee-oct22/bin/chitchat-baseline \
  --candidate /tmp/cheminee-oct22/bin/chitchat-candidate \
  --evidence /tmp/cheminee-oct22/chitchat-udp-evidence \
  --max-seconds 180
```

The evidence directory must not already exist. The Linux runner uses only Python
standard-library dependencies. It starts at most three loopback peers at once,
samples aggregate RSS, preserves 640 MiB free on `/workspace` and 512 MiB on the
evidence filesystem, caps evidence at 32 MiB, and limits each control read/write
to five seconds. All started children, including failed startup attempts, have a
bounded shutdown path. A port race fails the run. Every assertion is an explicit
exception check, so optimized Python cannot disable verification.

Each of baseline/baseline, candidate/candidate, baseline/candidate and
candidate/baseline performs:

1. Exact convergence of deterministic roughly 100 KiB key/value state per node,
   including Unicode, overwrites, deletion and tombstone garbage collection.
2. Pause subject B with SIGSTOP while observers A and C still agree on B's live
   heartbeat; pause C, then observe B become dead and B/C state disappear at A.
3. Delete an A key while B/C are paused and wait for that tombstone's collection.
4. Resume C and require A to receive a new genuine UDP SYN advertising B's frozen
   heartbeat. B must remain absent at A while C rejoins.
5. Resume B and require same-identity recovery plus complete exact contents at
   every node, including preservation of the deletion made while peers were away.
   This exercises the parent's garbage-collected-history removal (`LruCache::pop`).
6. Shut down B, restart it at the same address with generation 2, require complete
   new-generation convergence, and wait for generation 1 to be garbage collected.

`report.json` records hashes, configuration scope, scenario outcomes, time, sampled
RSS and disk minima. Per-scenario `events.jsonl` records the witnessed transitions,
state-content hashes, and received digests. Stderr is retained separately.

## Claims deliberately left open

The harness uses 100 ms gossip, four-second dead-node grace and two-second key
grace. Quickwit hardcodes **two hours** of dead-node grace in
`quickwit-cluster/src/lib.rs`. The harness also has no Quickwit readiness predicate
or gRPC catchup callback. Therefore it qualifies the pinned Chitchat parent and
real UDP protocol under the stated test timings, not full Quickwit rolling
upgrade, production timer behavior, gRPC state transfer, or HA readiness.

The three-node case does not fill Chitchat's 500-entry history cache. Upstream
parent tests and a separate bounded eviction fixture must cover that boundary.
It does not execute vulnerable panic/aliasing negative controls.

Tantivy remains a separate parent gate: use the pinned `057458b` revision with
Quickwit's actual features (`quickwit`, `mmap`, `lz4-compression`,
`zstd-compression`, `columnar-zstd-compression`). Run `test_store_lru_cache` plus
the compression variants, then a full Quickwit REST-created disposable baseline
index through candidate reopen, append, restart and baseline readback. Tantivy's
format-6/7 fixtures that exclude the `quickwit` feature cannot replace this.

Observed convergence time and RSS are bounded compatibility measurements, not a
production throughput/latency benchmark. No application compatibility result,
dependency clearance, merge, deployment or publication follows from this harness
alone.
