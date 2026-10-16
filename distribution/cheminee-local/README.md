# Local native Compose experiment

This is a tested local experiment, not a published image or a production deployment.
It uses a source-attributed native executable, a pinned Ubuntu base, UID 10001,
a read-only root filesystem, a persistent data volume, bounded caches/queues and
container resources. New indexes must also set `indexing_settings.resources.heap_size`
to an appropriate bounded value; this smoke explicitly uses `32MiB`. The server
default is 2 GB per indexing heap, which is unsuitable for this container ceiling.
The catalog-generation Ruby example omits that setting and has not been exercised
under this ceiling. Only Linux amd64 has been exercised. The 768 MiB ceiling,
2 CPUs and individual cache limits are experimental bounds, not workload sizing
recommendations. Elasticsearch coexistence has not been measured.

## Prepare and start

First build the native executable in Ubuntu 26.04 amd64 with Rust 1.96.1 and the
checksum-pinned RDKit packages installed by
[`install-rdkit.sh`](../../quickwit/tantivy-rdkit-mapper/ci/install-rdkit.sh):

```sh
cd quickwit
CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=4 \
  cargo build --locked -p quickwit-cli --features native-chemistry --bin quickwit
cd ..
python3 distribution/cheminee-local/prepare_runtime.py \
  --binary quickwit/target/debug/quickwit \
  --source-commit "$(git rev-parse HEAD)" --output /tmp/cheminee-runtime
```

Run packaging **inside that same trusted builder**, with `curl`, `ldd` and `strip`
installed. The output must be a new directory. This copies the executable and its
resolved shared libraries; it does not install compilers in the runtime or copy
the builder's custom certificate trust store. Source attribution is supplied by the
caller: the packaging script hashes bytes but cannot prove which source produced
them. Keep the build log, clean source revision and generated manifest together.
Do not run it on an untrusted executable. Binary reproducibility, data-dependent
RDKit features and redistribution/license clearance are not established here.

On the Docker host, build from that output and start from the repository root:

```sh
docker build -t quickwit-cheminee:local /tmp/cheminee-runtime
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
