# Local native Compose experiment

The new [versioned private pilot preparation](PILOT.md) adds exact embedded-revision
checks, required descriptor model assets, a matching installed Ruby gem, and a
prepared fresh-restore acceptance gate. Candidate production and native acceptance
are pending in hosted CI; the separately admitted fresh host owns the larger
kind/object-store test. Historical observations below do not qualify the new recipe.
Do not run another heavy build on the constrained shared VFS host.

The recorded local Compose smoke used the unoptimized native build at
`8009925c6b9757edc77ef8e6111309503028e7c5` (historical evidence). The current
harness and revised resource/restart bounds have not been run live. This is not
a published image or a production deployment.
It uses a source-attributed native executable, a pinned Ubuntu base, UID 10001,
a read-only root filesystem, a persistent data volume, bounded caches/queues and
container resources. New indexes must also set `indexing_settings.resources.heap_size`
to an appropriate bounded value; this smoke explicitly uses `32MiB`. The server
default is 2 GB per indexing heap, which is unsuitable for this container ceiling.
The catalog-generation Ruby example omits that setting and has not been exercised
under this ceiling. Only Linux amd64 has been exercised. The 768 MiB ceiling,
2 CPUs and individual cache limits are experimental bounds, not workload sizing
recommendations. Elasticsearch coexistence has not been measured. The examples
set total memory-plus-swap equal to the memory ceiling, disabling container swap.
Restart policy is `no` throughout measurements, preventing automatic recovery
from replacing a failed container incarnation. Container ID,
RestartCount and StartedAt are checked before and after that restart and at the
end, including observed Elasticsearch containers. The explicit restart sends TERM,
waits at most 60 seconds, and retains/validates the stopped state (no OOM, exit 0)
before starting again. A timeout or abnormal termination fails without restarting
or forcing KILL; inspect the retained report and container before recovery. The
runtime owner must exclude other lifecycle writers. These checks do not establish
the cause of a clean exit coincident with requested TERM, nor detect every hostile
external stop/start between observations. These are functional checks;
concurrent workload and PID-limit behavior have not been validated.

## Prepare and start

First complete the admitted `descriptor-v1` native build described in [PILOT.md](PILOT.md).
For a directly invoked packaging step inside that same trusted builder:

```sh
python3 distribution/cheminee-local/prepare_runtime.py \
  --binary quickwit/target/debug/quickwit \
  --source-root "$PWD" --model-assets "$QW_CHEMINEE_MODEL_ASSETS" \
  --source-commit "$(git rev-parse HEAD)" --output /tmp/cheminee-runtime
```

Run packaging **inside that same trusted builder**, with `curl`, `ldd` and `strip`
installed. The output must be a new directory. This copies the executable and its
resolved shared libraries; it does not install compilers in the runtime or copy
the builder's custom certificate trust store. The source argument must match both
the clean checkout and the executable's full embedded server revision. This does
not prove a reproducible build from those sources. Keep the build log, clean
source revision and generated manifest together.
Do not run it on an untrusted executable. Binary reproducibility, data-dependent
RDKit features and redistribution/license clearance are not established here.

On the Docker host, build from that output and start from the repository root:

```sh
candidate_version="$(python3 -c 'import json; print(json.load(open("/tmp/cheminee-runtime/manifest.json"))["candidate_version"])')"
docker build --build-arg "CHEMINEE_VERSION=$candidate_version" \
  --build-arg "SOURCE_COMMIT=$(git rev-parse HEAD)" -t quickwit-cheminee:local /tmp/cheminee-runtime
export CHEMINEE_IMAGE="$(docker image inspect quickwit-cheminee:local --format '{{.Id}}')"
chmod 644 distribution/cheminee-local/quickwit.yaml
docker compose -f docker-compose.yml.example up -d --wait
python3 distribution/cheminee-local/smoke.py --output /tmp/cheminee-smoke.json
```

The immutable local image ID is required; Compose never pulls a mutable default.
The base is digest-pinned and all copied runtime files are hashed in
`/opt/cheminee-runtime-manifest.json`. System dependencies are captured from the
builder, not rebuilt reproducibly by this packaging step. The host needs Docker
Compose v2 and Python 3; build dependencies and image bytes must be prepared first.
This remains more setup than a published gem/image installation.

The smoke creates and deletes its own uniquely named index, prepares 1,000 synthetic
offers, checks exact chiral identity and supplier membership, gracefully restarts the
container, and checks the same retained results. It records end-to-end HTTP times
and cgroup v2 memory/peak/OOM counters plus process RSS/high-water samples.
Cgroup accounting and process RSS differ substantially on this reused host; shared
file-backed pages can be charged elsewhere. Neither value alone is a portable RAM
requirement. Sampling includes measurement-process overhead and may miss short peaks;
container restart resets some high-water counters. This is a functional/resource observation over a tiny
repeated corpus, not a representative throughput, tail-latency or chemistry-truth
benchmark. It does not establish power-loss durability or multi-node HA.

## Readiness, persistence and diagnostics

`/health/readyz` reports node readiness. The experiment reproduced a short interval
after restart when it returned true but search returned HTTP 500 because searcher
membership had not propagated. The smoke separately waits for a successful strict
read; it retries only that specific startup read error with a deadline and records
every occurrence. It does not retry ingestion. Applications must distinguish node
readiness from successful queries against a pinned, validated catalog generation.

Use `docker compose -f docker-compose.yml.example logs --tail 100` and
`docker stats` for local diagnosis. Logs rotate; per-index metrics and unused OTLP
pipelines are disabled. Avoid routine raw catalog, query or error-body logging.
The journal example's private catalog snapshots do not belong in support bundles.
This setup has no automatic sanitized support-bundle exporter or overload policy
qualification yet. Its only exposed port binds to host loopback; no auth/TLS claim
is made for access outside that host.

`docker compose -f docker-compose.yml.example stop` preserves data. `start` reuses
it. `down` also preserves the named volume; **`down -v` deletes it**. Do not use the
latter for a catalog you intend to keep. The smoke deletes only its own test index.
There is no automatic catalog generation cleanup, backup or recovery service.

The local image measured 305,602,041 bytes before registry compression. The actual
native run and resource observations are retained in the campaign evidence. The
32 GiB workspace had under 1 GiB free during this experiment; Elasticsearch was
not pulled or started. Full workspace CI, representative load, concurrent imports
and searches, Elasticsearch coexistence, and recovery headroom remain open gates.

## Prepared coexistence harness (execution still pending)

An optional override starts a separate, single-node Elasticsearch on loopback.
The 1 GiB JVM heap and 2 GiB container ceiling are test parameters, **not measured
recommendations**. The repository's REST compatibility fixture uses ES 8.9.0;
this override requires an explicitly selected immutable local image and does not
claim compatibility with that or other versions. Record its digest and version.
It has not been started here: the bounded native validation shares a 32 GiB VFS
Docker filesystem, so another image/container could remove recovery headroom.

After preparing images and measuring sufficient disk headroom, run from repo root:

```sh
export ELASTICSEARCH_IMAGE=sha256:<actual-local-image-id>
docker compose -f docker-compose.yml.example \
  -f distribution/cheminee-local/compose.elasticsearch.yml.example up -d --wait
python3 distribution/cheminee-local/smoke.py \
  --observe-container cheminee-local-elasticsearch-1 \
  --output /tmp/cheminee-es-coexistence.json
```

The extended smoke records both containers during Cheminee idle/import/query/restart
phases, including cgroup peaks/OOM and Elasticsearch process RSS. It reads process
names only, not arguments or environment. It creates **no Elasticsearch workload**:
that first run establishes idle-neighbor coexistence only. A separate run with a
retained representative Elasticsearch indexing/search workload is required before
making active-coexistence or sizing claims. Retain the workload, image identities,
host CPU/RAM/disk, before/after storage, sampling gaps and result oracles. Do not add
process RSS values as if shared pages were private memory. This harness has syntax
and Compose configuration checks only; it is not runtime acceptance evidence.
The optional Elasticsearch named volume persists across `down`; remove it only when
its explicitly disposable test data is no longer needed.

Observation requires cgroup v2 and a Docker healthcheck on every additional container.
Counters/peaks are container-lifetime values, not increments attributable to this run.
Docker commands have deadlines; the sampler stops before its verdict. Missing,
stale or cross-phase samples cannot establish phase coverage. Short import or
post-restart query phases may therefore deliberately fail measurement completeness.
For a complete measured query phase, use a separately retained bounded repeated-read
workload; do not substitute idle sleep and label it query memory. Historical native
smoke evidence predates these stricter sampling checks and is not a run of this version.

## Resuming from the v5 checkpoint

V5 does not include the native runtime. Do not follow the historical build recipe
above for the bounded campaign continuation. Obtain a compatible verified artifact
and resource admission from the sole runtime owner. The new
[resource measurement wrapper](../../docs/cheminee-campaign/resource-measurements/README.md)
checks existing container identities, health, configured limits and explicit owner
budgets before optionally invoking the smoke. It never builds or starts a runtime.
Its unit/configuration checks are separate from pending live measurements.
