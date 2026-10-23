# Cheminee internal pilot acceptance

Cheminee is the public chemistry product; Quickwit is its search engine. This
pilot does not replace RX's current search or establish compatibility with RX's
legacy Cheminee 0.1.52 `/v1` contract. No deployment or publication is approved by
this document. The dependency and publication holds remain in force.

## Current evidence and blockers (2026-10-23)

The historical immutable 100,000-record MOSES study exercised native chemistry
with single-node local storage. It did **not** exercise kind, an object store,
the Ruby catalog importer, backup/restore or deployment HA. Its corpus hash is
`9a63bf25bc02ba3c965bb050cd74ba1a059bc362b8fb210b8febb6a326ce2e5e`
(20,032,857 bytes); the original corpus and indexes are absent from this restored
workspace. Recover and verify them, or record a new public corpus and selection
manifest as a new study. Repeated fixture molecules are useful boundary tests,
not evidence of representative chemical diversity.

A new [MOSES preparation recipe](corpus-preparation/README.md) now reproduces
100,000 distinct raw SMILES from the checksum-pinned molsets 0.3.1 data archive.
Its synthetic offer metadata and corpus hash are new. Native chemical uniqueness,
preparation, query truth and operational acceptance still require execution in
the fresh benchmark environment; raw-string uniqueness alone does not prove them.

The requested kind/object-store acceptance has **not started**. Docker is
available, using VFS with `/var/lib/docker` on the workspace filesystem. Measured
free persistent space was 678,436,864 bytes: only 7,348,224 bytes above the
640 MiB emergency floor and below the 1 GiB reserve before allocating anything.
The executor has four CPUs and 16 GiB RAM. `/tmp` is RAM-backed and cannot provide
persistent recovery capacity. The host lacks kind and kubectl; verified current
native runtime, kind-node and object-store images are not present.

A fresh copy of this same saved environment does not resolve these constraints.
The next environment needs Docker with enough persistent backing capacity,
kind and kubectl compatible with a pinned node image, a pinned real S3-compatible
store image, the verified Cheminee image/gem pair, and immutable corpus/oracle
inputs. Preserve the source and evidence before moving. No daemon storage,
network or security changes are part of this campaign's authorization.

There is no measured sufficient total disk or RAM budget yet. Record the following
byte allowances before admitting the run; do not substitute the existing 5 GiB
workspace-build allowance for a kind budget:

| Allocation | Admission evidence |
| --- | --- |
| Images | Compressed and unpacked sizes, VFS layer duplication, kind/containerd imports |
| Runtime | Node writable layer, object-store metadata, logs, WAL and cache bounds |
| Catalog | Simultaneous active, staging and rollback generations plus indexing/merge peak |
| Recovery | Quiesced backup and a distinct empty restore destination, both retained during verification |
| Inputs | Corpus, independent truth results, journals and receipts |
| Reserve | At least 1 GiB beyond the above allowances; stop before the 640 MiB emergency floor |

Required free space is the sum of these allowances on each affected filesystem,
accounting for any shared backing store. A smaller calibration import must measure
storage amplification and peak memory before scaling; it cannot prove a linear
100k bound. Keep concurrent indexing bounded and record actual cgroup limits.
The existing 768 MiB Compose limit is a historical test parameter, not sizing for
descriptor preparation or this acceptance run. Elasticsearch coexistence remains
a separate measurement.

## Smallest disposable deployment

Use one kind node, one native Cheminee all-in-one process, one real S3-compatible
object store, and the matching generated Ruby SDK. An S3-backed file metastore
allows this bounded single-writer experiment without PostgreSQL. Enforce exactly
one metastore writer, including during replacement (`Recreate`, not overlapping
rolling updates). This topology cannot establish HA.

Keep object data, metastore, required WAL and the Ruby catalog journal on explicit
test-owned durable roots. Bind any host access to loopback. Do not expose an
unauthenticated Cheminee endpoint to a shared network. A future shared private
pilot needs an approved authenticated access boundary and secret delivery; no
credentials or ingress are created here. Record image digests, full source SHA,
model/fingerprint spec, schema hash and gem version before importing.

## Required acceptance sequence

1. Admit resources and verify inputs. Record source/image/schema/model/gem hashes,
   corpus provenance, record count and chemical uniqueness separately. Independent
   chemistry truth must not be computed solely by the same preparation function
   being tested. Preserve stereochemistry, salts and supplier/source identities.
2. Import at least 100,000 diverse records as raw SMILES through the installed Ruby
   client and native mapper. Record each batch's accepted/rejected counts and
   publication barrier. Acceptance, persistence, publication and searchability are
   separate states; an ambiguous acknowledgement quarantines the generation.
3. Audit every ID and original offer field through disjoint u64 ranges within the
   supported offset boundary. Check global and partition counts, chemistry truth,
   broad/selective/empty/novel queries, missing fields and failed leaves. Preserve
   exact-search failures. A shape-valid derived payload is not chemical truth.
4. Build generation B with additions, changed offers and withdrawals. Reject
   incomplete or stale snapshots. Verify promotion, generation-pinned reads and
   rollback without weakening identity reservations or supplier high-water marks.
   Scraped availability remains dated catalog information, not live stock.
5. Record a clean stop/start and full readback. Separately exercise a forced process
   or pod replacement with retained storage. Keep these receipts distinct; neither
   alone proves unpublished-WAL recovery or multi-node HA.
6. Quiesce writers and back up object data/metastore, complete journal and required
   WAL. Verify backup hashes. Restore into fresh empty roots without reimporting
   the corpus. Re-audit all data and chemistry, pointer, reservations and high-water
   marks; repeat rollback. Restoring only the search index is insufficient.
7. Retain phase timings, errors, cgroup memory/OOM counters, disk high-water marks,
   object inventories and reproducible commands. Report client end-to-end latency
   separately from server stages. Do not derive performance recommendations from
   a repeated tiny chemistry fixture or report clean restart as crash durability.

Routine diagnostics should contain bounded reason codes and request/import IDs,
not raw offers, structures, credentials or complete journal contents. Preserve
private debug evidence separately with explicit access. Automatic cleanup must
not remove the active, rollback or unverified-backup generation. Cleanup of the
disposable test roots happens only after the evidence and restore are verified.

## Release and promotion holds

PR #3 introduces protobuf 2.27.1 (`RUSTSEC-2024-0437`) and ZIP 0.6.6
(`RUSTSEC-2026-0367`, `-0368`, `-0369`) through the TensorFlow binding. Its October 23
dependency gate failed. PR #6's green comparison against PR #3 does not clear
those findings. Native image/gem preparation is an engineering artifact, not a
security or release approval. Keep package publication, production deployment,
HA/crash-WAL qualification and RX compatibility as explicit separate gates.
