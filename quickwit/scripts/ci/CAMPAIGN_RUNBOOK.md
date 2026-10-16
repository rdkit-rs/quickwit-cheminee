# Bounded Cheminee campaign work

Use the existing `cheminee-native-builder`. Its Rust/C++/RDKit environment and
bind-mounted Cargo cache already exist. Docker uses **VFS** here; creating another
builder or Ruby container is not a cheap substitute for reusing it. Inspect
`docker ps -a --size` and `docker inspect` first. A stopped existing container can
be started after checking for surviving work. A missing container is a distinct,
unbudgeted creation phase: do not automatically recreate it. No Docker driver,
security, daemon or infrastructure changes are authorized by this workflow.

## Inspect before retrying

Run `campaign_phase.py status --state <recorded-state.json>` **inside the original
builder/PID namespace**. It reports process identity, live group members and the
shared heavy-phase lock. Do not equate a lost tool connection with job failure.
A running group must not be restarted. A missing process without a reliable terminal
state requires review of the log and state; only then pass the exact recorded state
SHA256 using `--reviewed-prior-state-sha256`. This is a recorded operator decision,
not automatic retry or a claim the prior operation succeeded. Boot/namespace
mismatches refuse automatic reuse; only an explicitly reviewed terminal state can
be reused. Inspect the original container and preserve evidence.

The lock lives at `/workspace/recovery/campaign-heavy.lock`; never unlink/replace
its inode to bypass a busy job. It serializes **cooperating** heavy phases and is
inherited by the child. The runner also checks visible unmanaged compiler processes.
It cannot police raw Docker operations in another namespace. Route heavy work through
the same protocol; do not launch raw Cargo/image/container writers in parallel.
Read-only reviewers should reuse hashed source, logs and test binaries.

## Dependency preflight is separate from compilation

From `quickwit/` in the existing builder, use this explicitly attributed local
TensorFlow 2.15.1 recipe (different from the default 2.13.0 download):

```sh
export PKG_CONFIG_PATH=/workspace/.onboarding/sysroot/usr/lib/pkgconfig
export QW_KRB5_CRATE=/workspace/recovery/cargo-native/registry/cache/index.crates.io-1949cf8c6b5b557f/krb5-src-0.3.4.crate
export CFLAGS=-std=gnu17
export CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0
export CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=4
python3 scripts/ci/campaign_preflight.py \
  --output /workspace/recovery/dependencies-FRESH.json \
  --tensorflow-pc /workspace/.onboarding/sysroot/usr/lib/pkgconfig/tensorflow.pc \
  --tensorflow-library /workspace/.onboarding/sysroot/usr/lib/libtensorflow_cc.so.2 \
  --tensorflow-library /workspace/.onboarding/sysroot/usr/lib/libtensorflow_framework.so.2
```

Preflight hashes the lockfile, existing CI wrapper/patch, cached Kerberos crate and
selected TensorFlow libraries, checks pkg-config resolution, and does no compilation
or network download. Missing dependencies fail separately. It does not prove all
Cargo dependencies are cached or ABI compatibility. If network preparation is needed,
probe that dependency separately with a deadline; do not discover a large download
failure inside another expensive build. Do not silently substitute a TensorFlow recipe.

The existing `with-krb5-c23.sh` remains the Clippy entrypoint. Optional
`QW_KRB5_CRATE` avoids a repeat download; both cached and downloaded bytes must pass
the original checksum before patching. Default CI behavior remains unchanged.
A harmless Cargo substitute verified the forwarded arguments and applied patch;
a wrong crate was rejected before Cargo. This is not a full Clippy run.

## Admission first, emergency stop second

```sh
python3 scripts/ci/campaign_phase.py run --phase workspace-check \
  --state /workspace/recovery/workspace-ADMISSION-FRESH.json \
  --log /workspace/recovery/workspace-NOT-LAUNCHED-FRESH.log --admit-only
```

Current roughly 727 MiB available is insufficient. The policy allows **4 GiB growth
plus a 1 GiB reserve** for workspace checks, then retains a separate 640 MiB emergency
floor. These are provisional conservative operating allowances, **not measured
sufficient capacity**. The observed 1.19 GiB growth ended in failure and is only a
lower bound on successful peak usage. Native build/check allowances are likewise
policy, not recommendations for customer deployments. Unknown image/container/export
phases have no budget or command and are refused. Do not lower a budget to make a
refusal disappear; revise it from evidence and required remaining work.

These allowances apply to the existing shared target with dev/test debug=0,
incremental=0 and four Cargo jobs. Record any recipe change before reconsidering
the budget; Rust flags, Cargo home and target-directory overrides are retained
in state because they affect cache identity and the filesystem that grows.

After admission can pass, with the same explicit dependency environment:

```sh
python3 scripts/ci/campaign_phase.py run --phase workspace-check \
  --state /workspace/recovery/workspace-RUN-FRESH.json \
  --log /workspace/recovery/workspace-RUN-FRESH.log \
  --preflight /workspace/recovery/dependencies-FRESH.json
```

The runner fixes the workspace command to the repository compatibility wrapper,
checks fresh output paths, validates finite integer budgets and fresh preflight
hashes/environment, and writes durable launch intent before spawning. It samples
filesystem-wide free space and retains initial, periodic and final minima. Samples
can miss subsecond peaks and include unrelated writes; they are not per-crate
allocation measurements. PID/group cleanup excludes zombies, escalates when live
children ignore TERM, and does not mark same-group background survivors successful.
Descendants that create a new session and close inherited descriptors can escape
this cooperating-process boundary. After supervisor SIGKILL, the inherited lock
blocks duplicate cooperating work but no longer monitors disk usage.

Outcomes distinguish admission refusal, dependency refusal, process failure, timeout,
disk stop, supervision error and completion. A transport disconnect is not inferred
from any of these. The current correctly wrapped full workspace check remains unrun.

## Cleanup and checkpointing

Retain the small source/evidence/Git-bundle/gem checkpoint before cleanup. Current
archives are about 8 MiB and exclude binaries/images/indexes; runnable restore cost
is not measured. Inventory a candidate, record `df -B1` before and after, and delete
only a known reproducible writable artifact after preserving its required bytes or
recipe. Keep source, evidence, indexes and Docker volumes unless specifically retiring
them. Deleting restored lower-layer caches reclaimed nothing here. `docker save`
used hidden staging and was not a successful low-disk reclamation strategy.

Keep a shared target/cache with an explicit recipe ledger. Do not create one physical
target per feature combination or erase caches after every interruption. The CI
wrapper's temporary patched-source path could cause cache churn, but this is not
measured or changed here. Future stable-source caching must preserve checksum/patch
verification and atomic initialization.

The tiny-process test suite exercises admission boundaries, NaN/bool rejection,
lock survival after supervisor death, TERM-resistant grandchildren, durable intent,
preflight rejection and namespace mismatch. It launches no Cargo or Docker builds.
