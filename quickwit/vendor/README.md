# Narrow LRU panic-safety backports

These two copies retain upstream package names, versions, manifests, dependency
requirements and MIT licensing. Tantivy and Chitchat remain at their existing
revisions. Only the `pop()` implementation in each `src/lib.rs` changes: detach
the removed node before reclaiming its allocation or dropping its key. This is
the operation-ordering repair from upstream LRU PR 238 / release 0.18.2 for
RUSTSEC-2026-0253, inspected in cached 0.18.5 source. The unrelated
`get_or_insert_mut_ref` lifetime correction is not part of this backport.

Original crates.io archives:

| Version | Archive SHA-256 |
|---|---|
| 0.16.4 | `7f66e8d5d03f609abc3a39e6f08e4164ebf1447a732906d39eb9b99b7919ef39` |
| 0.17.0 | `0e0b564323a0fb6d54b864f625ae139de9612e27edb944dda37c109f05aac531` |

Both original `src/lib.rs` files have SHA-256
`e916c9f5996d5ad892dc86e008fe72d47c0d182e3638c09a9a7630c26b77ed81`.
Both patched files have SHA-256
`b1b82f43d3998db4c3c9906ed6f80ba4b886a9cac793b30dca60ec239d1a21bc`.
The reproducible source transformation is in `scripts/ci/lru_backport_probe.py`.
The seven retained files per package come directly from the verified archive;
only the source transformation above is applied. Upstream CI and gitignore files
are omitted. The retained `.cargo_vcs_info.json` describes the original source,
not these local modifications.

`lru-provenance.json` inventories every retained file and its hash, original
registry identity and archive checksum. Audit validation must reject altered or
additional package files and symlinks. A separate registry-identity projection
keeps the two original advisory rows visible; raw Cargo audit cannot establish
remediation merely because a path dependency is no longer matched as a registry
package. No advisory is suppressed or subtracted for these backports.

Two focused regression tests run against both actual vendor paths with default
Hashbrown and std-map features. The panic regression asserts unwinding, key
removal, length/order, actual eviction and subsequent operations. Upstream library
tests pass 52 with default features and 51 with std-map for each version; the
default-only test is test_with_hasher. Separate locked test dependencies live
under scripts/ci/lru-backport-locks and CI tests isolated copies. Parent
compatibility remains a separate gate. The workspace
excludes these packages from membership so their isolated tests do not acquire
Quickwit's workspace-wide native build requirements. Their MIT source headers
are preserved and narrowly excluded from Quickwit's Apache-header check.

Locked all-feature metadata must preserve every resolved package dependency and
feature, with only these two source identity substitutions. Existing production
index reopen/restart and old/new Chitchat peer tests remain mandatory before
claiming compatibility. The full dependency preflight remains blocked.
