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
store = CatalogGeneration.new(api: api, directory: '/data/catalog-journal',
                              expected_suppliers: %w[Acme Beta])
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
An empty offers list withdraws that supplier's previous offers only as part of an
explicitly complete snapshot. Availability remains dated catalog information.
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

The example is bounded to 10,000 offers because its audit uses the adapter's tested
offset boundary. Audit pages of 100 and a single serialized writer are test choices,
not benchmark-derived recommendations. There is no cursor, distributed CAS, lease,
or garbage collection contract here. This example's dynamic mapping preserves raw
SMILES, salts and stereochemical text; it does **not** configure native chemistry
preparation. The separate native smoke tests the chemistry query mapping. Integrating
both mappings and proving refresh safety under node/power loss remain release gates.

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
