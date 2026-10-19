# Behavior-preserving remediation: bounded investigation

Source baseline: c774b166e0bcffa9eadbcda48d4d657d797ca639. This is a design
and source-inspection checkpoint, not dependency clearance. Existing authorization
covers behavior-preserving fixes and reviews. No residual finding is accepted.

The six exact domains and standard domain rules are approved, but publication of
the v2 environment configuration remains pending. These rules are not effective
egress permission in the running environment. Do not bypass proxy denials.

## LRU repair probe and integration boundary

Independent Astra MAX design review selected an exact pop() panic-safety backport
to both lru 0.16.4 and 0.17.0. It detaches the node before dropping the key. The
separate get_or_insert_mut_ref lifetime correction is not this advisory's fix.
Tantivy's pinned revision and Chitchat 0.11.1 remain unchanged.

scripts/ci/lru_backport_probe.py verifies cached archive SHA-256 values, extracts
three known regular files, replaces exactly one original implementation, and
builds a dependent regression harness offline. Two scoped tests pass for each
version with both std-map and default hashbrown features (eight executions).
The panic case asserts unwind, key removal, length, order and actual eviction;
the ordinary case checks recency and replacement. Probe output is about 62 MiB
in /tmp. No original vulnerable regression was executed and no Miri claim is made.
These are not the complete upstream library tests or parent integration tests.
Initial dependency resolution uses the offline cache: this is an exact-source
backport probe, not a fully locked dependency build. Retained harness Cargo.lock
files allow locked replay. Evidence records Cargo/rustc versions, invocations,
and SHA-256 values for the script, fixture, source, manifests, locks and logs.

Before introducing the two vendor overrides, preserve original package versions,
registry source/checksum, exact accepted diff and all patched file hashes. The
audit currently matches source identity: a local source override would make its
raw registry findings disappear. Add a validated registry-provenance projection
and keep both original advisory rows visible with separately verified backport
status. Reject unknown source contents or unmapped overrides. Do not subtract
these rows or describe the full audit as clean. The application graph and its
11 blocking matches are unchanged at this checkpoint.

Tantivy's cache contains decompressed blocks; Chitchat's contains garbage-collected
node history. Required follow-on tests include test_store_lru_cache and compression
variants, test_dead_node_garbage_collection, test_reset_garbage_collected_node_state,
test_node_goes_from_live_to_down_to_live, and stale-node recreation. Tantivy's
format_6/7 compatibility tests exclude the quickwit feature; they do not establish
production-format compatibility. Keep an actual baseline production index reopen
fixture and old/new Chitchat peers for convergence/restart validation.

## TensorFlow and RSA investigation

- tensorflow 0.21.0 pins protobuf exactly to 2.27.1. Runtime linking changes the
  native loading path, not this dependency. First investigate regeneration of
  binding protocol types against a repaired protobuf library; retain SavedModel
  loading and error behavior. A small C API bridge is a fallback, not yet selected.
- tensorflow-sys 0.24.0's build script uses ZipArchive::by_index, enclosed_name,
  File::create and io::copy. It does not call the advisory-named bulk extract
  methods in this helper. This narrows reachability analysis but does not clear
  the ZIP findings or prove safe extraction in all environments. Test traversal,
  symlinks, pre-existing destination links and permission handling on any upgrade.
- Descriptor compatibility requires the serve tag, serving_default_dense_input,
  StatefulPartitionedCall, float32 tensors, 128-dimensional centroids, and the
  current Slice/ExpandDims/BroadcastTo/Sub/Square/Mean/Sqrt/Neg/TopKV2 graph.
  Preserve ties and numerical outputs against independent fixed fixtures.
- Recorded all-features metadata has four direct RSA parents: openidconnect,
  reqsign-core, reqsign-google and sqlx-mysql. This graph is not a deployment
  reachability proof. reqsign-core signs service-account JWTs; reqsign-google
  also signs requests with private keys. Preserve both authentication paths when
  replacing the backend; random blinding alone is not a clearance argument.
- Pulsar OAuth uses provider discovery and issuer validation through OpenID;
  its source also manages token refresh and fallback to non-expired tokens.
  Do not replace it with a guessed token URL or remove credential modes.
- SQLx MySQL's inspected authentication code parses a public RSA key. Its
  presence is not proof that Quickwit performs private RSA operations there.
  Prove the edge unused across supported features before removal. Workspace
  consumers inspected request PostgreSQL; all-features resolution alone cannot
  prove safe removal of the MySQL lockfile entry.

## Azure compatibility matrix before replacing the SDK

| Contract | Source baseline and required verification |
|---|---|
| Configured authentication | from_uri prefers resolved account key, otherwise create_credential. Test environment/managed identity selection, expiry, invalid credentials, no secret logging. |
| Constructor authentication | new accepts StorageCredentials. Preserve supported credential variants, including SAS; distinguish constructor support from configured URI support. |
| Emulator | Existing integration-testsuite uses ClientBuilder::emulator and no retries. Preserve Azurite endpoint behavior without enabling it in production. |
| Names and ranges | Preserve URI/container/prefix parsing and lossy path conversion; test empty objects, exact range boundaries, missing keys, streaming and truncation. |
| Integrity | Single uploads and every multipart block carry MD5. Reject checksum mismatches; verify actual request headers, not just builder calls. |
| Ordered publication | Concurrent blocks use block:NNNNN IDs, sorted before put_block_list. Test reordered completion, failed blocks, interrupted upload and commit failure. No success before commit acknowledgement. |
| Retries and ambiguous acknowledgement | Preserve per-operation policy and error categories. Existing explicit retries surround reads and part uploads; final commit has no explicit outer retry. Record SDK-internal retries separately. Test lost responses without claiming exactly-once writes. |
| Deletion | Missing-object deletion succeeds; bulk operation reports individual failures. Test authorization failures and mixed outcomes without hiding them. |
| Resource behavior | Preserve bounded upload concurrency and streaming; measure memory and cancellation before changing defaults. |
| Diagnostics | Preserve duration/byte/in-flight metrics with bounded labels. Redact authorization, signed query strings and catalog contents in logs and debug bundles. |

Maintained SDK adaptation is preferred; OpenDAL is an alternative only after the
same matrix passes, including its signing dependency graph. No adapter is selected
or installed at this checkpoint.

## Resource admission for subsequent validation

Measured local free space at investigation start: 711,340,032 bytes on /workspace
and 4,119,773,184 bytes on /tmp. The /workspace emergency floor is 671,088,640
bytes (640 MiB): only 40,251,392 bytes of headroom. No full builds or benchmarks.
Use cached artifacts, bounded reads and small isolated checks in /tmp; recheck
free space before writes. Do not delete unrelated caches or history.

Fresh-environment tests require the published v2 configuration and successful
ordinary downloads, a source checkout plus pinned native dependencies/model
fixtures, and separate persistent storage for baseline and candidate compatibility
fixtures. Run heavy phases serially on the reported four CPU equivalents and
16 GiB memory limit. The reported 29.83 GiB free disk is capacity, not an established
test requirement. Exact full-build peak disk/RAM is unmeasured; do not certify it
as sufficient. Existing local artifacts are 6.3 GiB for one workspace target,
815 MiB for isolated transport and 277 MiB for profiling; these are observations,
not clean-build peak estimates. Instrument the first admitted targeted build,
then calculate remaining headroom before adding native/full-workspace phases.

Required gates: repaired LRU regression and default-feature tests; Tantivy
existing-index reopen/search and update tests; Chitchat restart and mixed-version
gossip/state-transfer tests; Azure matrix; TensorFlow fixed-output parity; RSA
credential/provider tests. Local isolated tests cannot replace these gates.

## Additional generator and installer inventory

Cached-only independent Astra MAX inspection identified code outside the earlier
pom.properties inventory: Rhino, Caffeine, JNA and Lombok, among other groups.
JNA includes 26 native payloads and Lombok includes two Windows native binaries.
Class constants identify JNA 5.12.1 / native dispatch 6.1.4, and Lombok 1.18.30
in the baseline versus 1.18.38 in the candidate generators. This is identity
evidence, not security clearance of those binaries.

The baseline's eight .jar-named entries comprise seven ZIP archives and one
zero-byte Micronaut wrapper placeholder. Gradle distribution URLs in templates
do not identify wrapper binary versions: some wrapper hashes remain unchanged in
7.26 despite changed distribution URLs. Keep those components in the inventory.

Cached advisory search found a further Rhino candidate, GHSA-3w8q-xq97-5j7x.
Baseline Rhino version evidence is incomplete, so this is not a confirmed new
match and is not added to the existing tally. Candidate generator POMs declare
Rhino 1.7.15.1, but independent bytecode identity remains to be established.
Installer 0.7.0's six comparable Windows launchers differ from cached distlib
0.3.9 and 0.4.2; their exact native provenance remains open. Absence of package
advisory matches does not clear bundled native code or embedded libraries.
