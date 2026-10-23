# Local acceptance with verified JSON 3.1.0

Transfer Library `libfile_84bac7810ab0819182681648d89d2a36` was read as complete
text and verified SHA256 `79cfdf58bf989c8ce167ec17f4fe09bc1e5caa53fc971efea89761faf37eb1da`.
Strict base64 decode yielded 624,867 archive bytes with SHA256
`d4b0535539e6a33af4b5e40676f5a542c9391cc98fd16e71f1c27af57573aff6`.
All 33 regular relative-path files matched size/hash before isolated extraction;
no links, absolute paths, traversal or unmanifested files were accepted.

The existing interpreter/libruby hashes match the corrected worker report.
ELF inspection and ldd resolve the extension's genuine libruby-3.3.so.3.3 to the
existing onboarding runtime. No SONAME alias, marker fabrication, dependency-lock
change, compilation, package installation or new container was used. Existing
metadata was restored unchanged into `/workspace/recovery/json31-isolated`.

Actual JSON::VERSION3.1.0, both real native paths and Unicode/u64 roundtrip were
checked before each run. Source base is f8c633d440e985bd30f3e6d1e567560f685f270b
plus the reviewed JSON feature-selection fix in this commit. Results:

- Installed gem wire suite: 20 tests/392 assertions, seed10109.
- JSON provenance guard: 9 tests/10 assertions.
- Local journal/process suite: 16 tests/86 assertions, now using JSON3.1.0.
- Read-only native smoke inside the existing builder: exact 16-row graph/Tanimoto
  counts/enumeration and strict failed-leaf/unchecked partial-result checks pass.

Do not sum these as unique coverage. The guard's first real pinned run found a
false rejection of Faraday request/response json.rb files. It now identifies JSON
features relative to load-path roots; a regression test preserves middleware
coexistence while retaining shadow/version/native provenance rejection. This fixes
a test acceptance guard, not shipping gem behavior. Other dependencies retain
activated-spec lock checks; actual-code provenance is explicitly checked for JSON.

Run the retained script from this same workspace; the wire suite includes all
lock checks and the strengthened loaded-code guard. For the native smoke use the
existing builder with LANG=C.UTF-8, SDK_SMOKE_HOST=127.0.0.1:19480,
SDK_NATIVE_FIXTURES=/workspace/recovery/composable-native-run1 and local NO_PROXY.
The first builder probe failed at parsing the Unicode literal under US-ASCII;
setting the locale fixed the harness without changing API code.

## Remaining admission and acceptance boundaries

At measurement, free space was 732,061,696 bytes (about698MiB). Reviewed workspace
admission remains 5,368,709,120 bytes: shortfall4,636,647,424 bytes (about4.32GiB).
The separate640MiB emergency floor has only about58MiB margin. These are measured
filesystem values plus provisional admission policy, not successful-build sizing.
No further heavy phase is admitted. Do not export VFS images or duplicate containers.

Smallest workspace-CI resolution is to establish at least the missing headroom
through verified reclaimable writable artifacts or an already provisioned suitable
workspace, then refresh dependency preflight and use the existing compatibility
wrapper. Do not assume lower-layer deletion reclaims bytes or delete reusable
native artifacts blindly. A successful full-workspace peak is still unknown.

Compose measurements additionally need the compatible verified Compose runtime,
its health/port contract and explicit resource admission; the current multi-node
builder is not that deployment. Representative profiling needs the missing corpus.
New-server SDK provenance/release acceptance and HA/storage/power-loss tests remain
open. This closes the local pinned-Ruby runtime blocker only. Publication hold remains.
