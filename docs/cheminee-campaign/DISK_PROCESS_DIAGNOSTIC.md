# Disk and process diagnostic — 2026-10-16

No new build was started for this analysis. Snapshot is approximately 15:10 UTC;
raw measurements and per-command sampled free space are in [disk-process-diagnostics.json](evidence/schema-timestamp/disk-process-diagnostics.json).

## Measured facts

- Filesystem:33,770,192,896 bytes total (31.45 GiB; df rounds to 32G),
  762,327,040 available (727 MiB),98% usage. Inodes 28% used:
  577,836 used /2,097,152 total;1,519,316 free. Capacity, not inodes, is tight.
- Native campaign target:6,595,780 KiB (6.29 GiB). Its deps subtree is 5,744,460 KiB
  (5.48 GiB), build subtree 794,404 KiB. Categories by apparent file bytes:
  1,031 rlibs≈2.83 GiB;2,025 rmeta≈1.74 GiB;107 shared objects≈414 MiB;
  five executables≈465 MiB. These categories are not independent filesystem usage
  totals: hard links, overlay layers and directory accounting matter.
- Recovery directory:1,390,696 KiB (1.33 GiB), including Cargo registry/git
  1,216,240 KiB (1.16 GiB). Do not add the nested cache again. Original .onboarding
  visible tree:8,614,628 KiB (8.22 GiB), including 3.57 GiB target. It is largely
  a restored lower layer; visible du is not recoverable writable space.
- One target path: /workspace/quickwit-cheminee-pr3-inspection/quickwit/target.
  Rust 1.96.1; dev/test debug=0; incremental=0;4 Cargo jobs. Incremental directory
  is 4 KiB. This is already a stripped-debug/nonincremental development build,
  not an accidental release+debug+incremental triple build.
- Native builder bind-mounts the workspace and registry/git caches. Docker driver
  is `vfs`. Reported images: builder 2.005 GB, Ruby 995.7 MB, Ubuntu 100.9 MB (shared with
  builder). Running builder's reported writable layer is 32,472,554 bytes; reported
  full root filesystem is 2,037,713,374 bytes. The retained
  Compose data volume is 268.5 MB. Docker's logical/shared/writable accounting is
  not a measurement of physical VFS clone allocation; direct host VFS du was
  unavailable. Container/image duplication is supported by observed reclamation,
  but exact per-layer physical savings were not instrumented.

## Build growth and failure sequence

Free-space measurements are sampled once/second plus final free space; transient
peaks can be missed. Use minimum(all periodic samples plus final), not the last sample
alone. No profiler attributed concurrent filesystem changes to individual crates.

| Command/run | First free → final free | Outcome |
| --- | --- | --- |
| Native server build |2,793,988,096 →2,534,346,752 bytes |Passed;106 s sampled;≈248 MiB net growth |
| Raw workspace all-features Clippy |2,793,439,232 →1,519,534,080 |Failed TensorFlow download 403;≈1.19 GiB net growth |
| Scoped native Clippy |1,519,517,696 →1,284,546,560 |Passed;≈224 MiB net growth |
| Workspace with existing TF 2.15.1 |1,284,538,368 →665,366,528 |640 MiB disk guard stopped process group |
| Resume after context compression |806,019,072 →780,992,512 |Failed krb5-src const-qualifier compilation |
| Explicit C17 retry |780,980,224 →780,300,288 |Same krb5 failure;156 s sampled;79.60 MiB below-start sampled trough, despite near-zero net growth |

Earlier timestamp-unit build stopped at 652,713,984 bytes with the 640 MiB guard.
An earlier workspace attempt used 512 MiB guard and ended at 450,002,944 bytes.
Guards terminate below threshold; they are not hard reservations, so allocations
between samples and termination can overshoot. Current 640 MiB guard sends SIGTERM,
with SIGKILL fallback only if the process has not exited after 15 seconds. This is emergency protection, not adequate admission
headroom for a cold all-features build.

**Avoidable process error:** raw Cargo retries bypassed the existing CI entrypoint
`quickwit/scripts/ci/with-krb5-c23.sh`, already invoked by `.github/workflows/ci.yml`.
It verifies the exact krb5-src 0.3.4 checksum, applies the retained patch with zero
fuzz, and supplies an isolated Cargo source override. The repeated Kerberos/C17
attempts were avoidable. They do not establish an unresolved repository defect.
The correct wrapped full-workspace check is still unrun in this continuation.
The wrapper currently uses a fresh mktemp path for the patched crate; a stable,
checksum+patch-keyed source directory would be worth evaluating to avoid path-based
cache churn, but that churn was not measured here.

## Reclamation and rebuild costs

- Deleted 1,384 old .onboarding rlib/rmeta files plus incremental directories only
  after inventory, preserving sources/executables/evidence. Measured free space
  1,573,670,912 →1,573,535,744: **no recovery**, a 132 KiB decline that does not isolate whiteouts from other writes. Do not
  repeat lower-layer deletion as a disk strategy.
- Removed the retired runtime image and stopped/removed the idle Ruby container.
  Exact before/after free-space pairs and removed Ruby container --size fields
  were not retained, so reclaimed bytes are **unknown**. Prior conversational
  approximations must not be treated as measurements. Ruby image,
  bound installed gems, runtime manifest/context and test evidence were preserved.
- Runtime build context:208,539,648 allocated bytes by du before archival;
  verified gzip archive 67,917,733 bytes. Verified every regular file hash and mode
  before deleting the expanded tree. Independent guard snapshots before/after
  that interval were 665,366,528 and 806,019,072 available bytes (+134.14 MiB).
  They were not an atomic cleanup measurement; intervening small writes occurred.
  Exact cleanup-attributable filesystem reclamation is therefore unknown.
- Attempted compressed Docker image export had hidden staging growth and tripped
  its 128 MiB emergency floor; export was stopped/removed and original Ruby image
  retained. It was **not** a successful reclamation. No peak staging-size log exists.
- Prior-session removal of native library/metadata artifacts caused rebuilding;
  exact attributable cost is unavailable. This continuation reused the target
  incrementally. Feature-set changes (native scoped vs workspace all-features)
  and CFLAGS change still generated distinct dependency outputs/rebuild work.
- Current checkpoint preparation is small: v4 archive 8,352,398 bytes; pending
  continuation archive 8,592,966 bytes; staging≈8.2 MiB, Git bundle≈561 KiB. Full
  source/bundle/gem assembly+verification took about 1.14 seconds by the session
  tool timing (not a retained benchmark log).
  This excludes remote upload and environment restore time. No measured restore
  duration is available. Binaries/images/indexes are excluded; runnable restoration
  requires them too, and its total duration was not measured. These checkpoints
  preserve source/evidence, not an instant runnable environment.

## Ownership and reclaimability boundaries

| Files / layer | Observed status | Cleanup policy |
| --- | --- | --- |
| Git source, evidence, bundles, Library v4/current archives | Small preserved campaign deliverables | Preserve; not build scratch |
| Active target/debug outputs | Generated by native/check/test recipes; per-file overlay placement not enumerated | Reproducible but deleting loses validated build reuse; only retire obsolete variants after replacement |
| Bound Cargo registry/git cache | Reused by builder; may contain restored and new files | Do not assume every byte is reclaimable or duplicate |
| Old .onboarding caches | Restored content; deletion test recovered no bytes | Treat lower-layer deletion as ineffective; not a cleanup budget |
| Docker image layers | Retained immutable image content; VFS driver confirmed | Reported logical image sizes do not prove physical reclaimed bytes |
| Builder container root | Docker reports32,472,554 writable bytes /2,037,713,374 full-root bytes | Keep while native work is active; physical VFS allocation unknown |
| Removed Ruby container root | No --size snapshot was retained | Exact writable/full-root/reclaimed bytes unknown; do not reproduce copy to measure |
| Runtime context archive |67,917,733-byte verified archive; expanded copy removed | Restore as needed; no source/runtime content was discarded |
| Compose volume |Docker reports268.5MB; retained persistent data | Do not prune as disposable build cache |

Docker reports build cache0B. Broad cache-prune commands are not justified by
these measurements. No per-file lower/upper-layer map was collected; this table
does not claim that every visible restored file is immutable or every target byte
is immediately reclaimable.

## Test and operational dependencies

Native chemistry tests require pinned RDKit, Rust/C++ tooling and current prepared
schema contracts. The selected scoped checks pass. All-features additionally pulls
TensorFlow, Kafka/SASL/Kerberos/OpenSSL and other connector paths; the default
TensorFlow 2.13.0 download was 403-blocked, while a retained 2.15.1 installation was
used explicitly for retries (not the same dependency environment). CI workflows, the root docker-compose.yml and
Makefile also define PostgreSQL and broader integration services; coverage includes
LocalStack, Pub/Sub emulator, Azurite, fake GCS and Pulsar. Clippy success alone would
not constitute full service-backed test success. Native HTTP uses local synthetic
fixtures; Compose+Elasticsearch has not run alongside these build costs.

## Recommended process changes (proposals, not measured capacity targets)

1. Read and reuse the repository's exact CI wrapper/feature matrix before the first
   expensive invocation. Record the toolchain, environment and dependency recipe.
   Stop retrying a known failure unless the next run changes its actual cause.
2. Admit a build only after budgeting the observed growth for that build class,
   linker/export staging, a recovery reserve and concurrently running services.
   For this history, a 640 MiB tripwire is demonstrably too late as a start criterion.
   Derive a numeric admission threshold from more runs; do not present an invented
   fixed GB target as proven. Retain 1-second samples and final free space.
3. Keep one bounded build process at a time and a shared canonical target/cache
   with an explicit feature/toolchain recipe ledger, not a separate physical target
   directory per feature set. Prefer incremental reuse over
   delete-and-rebuild; consider stable verified patched-source paths. Cap retained
   obsolete variants only after successful replacement and provenance capture.
4. Separate build validation from Compose/ES measurement in time or provisioned
   storage. On a future environment, evaluate a copy-on-write Docker driver/storage
   layout; do not change the current daemon or buy capacity without approval.
5. Inventory lower/upper-layer provenance before deleting. Reclaim confirmed
   campaign-owned writable artifacts, not snapshot lower layers. Preserve small
   source/evidence checkpoints early. Avoid docker save as a low-disk escape hatch.
6. Make continuation entrypoints read a compact state file: exact HEAD, test matrix,
   correct CI command, active PID ownership, free-space baseline, artifact manifests,
   missing corpus and open gates. This reduces repeated discovery/rebuilds and
   prevents a recovered source archive being mistaken for a restored runnable stack.

Backend resume failures on the original two attempts are recorded as backend errors.
No telemetry ties them to ENOSPC, inode exhaustion or these later guard stops.
Do not attribute backend disconnects to disk without platform-side evidence.

The next validation must use the committed [campaign runbook](../../quickwit/scripts/ci/CAMPAIGN_RUNBOOK.md), offline dependency preflight and admission runner. The earlier raw Cargo retries missed the existing Kerberos wrapper; that was an avoidable process error. No correctly wrapped full-workspace check has run.

Implemented guard policy requires 4 GiB growth allowance plus 1 GiB reserve before a workspace check, separately from the 640 MiB emergency floor. These are provisional operating allowances, not a measured sufficient peak. The current admission check refused the phase without spawning Cargo. Existing VFS containers and the shared target are reused; unbudgeted image/export/container creation phases are refused.

Host `/tmp` is a separate roughly 9.44 GB tmpfs. Inside the builder, `/tmp` shares the constrained overlay with `/workspace`; host temporary capacity is not persistent builder headroom. No heavy build was started for this diagnostic or guard validation.
