# Disposable production-index compatibility probe

`index_restart_compatibility.py` uses a real single-node Quickwit process and its
REST APIs with a local file metastore and split storage. It creates only public
synthetic documents in a fresh absolute work directory. Both executable paths
must be absolute. The baseline creates and force-publishes 384 documents; the
candidate reopens the same index, appends 96 distinct documents, and restarts;
the baseline then reopens the candidate-written index. Every handoff requires
SIGTERM followed by exit status zero, with no prior process exit or forced kill.

From the repository root, with separately built revision-attributed binaries:

```sh
python3 quickwit/scripts/ci/index_restart_compatibility.py \
  --baseline-binary /absolute/baseline/quickwit \
  --candidate-binary /absolute/candidate/quickwit \
  --baseline-revision FULL_40_CHARACTER_BASELINE_COMMIT \
  --candidate-revision FULL_40_CHARACTER_CANDIDATE_COMMIT \
  --work-dir /tmp/quickwit-index-compatibility-fresh \
  --port 18280
```

The REST port, TCP port+1 (gRPC), and UDP port+2 (gossip) must be free on
127.0.0.1. The work directory must not already exist; its parent must exist.
Quickwit configuration and external-service environment overrides are excluded.
`PATH` and `LD_LIBRARY_PATH` are retained for the selected executables' runtime
dependencies. HTTP proxy use and redirects are disabled. Readiness, requests,
publication polling, and shutdown have bounded timeouts. Failed writes are
never retried; failures retain evidence and terminate the owned process.
Startup waits for the configured node and required services in the cluster's
ready set. Reopen also runs a bounded read-only count query before the strict
oracle: only the exact startup error reporting no available searcher nodes is
retried while the local searcher pool catches up. Other errors and partial
results fail immediately. No failed compatibility assertion is retried.

Each document has a unique `u64` fast field `record_id` above 2^53, complete
stored source, and 4 KiB of deterministic payload. The configured 16 KiB
document-store block size makes the stored corpus span many blocks. This does
not establish a cache-eviction count. The independent oracle is the generated
input corpus, never a previous search result. Each checkpoint verifies every
record ID and complete source through 37-hit Elasticsearch-compatible
`search_after` pages with numeric ordering, then checks a terminal empty page.
With `store_source=true`, Quickwit returns the mapped stored fields alongside
an internal `_source` object holding the original document; both copies must
match the input corpus exactly.
It also checks a selective term query and an empty-result query. Every response
must report an exact total, consistent shard counts, no failed shards, no
timeout, and no early termination. Requests explicitly set
`track_total_hits=true` and `allow_partial_search_results=false`.

`result.json` records executable paths and SHA256 hashes, declared revisions,
the script and corpus hashes, environment, process events, and oracle results.
The work directory also retains node/index configurations, original corpus and
ingest bodies, REST request metadata and responses, server build information,
server logs, and the disposable index. Different-binary runs require distinct
full commit IDs that match each server's embedded `build.commit_hash`; callers
must rebuild `quickwit-serve/build.rs` against the actual checkout so its Git
metadata is accurate. The paired CI build helper does this explicitly. Features should be
recorded by the CI build step alongside this evidence.

Identical binary hashes automatically produce `mode: same-binary-rehearsal` and
require identical revision labels. Unknown cached binaries may use an honest
label such as `unknown-oct16-rehearsal`; this validates the script only and is
not evidence for a new revision pair. No index compatibility claim should be
made until `mode: qualification` passes for the actual baseline and candidate.

This is a published-index reopen/restart qualification, not a benchmark,
duplicate-ID upsert contract, lost-acknowledgement/WAL crash-recovery test,
replication/HA test, or production-data migration. `benchmark_trials` is zero.
No external data, production endpoint, or previously created index is accepted.

Run the focused negative-oracle and lifecycle tests without building Rust:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s quickwit/scripts/ci -p test_index_restart_compatibility.py -v
```
