# Shared chemistry methods

## Workload and contract

The corpus selects 100,000 distinct source SMILES from MOSES `molsets==0.3.1`:
1,584,663 train, 176,074 test and 176,225 scaffold-test rows. Sort by
`SHA256(b'tantivy-rdkit-compression-v1\0' + smiles.encode())`, then source-set and
one-based source row, and take the first 100,000. IDs are 1 through 100,000.
The sample includes 81,777 train, 9,165 test and 9,058 scaffold-test rows.
It contains 99,989 distinct normalized structures; duplicate structures are not
duplicate record IDs. This curated leadlike corpus does not represent arbitrary
salts, invalid molecules or polymers.

The flat `descriptor_v1` contract has normalized SMILES, 43 numeric descriptors,
Pattern and Morgan fingerprints, scaffold IDs, learned similarity-cluster IDs
and searchable metadata. Normalization is fragment-parent (`skipStandardize=true`)
then canonical tautomer then Cheminee custom neutralization. Morgan is radius 3,
2,048 bits, LSB0, without chirality or feature invariants. Neither learned fields
nor validation may be silently omitted to improve throughput.

Cheminee has 48 fields. Quickwit adds its native graph/scoring fast fields,
`record_id` and an input-only SMILES field. Flat numeric descriptors are indexed,
not stored, with only `exactmw` fast. JSON dotted-path expansion is enabled.
Numeric fieldnorm and text-token-length policies differ; see experiment 001's
source report. Nested experiment 004 intentionally changes descriptor storage
and fast-field availability and must not be mixed into flat timing comparisons.

## Revisions and shared dependencies

| Component | Identifier |
|---|---|
| Cheminee application | `f8d31a604203392f4dfba7d9a84120100b8426b5` |
| RDKit Rust bindings | `0ae060c9cfc14626172070989fee890b16454373` |
| Ubuntu image | `sha256:f144425ff09be612d6d9ad965196e9cdc23dae1f42110a8a11a3e9a8198759f7` |
| Dynamic RDKit package | `2026.09.1+ds1-1~ubuntu26.04` |
| Rust compiler | `1.96.1` |
| TensorFlow CPU C API | `2.15.1` |
| Model crate | `cheminee-similarity-model 0.1.6` |
| MOSES source | `dd7ed6ab38e23afd3ef5371d67939a1760bd8599` |

TensorFlow 2.15.1 was used because the original 2.13 download failed. The model
algorithm/assets were unchanged. The homemade RDKit package is dynamically
linked. The package repository is a setup source, not measured index storage.

| Input | SHA-256 |
|---|---|
| molsets wheel | `7f4450e3ebecebe79c3a2a55950c93daddee071120daf64a163d03481e811d34` |
| RDKit development package | `47d7dcb895a4983093ccb85407ad0908a6b7c68405147f951a9a72fabf29405d` |
| RDKit runtime package | `13b43cf87b53bf290a0a5f17c6ce299d8672817d6ff38150d419d16f040b3705` |
| RDKit data package | `40a47d0c1ad5f90797db0d833bac9b0dc05c2f5914eec1aaa381c68e341bbe0c` |
| TensorFlow wheel | `54660c074d7241a503e81edfd9f5ef5af88f64051b72e2945f26318c790f2d26` |
| Model archive | `264d7b3af776382dc98e12b1e7c111e76b99a3714ca71acf427bfe63536b26d5` |
| Centroids | `5cf1ede6d2193dccd6b552dcce51b49c12cf69b28589e9f98c18311230edec65` |

## Resource and measurement boundaries

All timing comparisons use a four-core quota, 14 GiB memory, local `file://`
storage and one engine at a time. Five CPUs are visible; that does not grant
five cores of quota. Historical experiments 001/002 used Intel Xeon Platinum
8573C; recovered experiments 003 onward use AMD EPYC 9V74. Cross-environment
ratios do not isolate application changes. No cache drops or artificial load.

CPU means process user+system core-seconds, not elapsed span duration. Average
cores = CPU / wall; quota fraction = average cores / 4. Instrumented stage
values use exclusive per-thread clocks with async/worker propagation and a
common interior snapshot window. Boundary and unclassified residuals remain
explicit. Owned allocations are distinct from shared process RSS/PSS.
Concurrent query CPU is charged once per batch. Sampled peaks may miss short
spikes and must not be added across stages or runs.

All-searchable means all raw documents were accepted and a REST count barrier
returned the expected total. Setup, intentional boot idle, post-publication
lifecycle, audits and shutdown are separate. Publication completion does not
mean garbage collection is finished. Quickwit has a 32-minute obsolete-split
grace and a periodic ten-minute GC sweep. A long observation records deletion
without forcing merges; two-day split maturation prevents a permanent fixed-point
claim. Restart readback is not a power-loss durability test.

Body bytes / defined request interval is an application transfer rate including
backpressure and preparation, not network capacity. Local upload/publication is
filesystem work. Split payload, node cache, WAL and temporary files are separate.

## Recovery limits

Historical raw input was 22,021,752 bytes, SHA-256
`bcd62363cb784827752de27f361f6081056c99a7d636749f182e7b3cecc08e6a`.
Recovered raw input is 20,032,857 bytes, SHA-256
`9a63bf25bc02ba3c965bb050cd74ba1a059bc362b8fb210b8febb6a326ce2e5e`.
Molecule selection/order matches; original metadata serialization and some
query definitions were unavailable. Metadata was reconstructed consistently for
both engines. The historical isolated Cheminee lockfile was also unavailable;
the recovered lock resolves CXX 1.0.205 versus Quickwit's 1.0.204, with unchanged
Cheminee application source. These differences remain confounders across studies.
