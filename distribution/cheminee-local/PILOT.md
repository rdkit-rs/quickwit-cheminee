# Versioned private pilot preparation

The [candidate workflow](../../.github/workflows/prepare-cheminee-pilot.yml) and
`build_pilot.sh` prepare a source-addressed Cheminee candidate using the Quickwit
engine. Only lightweight provenance/lifecycle tests have run for this version.
No current native image, matching gem, live restore result or release approval is
claimed. The fresh test host cannot admit a local build within its current disk
budget. The PR workflow therefore prepares the candidate on a disposable hosted
runner; the fresh host owns kind/object-store acceptance. Do not start a duplicate
build on either constrained VFS host. GitHub may not offer manual dispatch until
the workflow exists on the default branch; the PR trigger checks out its exact
head rather than a synthetic merge commit. The commands below also support a
separately admitted build host.

The recipe builds `descriptor-v1`, uses the existing checksum-pinned RDKit,
TensorFlow and descriptor-model installers, and captures the stripped executable's
full embedded commit through its real loopback `/api/v1/version` endpoint. It also
checks the unique node identity and captures that same process's `/openapi.json`.
The candidate version is `<embedded engine version>.pre.pilot.g<full source SHA>`;
it is a prerelease identity, never an invented release tag. An unknown, stale or
short embedded revision fails packaging. The four required model files are checked
against the native loader's hashes, copied, and configured inside the image.

The pinned Ruby generator consumes this captured schema, regenerates twice, and
builds a local gem. Before live acceptance, every installed gem file is checked
against the exact archive. The final manifest binds the accepted gem SHA256,
server and projected schemas, model provenance, OCI labels, actual local image
config digest and every exported image layer. `cheminee-image.tar` is a Docker
archive with OCI image labels; no registry manifest digest exists until publication,
so the manifest records it as null. Dependencies from Ubuntu's package repositories
are inventoried, not claimed to be reproducibly rebuilt.

Acceptance uses a 4 GiB, two-CPU, restart-disabled local container and the installed
gem. It checks the 10,001-row synthetic catalog boundary, native preparation,
refresh and rollback, then clean shutdown/restart and retained-data reads. It then
quiesces the source, backs up its complete file data and Ruby journal, checks fresh
empty destinations, verifies restored file bytes, permissions and normalized
hardlink groups, and re-audits
without reimport on a different container/volume/journal. The restored journal also
exercises a revision-checked rollback. Source and restored services never overlap.
These are **prepared gates**, not results until a real run passes. The data contains
20 structures with repeated offers; this is not the diverse 100k/kind/object-store
experiment, forced replacement, online backup, HA or sizing qualification. The
offline mapper oracle checks the real wire path; eight retained historical golden
rows and curated small graph/fingerprint cases provide additional truth checks.
It is not an independent oracle for an arbitrary 100k corpus.

Phase-boundary receipts retain cgroup v2 current/peak/events, data-directory bytes
and wall time, with the observed incarnation beside each sample. Peaks and events
describe the observed cgroup/incarnation lifetime and may reset on restart; they
do not attribute isolated phase memory or establish throughput. A shutdown timeout,
nonzero exit, OOM, unexpected incarnation, nonempty restore destination or hash
mismatch fails without a forced-kill/restart fallback. Failure evidence and owned
volumes remain until the disposable host is retired by its owner. No real catalog
or credentials belong in these synthetic artifacts. The protobuf/ZIP dependency
security findings remain an explicit release hold.

## Exact native build on an admitted fresh host

First obtain CPU/RAM and persistent disk admission for the **Docker storage
filesystem**, build target, image/context/export copies, retained source and restore
volumes, journals and reserve. The candidate job's 24 GiB initial and 8 GiB post-build
checks are provisional CI allowances, not a sufficient kind/100k budget. The
script's explicit argument records operator intent; it does not measure capacity.
Use an otherwise unused disposable checkout/host, Linux amd64, Docker, Git, and
the pinned Rust 1.96.1 toolchain. Set `CHEMINEE_SOURCE_REVISION` to the reviewed full
commit supplied by the handoff. No `GITHUB_ACTIONS` environment impersonation is
needed. From the repository root:

```sh
set -euo pipefail
test "$(git rev-parse HEAD)" = "$CHEMINEE_SOURCE_REVISION"
git diff --exit-code HEAD --
test "$(rustup run 1.96.1 rustc --version | cut -d ' ' -f 2)" = 1.96.1
mkdir -p .pilot/native
docker run --rm --memory=5g --memory-swap=5g --cpus=2 --pids-limit=1024 \
  -v "$PWD:/work" -v "$(rustup run 1.96.1 rustc --print sysroot):/opt/rust:ro" -w /work/quickwit \
  -e PATH=/opt/rust/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  -e EXPECTED_REVISION="$CHEMINEE_SOURCE_REVISION" \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/work \
  -e CARGO_BUILD_JOBS=2 -e CARGO_PROFILE_DEV_DEBUG=0 -e CARGO_PROFILE_TEST_DEBUG=0 \
  -e CARGO_INCREMENTAL=0 -e CFLAGS=-std=gnu17 \
  -e PKG_CONFIG_PATH=/opt/cheminee-tensorflow/lib/pkgconfig \
  -e LD_LIBRARY_PATH=/opt/cheminee-tensorflow/lib \
  -e QW_CHEMINEE_MODEL_ASSETS=/opt/cheminee-model/assets \
  -e TF_NUM_INTRAOP_THREADS=1 -e TF_NUM_INTEROP_THREADS=1 -e OMP_NUM_THREADS=1 \
  ubuntu@sha256:f144425ff09be612d6d9ad965196e9cdc23dae1f42110a8a11a3e9a8198759f7 \
  bash /work/distribution/cheminee-local/build_pilot.sh --admitted-disposable-builder \
  2>&1 | tee .pilot/native/build.log
```

The script writes `.pilot/context`, actual server OpenAPI, native descriptor golden
checks and the catalog oracle. It refuses an existing packaging context. Preserve
the entire build log and failed outputs before retrying. The remaining generator,
gem install, image build, `accept_pilot.py` and `finalize_pilot.py` commands are in
the candidate workflow with pinned Java/Ruby/generator versions. They can run under
the same admitted fresh owner, sequentially; do not dispatch a second heavy lane.
The workflow uploads only accepted private candidate artifacts and separate failure
diagnostics. It has no push, tag, deployment, cloud-resource or credential steps.

Lightweight checks (no Cargo, Docker or downloads):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s distribution/cheminee-local -p 'test_pilot*.py' -v
bash -n distribution/cheminee-local/build_pilot.sh
```
