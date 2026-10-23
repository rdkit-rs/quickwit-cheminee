Independent review of the importer-side catalog generation example

Reviewed 2026-10-16 in `/workspace/quickwit-cheminee-pr3-inspection`, with repository HEAD `8009925c6b9757edc77ef8e6111309503028e7c5`. The example and smoke harness were uncommitted at review. No source files were edited by this reviewer.

Approve the current design as a bounded, single-host example with one cooperating writer protocol. The previously identified identity, batch-ID type, and interrupted-publication defects are resolved. I found no remaining blocking source defect within that stated scope. This does not approve distributed operation, hardware durability, a server-enforced seal, exactly-once ingestion, or chemistry validation of these documents.

The reviewed implementation is `sdk/ruby/examples/catalog_generation.rb`; the real HTTP harness is `catalog_generation_smoke.rb` beside it. The important protections are coordinated correctly:

- Supplier coverage comes from separately supplied trusted configuration, persisted in `scope.json`. Supplier names are copied and frozen. Every refresh must contain exactly that scope and a complete, strictly newer snapshot for each supplier. A successful scrape request is not evidence that its snapshot is complete.
- Each offer becomes one document. `(supplier, offer_id)` and numeric `record_id` are reserved bidirectionally before index creation. Reservations survive failed staging, withdrawals, and rollback. The JSON-encoded identity pair avoids ambiguous concatenation. Structure, salts, and stereochemistry are not used as offer identity.
- The batch ledger copies record IDs before validating them as u64 Integers, closing the Ruby Integer/Float equality mismatch and retaining a stable membership list across the HTTP wait. Acknowledged duplicate batch IDs return the journal receipt without another HTTP write; different contents or overlapping IDs are rejected.
- The generation-wide in-flight check prevents a restarted importer from continuing with a different batch after an uncertain request. The in-flight entry is fsynced before dispatch. Partial, missing, or unknown acceptance quarantines the generation. The code never automatically retries that append. Bounded quarantine reasons are now retained, including exceptions in create/ingest.
- Promotion requires complete acknowledged membership and a strict count-and-content audit through `ExactSearch`. It keeps the sole-writer lock for the audit and pointer change. Match-all scoring with unique record-ID ordering makes the audit comparison deterministic; count alone cannot pass a duplicate/missing-content replacement.
- Sealing is persisted before publishing `active.json`. That pointer atomically carries revision, active/previous generations, and source high-water marks. An already-active sealed/promoted generation is reconciled before another audit, so a retry after pointer publication neither increments revision again nor quarantines an already-published generation on a subsequent audit failure.
- Rollback audits the retained target, compares the expected pointer revision, increments revision, and preserves the highest source sequences. Identity reservations also remain. A rollback does not reopen the importer to an old snapshot.

Crash behavior is appropriately conservative:

| Interruption | Recovery behavior |
| --- | --- |
| Identity reservation saved, before index creation | Reserved IDs may remain unused. Reuse for a different offer remains forbidden. |
| Create request outcome uncertain | The creating/quarantined generation cannot accept ingestion or publication; a fresh generation is required. |
| In-flight journal saved, before dispatch or before durable acknowledgement | Any later ingest/promote detects uncertainty and quarantines; no replay. The smoke explicitly exits before dispatch. |
| Successful audit and sealed journal, before active pointer | The generation is closed to ingestion; promotion may retry its audit and revision check. |
| Active pointer fsynced, before promoted status | The pointer is authoritative. Recovery reconciles status idempotently. The smoke explicitly exits at this boundary. |
| Failed revision comparison | The active pointer and high-water remain unchanged; the stale candidate cannot become active through another attempt. |

File updates use a new private temporary file, file fsync, rename, and containing-directory fsync. Creating the journal directory also fsyncs its existing parent. This is the expected ordering for the stated filesystem assumptions. Process-exit injection does not establish behavior under power loss, corrupt storage, lost files, failed disks, or restoring an inconsistent backup.

Evidence inspected directly:

- `/workspace/recovery/catalog-generation-final3-smoke.log`: `status: passed`, 19 named checks, including stable identities, float rejection, acknowledgement loss, partial rejection, equal-count duplicate/missing contents, interrupted ingest, interrupted pointer publication, revision conflicts, and rollback high-water retention.
- `/workspace/recovery/catalog-generation-final4-smoke.log`: `status: passed`, 21 named checks. This adds a 121-document audit across two pages and a complete empty-catalog publication followed by rollback. These are checks, not a count of distinct HTTP requests, and the two runs must not be summed.
- I inspected the harness that produces those outcomes; I did not independently rerun its mutating HTTP workload. The original logs do not embed source/gem/server hashes. The source received small defensive ownership/diagnostic edits during review, so a retained final run should carry the final artifact hashes and execution identity. The source-level conclusions above include the final copy-before-validation change.

Final inspected SHA256 values: example `9103b337f68ed481c0d9de76e24fd3b5a91660d217d1a56c0a7cdfaaaa07a352`; harness `c2f776790be2d3ad759a6904c013b46eda6b30a749b9abc38d3ac7fee90e2b6e`; final4 log `18fc1c838b1a4d0a52e33db467375a1c70dec2aab1fea88c5ae800da4c7cdab3`. The checked-in candidate provenance names gem `0.9.1.pre.contract1` and server revision `8009925c6b9757edc77ef8e6111309503028e7c5`; that declaration alone is not runtime binary attestation.

Keep these limits explicit in the accompanying instructions:

- This is a fixed-supplier, full-catalog refresh protocol. Every supplier must advance its sequence on every refresh; callers must not manufacture a new sequence or completeness flag to reuse an incomplete scrape. Independent supplier refreshes require a separate composition contract.
- All mutations must use this same journal on one host and a filesystem supporting the required locking/fsync semantics. A second journal, direct API writer, index recreation, or external deletion defeats the cooperative seal. The example is outside the generated gem and installs no server alias or write fence.
- Readers should resolve the active pointer once and pin that concrete generation for their operation. The 10,000-document audit ceiling is a deliberate safety boundary, not a performance or stable-cursor claim. The audit keeps the complete catalog in memory, and historical identity reservations grow over time.
- These documents use a small dynamic mapping and merely require nonempty SMILES text. Successful publication proves the checked source contents and importer protocol, not chemical validity, native preparation, graph/fingerprint mapping, or availability of live stock.
- The journal directory is private persistent state, not a disposable cache. Source completeness, registry administration, retention/cleanup, credential controls, backup/restore, HA, and production operational policy remain outside this example.

Useful later regression additions are a disjoint new batch after an in-flight interruption, missing/changed trusted supplier scope across restart, missing acknowledgement counts, and exit after seal but before pointer. The existing control flow covers these conservatively by inspection; their absence from the HTTP smoke is not a reason to claim them exercised.
