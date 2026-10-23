# Pull-request Rust dependency security

GitHub's dependency-review API rejects fork repositories (HTTP 403), including
this public fork. The `Dependency Review / dependency-review` job therefore uses
cargo-audit 0.22.2, downloaded from its official release and SHA-256 verified.
It fetches RustSec once and audits the merge-base and exact PR-head Cargo.lock
against that same database revision. It never builds or resolves the PR project.
This preserves a dependency-change check, not a full release-security approval.

New `(advisory ID, package, version, source)` matches for vulnerabilities **or
unsoundness** fail. Existing matches remain visible security debt. Network,
missing lockfile, scanner, malformed report and inconsistent exit-status failures
fail closed. No advisory ignores, platform filters or severity thresholds apply.
The job summary lists every current match; artifacts retain both full reports,
lockfile hashes, compared commit IDs and database revision for 14 days.
Maintenance and notice warnings remain visible but do not block. Yank checking
is disabled: it is not vulnerability detection and requires registry access.

This differs from GitHub's advisory graph: RustSec-only coverage can miss GHSA-only
advisories; crates.io advisories do not automatically match Git forks. Native
RDKit/TensorFlow/system libraries, Ruby/npm dependencies, newly activated features
or exposure paths of already-present packages are outside this lockfile delta.
A disappearing match is `no_longer_reported`, not evidence of a security fix.
The exact PR head is checked; changes introduced only by a future merge resolution
must be checked on the revised branch. Unchanged dependency debt and release
exposure require separate review and remediation, not a green PR delta verdict.

## Initial evidence and inherited exceptions

At head `0dddfb071e2d7f28fa09eb01f94d05cd6dabbf0f`, compared with merge base
`6bf1e29cdbf03409287b2f7d0e59a4c19534d8fa`, RustSec revision
`999ec89d5d3f10f20be14750ec8c2d8b44e0ac9b` reports 31 vulnerability matches and
5 unsoundness matches in each lockfile: **zero introduced, 36 existing matches**.
These are package/version/advisory matches, not 36 distinct vulnerabilities or
proof of exploitability. Findings include rustls/webpki, quinn-proto, h2,
quick-xml, zip, protobuf, azure_core, domain, RSA, rand, lru and event-listener.
This change does not fix that inherited debt or approve release.

The old GHSA exceptions are historical context, not active suppressions here:

- GHSA-c38w-74pg-36hr and GHSA-4grx-2x9w-596c map to RUSTSEC-2023-0071
  (RSA timing). The old comment identified Google Storage usage; reassess actual
  private-key exposure before accepting risk. RustSec still reports the present rsa 0.9.10.
- GHSA-cq8v-f236-94qc maps to RUSTSEC-2026-0097 (rand logging). The affected
  locked version is 0.7.3, not patched 0.8.6; the inherited no-log-feature rationale
  is not a blanket exemption for future dependency changes.
- GHSA-2f9f-gq7v-9h6m (thrift 0.17) has no matching RustSec entry in this snapshot.
  The former trusted-input rationale is not validated by this scanner; input
  buffer limits do not establish bounds on inner allocations.

## Local verification

Run `python3 -m unittest discover -s quickwit/scripts/ci -p test_dependency_audit.py`.
The script accepts explicit scanner/database/base-lock/head-lock/output paths;
see the workflow for exact invocation. Seven unit tests exercise identities,
unsoundness, delta decisions, full evidence, filters, scanner status/errors and
database mutation. Real pinned-scanner checks passed for identical current
locks (exit 0), empty locks (0), introduced findings (1), and missing lockfile (2).
