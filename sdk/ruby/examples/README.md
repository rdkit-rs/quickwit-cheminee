# Catalog generation experiment

`catalog_generation.rb` is importer application code outside the generated gem. It
uses the generated `DefaultApi` plus the opt-in `ExactSearch` completeness adapter.
The journal runs on one host, serializes cooperating writers with `flock`, and
fsyncs journal/pointer replacements. It is not a server-side write fence, distributed
activation service, or an exactly-once ingestion API. Power-loss and filesystem
corruption have not been tested. Use a private journal directory on persistent
storage; its parent directory must already exist. The journal contains catalog data
and is created with restrictive permissions; do not attach it to routine logs.

```ruby
require_relative 'catalog_generation'
store = CatalogGeneration.create(api: api, directory: '/data/catalog-journal',
                              expected_suppliers: %w[Acme Beta])
# On restart use CatalogGeneration.new with the same arguments; never create again.
# Read a frozen complete snapshot, never a partially successful scraper run.
generation = store.stage(JSON.parse(File.read('complete-snapshot.json')))
store.ingest(generation, batch_id: 'batch-0001', record_ids: [1, 2, 3])
store.promote(generation)
# Readers resolve once and pin this concrete generation through all pages.
selected = store.pointer
search = QuickwitCheminee::ExactSearch.new(api: api, generation: selected.fetch('active'))
search.search(query: {term: {'supplier' => 'Acme'}}, limit: 20)
# Operator-requested rollback uses the expected activation revision.
store.rollback(expected_revision: selected.fetch('revision'))
```

Manifest shape:

```json
{"suppliers":["Acme","Beta"],"snapshots":[
  {"supplier":"Acme","sequence":1,"complete":true,"observed_at":"2026-10-16T12:00:00Z",
   "offers":[{"offer_id":"a1","record_id":1,"smiles":"C[C@H](O)Cl","price":10}]},
  {"supplier":"Beta","sequence":1,"complete":true,"observed_at":"2026-10-16T12:00:00Z",
   "offers":[{"offer_id":"b1","record_id":3,"smiles":"C[C@H](O)Cl","price":15}]}
]}
```

Supplier coverage is trusted configuration, persisted separately and checked on
restart. **Every supplier must advance its sequence on each complete refresh**;
this example deliberately does not implement independent supplier patch updates.
An empty offers list is rejected even when marked complete. After separately
reviewing the scrape, explicitly opt in with `stage(manifest,
allow_empty_suppliers: ['Acme'])` to withdraw that supplier's previous offers.
Large nonempty shrink thresholds need supplier-specific review; no measured shrink
policy or automated anomaly detection is implemented. Conflicting offer-level
supplier or observation times are rejected; observation times retain nanoseconds. Availability remains dated catalog information.
Two suppliers can offer the same structure; supplier/offer identity stays separate
from structure data. The durable identity registry prevents changing or recycling
record IDs, including after withdrawal or rollback. It grows with all identities
ever reserved and has no scale/memory qualification yet.

A batch ID and digest are fsynced before dispatch. Repeating an acknowledged batch
returns the saved acknowledgement without HTTP. An uncertain, rejected, interrupted,
or inconsistent batch quarantines the staging generation. Start a fresh generation
from the frozen complete snapshot; do not retry into the uncertain one. Other writers
must never append to a sealed or published generation. The server does not enforce
this assumption, including after restart.

Promotion checks acknowledged membership, exact published count, all record IDs,
and all stored content before comparing the activation revision. The durable pointer
is authoritative if a process exits after pointer fsync. Rollback re-audits a retained
generation and preserves source high-water sequences. No automatic cleanup is
provided: retain active, rollback and reader-pinned generations. The smoke script
alone deletes its own disposable indexes.

The audit partitions the full u64 `record_id` domain into disjoint inclusive ranges
containing at most 10,000 expected offers each. Ranges include gaps, zero and u64::MAX;
sparse IDs above JavaScript's exact-integer range are never converted to floats.
Each partition has an exact strict count, pages of at most 100, a stable exact total
on every page, and complete ID/source comparison. Global exact counts bracket the
audit. The unchanged `ExactSearch` adapter still limits `from + size` to 10,000 per
request and rejects partial or malformed responses. These ranges provide no cursor
or snapshot isolation; the immutable-generation/sole-writer assumption still applies.

This removes the previous 10,000-offer staging cap; it does not qualify the journal
for a large catalog. The full manifest and identity registry remain in memory, and
the full generation journal is rewritten for each batch. Batch membership uses a
bounded selected-ID set instead of scanning an ID array for each record. Page size,
batch size and serialized writes are acceptance choices, not measured tuning advice.
There is no distributed CAS, lease or garbage collection contract.

## Explicit native preparation profile

The default remains the legacy dynamic raw-source mapping. Existing legacy journals
open without migration. Native preparation must be selected when creating a fresh
journal, with the same configuration supplied on every open:

```ruby
native = {
  spec: CatalogGeneration::NativePreparation::SPEC,
  prepared_smiles_field: 'prepared_smiles'
}
store = CatalogGeneration.create(api: api, directory: '/data/native-catalog-journal',
  expected_suppliers: %w[Acme Beta], native_preparation: native,
  index_heap_size_bytes: 32 * 1024 * 1024)
```

This narrow profile uses the actual mapper's canonical Cheminee preparation with
RDKit 2026.09.1, `descriptor_v1: true`, and `descriptor_layout: nested`. It maps raw
`smiles` separately from stored, fast prepared SMILES; the contract-hashed Morgan
field uses hex input/output, Pattern uses base64, and all 43 numeric descriptors
and other descriptor values are stored. A matching `descriptor-v1` server build,
RDKit libraries and model assets are required. The importer needs no local chemistry
runtime or external preprocessing. Raw offers alone enter ingestion; callers cannot
supply any derived fields. Original supplier/offer identity and provenance remain
separate from normalized structures.

The native audit compares every original offer field exactly and validates the
complete declared derived structure: prepared SMILES presence, fingerprint encodings
and widths, descriptor names/numeric types, scaffold IDs and cluster range. It does
**not** prove that well-shaped derived values are chemically correct. The separate
acceptance oracle below checks values. Nested source arrays do not imply correlated
array-element query semantics.

The profile, native specification, prepared field and optional index heap size are
pinned in both scope and generation journals. Changing them requires a fresh journal
and generations; opening an existing journal with different settings fails. The
32 MiB heap above is a bounded acceptance parameter, not measured production sizing.
Omitting `index_heap_size_bytes` preserves the server default. `verify_active` audits
the selected active generation without changing the pointer and returns that pointer.

`catalog_generation_smoke.rb` uses real HTTP and synthetic offers. It injects lost
acknowledgements after actual ingestion, mixed rejects, equal-count duplicate/missing
rows, process exit before dispatch and after pointer fsync, stale revisions, and
rollback. These are functional checks, not durability or performance measurements.

## Recovery boundaries checked without an indexer

Run `ruby sdk/ruby/examples/catalog_generation_test.rb` with the installed gem.
It uses real private journal files, process exits and competing local publishers,
with a fake peer whose acceptance/call ledger is shared across child processes.
No server or indexing heap is needed. This validates importer recovery decisions;
it does not establish server persistence, chemistry correctness or power-loss safety.

Also run `catalog_partitioned_audit_test.rb` and `catalog_native_preparation_test.rb`
from this directory. Their fake wire peer covers the exact partition edge, 10,001
sparse u64 IDs, duplicate/missing/extra/altered records, strict response failures,
native output shape, profile mismatch, legacy journals, refresh and rollback. These
tests are importer-policy evidence only; they are not real-server or scale evidence.

- A process exit after sealing but before pointer replacement leaves the old
  pointer active. Recovery can audit and publish if the base revision still matches.
- An exit after the pointer save makes that pointer authoritative. Repeating
  promotion finalizes local state without another ingest or revision increment.
  If another generation has since won, the delayed promotion cannot replace it.
- An exit after the durable ingest intent, including after the peer accepted the
  rows but before acknowledgement, quarantines the generation on recovery. The
  importer does not guess whether dispatch happened or blindly replay the batch.
  Uncertainty in one batch also prevents sending another, disjoint batch.
- An acknowledgement saved before interruption can be returned from the journal
  without HTTP. A failed acknowledgement save quarantines even if the peer accepted.
- Two publishers sharing this journal serialize through the same lock; only one
  generation based on a given revision can win. Rollback preserves the source
  high-water marks, and partial or stale snapshots leave the active pointer alone.
  A rollback interrupted after pointer save rejects a retry using the old revision,
  rather than toggling the pointer twice.

All writers and readers must honor the application protocol. A direct server writer
can still alter an audited generation, and a journal directory must not be replaced
while writers hold its lock. Pointer recovery assumes readable, intact local files;
fsync calls alone do not prove power-loss or filesystem-corruption durability.

Stale staging indexes are not automatically deleted or globally fenced: the local
revision check blocks their promotion. Cooperating callers must retain uncertain
indexes for reconciliation and must not bypass this journal to rewrite published
content. An uncertain create outcome is quarantined; recovery uses a fresh random
generation ID rather than assuming the previous create failed.

Initialization is explicit and exclusive: `CatalogGeneration.create` requires a
nonexistent directory. Opening with `.new` and every subsequent operation require
the lock, scope, active pointer and identity registry; missing files never reset
high-water marks or ID reservations. Restore a verified journal backup and reconcile
server generations after loss; do not reinitialize the same catalog. Content
corruption and replacement of intact-looking files are not detected by checksums.
Audits enumerate by `record_id` only, avoiding merge-sensitive BM25 score ordering.

Scraper JSON strings must be valid UTF-8. JSON 3.1 rejects multibyte UTF-8 bytes
still tagged `ASCII-8BIT`, before staging creates a server index. Explicitly decode
using the known source encoding and validate first; never silently replace or drop
invalid bytes. See the SDK README for safe conversion examples.

## Native HTTP acceptance harness

`catalog_native_smoke.rb` sends 10,001 synthetic offers repeating the 20 small
structures in `catalog_native_fixture.ndjson`, then refreshes to 10,000 offers with
one withdrawal and a price change and rolls back. It exercises both sides of the
10,000-result partition edge, sparse IDs above 2^53, u64::MAX, retained identity
reservations and sequence high-water checks. It has a ten-minute phase deadline,
200-row batches, and a pinned 32 MiB index heap. It validates code is loaded from
the installed gem and checks loaded JSON provenance. No real supplier data is used.

Generate the expected values with the existing `descriptor_audit` example, built
from the same source using `--features descriptor-v1`:

```sh
descriptor_audit < sdk/ruby/examples/catalog_native_fixture.ndjson > /tmp/catalog-oracle.ndjson
# Use the candidate_version from the paired runtime manifest and its installed gem.
export SDK_EXPECTED_VERSION='candidate-version-from-runtime-manifest'
export SDK_INSTALL_ROOT=/absolute/path/to/isolated-gem-install
export GEM_PATH="$SDK_INSTALL_ROOT:$(ruby -e 'puts Gem.path.join(":")')"
SDK_SMOKE_HOST=127.0.0.1:7280 \
CATALOG_NATIVE_ORACLE=/tmp/catalog-oracle.ndjson \
CATALOG_NATIVE_STATE=/tmp/catalog-native-acceptance \
ruby sdk/ruby/examples/catalog_native_smoke.rb
```

The state directory must not exist and its parent must exist. The harness leaves its
synthetic indexes and private journal for its runner to retain or clean up. After a
graceful server restart using the same data, repeat with `CATALOG_NATIVE_PHASE=verify`
to check the saved pointer, all active records, derived values and query results.
After a runner verifies a backup and restores both server data and the full journal
to fresh locations, use `CATALOG_NATIVE_PHASE=restored` and the restored state path.
That phase verifies the receipt, explicitly rolls back to the retained refreshed
generation, and checks its content, identity reservations and unchanged high-water.
The Ruby harness does not itself create or validate the backup.

The CLI oracle shares native preparation code with the server, so its 20-structure
comparison proves mapping/transport agreement. The first eight structures also
match the retained independent Cheminee golden fixture. Integer descriptors and
fingerprints compare exactly; floating descriptors permit at most one ULP, matching
the existing descriptor REST acceptance's JSON round-trip allowance. Small facade
queries check curated identity/substructure memberships and similarity scores
computed directly from retained Cheminee golden fingerprint bits. These are explicit
truth sources, not expectations copied from a server query response.

Writing this harness or passing fake-peer tests does not establish a native HTTP
pass. Its result must come from an actual native server and matching installed gem.
The 10,001 repeated synthetic offers are not a representative 100k catalog test,
kind/object-store evidence, a performance result, HA, or node/power-loss durability.
