# Bounded local resource observations

This harness admits an **already-running** verified local Cheminee container and
optionally an already-running Elasticsearch neighbor before invoking the existing
1,000-offer synthetic native smoke. It never builds, pulls or starts containers.
Execution creates/deletes its own disposable index and gracefully restarts the
primary container; obtain the sole runtime owner's admission before `--execute`.
The historical Compose smoke used unoptimized source
`8009925c6b9757edc77ef8e6111309503028e7c5`; it is not evidence for the latest harness.
No live run of this revision has occurred. Lightweight tests are not runtime evidence.

## Prerequisites

Use Python 3, Docker CLI/Compose v2 and cgroup v2. Run directly in the Docker
host's network and filesystem namespaces. A host socket mounted into a separate
container is unsupported: its local loopback may refer to another host namespace. The primary container must publish
only `127.0.0.1:7280:7280`, have a working healthcheck and bounded CPU/memory. Both
containers must have independently verified compatible runtime/image provenance.
Both must use restart policy `no` for the entire measurement and memory-plus-swap
limits equal to memory limits. The admission and smoke records link container IDs,
RestartCount and StartedAt from admission to completion. Only the primary explicit
restart may change StartedAt; any automatic restart or observed-container
incarnation change fails the run. This closes the gap where recovered OOM state
and reset cgroup counters could look healthy. Concurrent workload and PID-limit
validation remain unrun.
Supply full local image IDs, not tags. The provenance file is JSON with `image_id`, `source_commit`
matching the full 40-hex revision supplied in `--source-commit` exactly and a 64-hex `binary_sha256`.
The supplied provenance SHA verifies the retained evidence file bytes; it does not independently establish source-to-binary
provenance or compatibility. The owner must establish those before admission.
V5 excludes the native runtime. Do not rebuild Rust to run this harness.

Measure the Docker data filesystem (including VFS writable-root duplication), data
volume filesystem if different, available CPU/memory after existing workloads,
expected import growth and recovery reserve first. `--storage-path` must identify
an existing path on the admitted Docker data filesystem. The harness restricts Docker to a local Unix socket, requires readable DockerRootDir
and writable volume/bind mount paths on the same filesystem device as the supplied
path, checks free bytes, and compares summed container ceilings with explicit owner
budgets. Separate data filesystems are unsupported. The owner must establish that
budgets are available/reserved and that the local socket is not a remote forwarder. It is not a continuous disk emergency brake. Provide sufficient
headroom for the entire bounded run; use the campaign's owner-controlled resource
admission process. No capacity purchase or new image pull is implied.

## Commands

From the repository root, validate without a server:

```sh
python3 -m unittest discover -s docs/cheminee-campaign/resource-measurements -p 'test_*.py' -v
python3 -m py_compile distribution/cheminee-local/readiness.py distribution/cheminee-local/smoke.py docs/cheminee-campaign/resource-measurements/run.py
```

Expected: nine tests `OK`, compile exit 0. Tests use synthetic responses and inspect
records; no live readiness, resource or chemistry acceptance follows.

With owner-admitted resources and real verified artifacts, fill these variables
from retained evidence, not guessed values:

```sh
python3 docs/cheminee-campaign/resource-measurements/run.py \
  --output "$NEW_PRIVATE_OUTPUT_DIRECTORY" \
  --image "$VERIFIED_CHEMINEE_IMAGE_ID" \
  --storage-path "$DOCKER_DATA_FILESYSTEM_PATH" \
  --min-free-bytes "$ADMITTED_DISK_RESERVE_BYTES" \
  --memory-budget-bytes "$ADMITTED_MEMORY_BYTES" \
  --cpu-budget "$ADMITTED_CPU_COUNT" \
  --source-commit "$VERIFIED_SOURCE_COMMIT" \
  --runtime-provenance "$VERIFIED_PROVENANCE_FILE" \
  --runtime-provenance-sha256 "$VERIFIED_PROVENANCE_SHA256"
```

Expected preflight result: `admitted_not_executed`, `live_measurements: pending`,
exit 0 and `admission.json`. Failure exits 1 and retains a failed report. Add
`--execute` only for an owner-authorized run, using a fresh output directory.
Optional `--elasticsearch-container NAME --elasticsearch-image sha256:...` observes
an idle neighbor; it creates no Elasticsearch workload. Expected successful
execution: `passed`, `smoke.json` plus `admission.json`. A failed smoke exits 1.
The original local smoke's synthetic strict chiral/nonchiral/count oracles remain
in force. No representative benchmark or active-ES coexistence claim is justified.

## Interpretation and failure detection

The smoke samples idle/import/query/restart/post-restart phases. It requires stable
samples for idle/import/query/post-restart, rejects missing/stale/cross-phase-only
coverage, records failures during primary restart and rejects failures elsewhere.
A short import can finish between samples: that is an incomplete measurement, not
a zero peak. Do not pad an import with idle sleep and label it import memory.
Restart samples/gaps are retained; the intentionally absent primary may be
unsampleable. Readiness requires literal JSON `true`; transient connection/503
failures retry within a deadline. Authentication and unexpected HTTP failures stop
immediately. Membership-wait samples are separate from the successful post-restart read phase.
Strict startup search retries only the known membership error and
never retries writes or incorrect query results. Final primary health/OOM state
and cleanup failures now affect the verdict.

Cgroup peaks/OOM values are container-lifetime counters, not phase deltas. Restart
can reset them. RSS and cgroup charges measure different things; do not add RSS
across processes as private memory. Sampling may miss short peaks. Storage before
and after includes unrelated concurrent host activity. Keep input identities,
artifact hashes, phase gaps and owner budgets alongside results. Reports are
private experiment evidence; do not publish raw smoke errors or catalog data.
