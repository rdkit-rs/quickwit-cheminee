# Dependency remediation preflight — incomplete

Authorized 2026-10-19 before the larger MOSES/Garage study. No suppression,
feature removal or scanner-source trick counts as remediation. A green PR delta
is not this preflight: require a complete supported-graph vulnerability/unsoundness
assessment and resolution of all findings, or an explicit user decision on an
unresolved case. Native chemistry, SDK, harness, backend and tooling are included.
No benchmark/optimization trial has started; trial count is zero.

## First remediation candidate

Baseline head 618e70c8; cargo-audit 0.22.2; RustSec database
999ec89d5d3f10f20be14750ec8c2d8b44e0ac9b. Full scan changes from 36 to 11 matches
(10 unique advisories), with zero introduced. This is not a clean audit.

Compatible patched updates cover domain, event-listener, h2, quinn-proto, rustls,
webpki and direct lru. AWS updates select modern HTTPS/Tokio and retain S3 SigV4a,
SSO/process credentials and the existing AWS-LC/proxy/DNS/stalled-stream behavior.
The duplicate deprecated TLS client is removed; SDK retries remain disabled in
quickwit-aws, not silently enabled by this change. Updated replay utilities remove
legacy HTTP/2 without removing replay tests.

OpenDAL 0.59.5 and reqsign updates remove vulnerable XML versions. Its new
transport API is adapted explicitly per operator, preserving verified TLS and
private-CA regression testing without global transport/trust mutation. The
production constructor gets a separate local range-read test. Profiling retains
pprof collection and the SVG endpoint, using patched Inferno directly. Folded
frames, thread labels/counts, empty profiles and writer failures have scoped tests.
The generated license inventory is refreshed using the same tool as CI.

Current validation: isolated flamegraph tests pass 3/3; an isolated OpenDAL
transport range-read passes 1/1; locked all-feature candidate metadata resolves.
The isolated transport check does not replace the repository GCS/TLS tests.
Current-head full CI, GCS runtime tests and final independent implementation
acceptance are pending. Native/full-workspace local builds are not admitted:
workspace free space is about 681 MiB against a 640 MiB emergency floor. Small
isolated checks use the separate /tmp filesystem. No unrelated data was deleted.

## Remaining Cargo findings and decisions

| Parent | Remaining advisory IDs | Required work / alternatives |
|---|---|---|
| Legacy Azure 0.21 | RUSTSEC-2026-0275, -0194, -0195, -0097 | Migrate to maintained Azure SDK with access-key, environment/managed identity, SAS/Azurite compatibility, per-part Content-MD5 and ordered commit preserved. OpenDAL Azblob is an alternative only with those integrity/auth guarantees; its signing path also introduces RSA. A token-only substitution is unacceptable. |
| TensorFlow binding | RUSTSEC-2024-0437; RUSTSEC-2026-0367, -0368, -0369 | Current upstream still pins protobuf 2.27.1 and ZIP 0.6. Either maintain a narrowly patched binding or a reviewed small C API bridge retaining SavedModel loading, named operations and exact ranking/numerical parity. Runtime linking alone does not remove protobuf. ZIP affected-API reachability is unproven but the finding is not suppressed. Native TensorFlow itself needs separate audit. |
| Tantivy / Chitchat LRU | RUSTSEC-2026-0253, two versions | Prefer minimal parent dependency patches, with persisted-index/restart and cluster interoperability tests. Tantivy main changes codecs/index dependencies; Chitchat 0.13 adds protocol envelopes and changes defaults. Do not upgrade blindly or hide registry matching with a source switch. |
| RSA: Pulsar/OpenID, reqsign/GCS, SQLx MySQL | RUSTSEC-2023-0071 | No patched RSA release, including current prereleases. Preserve OAuth2 discovery/issuer validation/refresh while removing its dependency path; replace private signing with an established constant-time backend; inspect/remove only genuinely unused MySQL feature edges. Maintained narrow parent patches versus larger adapter replacements require an explicit ownership/architecture decision. |

Independent Astra/max review identified these as substantive changes, not safe
lockfile-only fixes. No upstream repository, package, credentials or release has
been created. Preserve the current functionality until the replacement is
implemented and its regression/recovery evidence is accepted.

## Wider graph

SDK Ruby lock, Python REST/CLI/bootstrap locks, chemistry oracle/client tooling,
OpenAPI Generator shaded dependencies, native RDKit/TensorFlow and runtime OS
packages must be inventoried. Direct-package lookups alone cannot certify these
transitive graphs. Garage is not yet selected/installed and remains an admission
prerequisite. Findings and network/coverage limitations are retained under
/workspace/recovery/dependency-remediation-2026-10-19. Python findings are being
remediated separately within this preflight; native/SDK/tooling coverage is open.

## Ruby client remediation

Faraday is pinned to 2.14.3 and the generated gem dependency minimum matches,
addressing GHSA-33mh-2634-fwr2, GHSA-5rv5-xj5j-3484 and
GHSA-98m9-hrrm-r99r. The pinned generator was actually rerun against the retained
schema and its original server revision
8009925c6b9757edc77ef8e6111309503028e7c5. Only the generated gemspec and provenance
changed. This does not claim a new schema export from the final server head.
The installed candidate passes 24 wire tests / 420 assertions and 9 loaded-JSON
guard tests / 10 assertions, with no failures, errors or skips.

The generator itself remains an open tooling finding: the 7.11.0 shaded JAR
contains affected Maven components. Regeneration reproducibility is not evidence
that its dependency graph is safe. Native RDKit, TensorFlow and OS runtime coverage
also remains incomplete.

## Decision sequence

1. Complete the expanded dependency assessment before admitting any benchmark;
   retain the publication hold and disk floor. The PR delta check alone is insufficient.
2. Apply compatible upstream fixes and explicit transport adaptation; preserve
   authentication, verification, SDK retry policy and profiling behavior.
3. Preserve the generated Ruby shipping surface and regenerate its minimum patched
   HTTP dependency from the template, retaining the actual schema provenance.
4. Remove executed bootstrap tools with affected bundled dependencies only when a
   hash-bound wheel installation path preserves the existing test lock and entrypoints.
5. Keep architectural and uncovered native/tooling cases open. Choose and validate
   their replacements before benchmark admission; no source change or advisory
   exclusion counts as a security fix.

The compact [evidence record](dependency-preflight-evidence.json) binds the Cargo
comparison to the candidate lock hash and records scoped test outcomes. Full logs
are retained in the recovery directory. CI and gate status must be checked against
the final commit, not inferred from the earlier green head.
