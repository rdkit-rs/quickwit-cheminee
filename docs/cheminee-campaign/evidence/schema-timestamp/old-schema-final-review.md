# Independent final review: bounded old-schema chemistry handling

Reviewed 2026-10-16 against the working-tree patch over `c15204119d29285511ac1a5563732a6a714a3315`. No source edits were made by this reviewer. This follows `old-schema-design.md` and closes the specific follow-ups in `old-schema-implementation-review.md` for the scope below.

**Approved for the tested implementation scope:** current chemistry declarations/inputs stay eager, ordinary candidates use physical field IDs, and incompatible old chemistry fields fail only when the segment has a live candidate requiring verification. No remaining implementation blocker was found in that bounded path. This does not approve complete relevance semantics, arbitrary schema migration, the timestamp-pruning patch, or campaign/release readiness.

## Implementation and boundary tests

The separate current `chemistry_schema` remains confined to the three chemistry constructors; physical schema resolution and ordinary warmups are unchanged in purpose. Physical fingerprint and graph contract checks run after candidate construction, deletion filtering and the empty-domain check. Graph retains its fingerprint spec and verifies exact prepared text/stored/fast/raw requirements. Candidate errors, eager graph matcher setup, per-value failures and strict current-schema checks remain visible.

Chemistry warmup filtering uses pure schema predicates and does not suppress I/O errors. Incompatible columns are omitted from warmup and checked again if a live candidate needs them. Ordinary absent term-set and formerly non-fast range warmups now follow existing disabled-validation compilation semantics; their current-schema validation remains strict. No logical field-ID leakage was found.

The expanded native mapper matrix now covers missing/wrong-type/non-fast fingerprints; missing/non-fast/nonraw/wrong-type/unstored prepared fields; dynamic-only fields; and a populated dynamic prepared-field trap with a valid exact fingerprint. It asserts exact chemistry warmup membership, retained physical candidate postings, deliberately mismatched field ordinals, empty/live outcomes and eager malformed inputs. The populated dynamic variant fixes the earlier vacuous fixture. The separate ordinary term-set/range sentinels pass. The old core error-message oracle was intentionally changed to the earlier physical-contract failure, retaining its empty/deleted-only/nested-error checks.

I independently reran the retained final compiled binaries:

- `old-schema-independent-mapper-final.log`: **5 mapper chemistry tests passed**.
- `old-schema-independent-core-final.log`: **7 core composable tests passed**, including deleted invalid values, nested candidate errors and eager failing matcher setup.

These are independent test executions, not independent compilations. `old-schema-final-boundaries2.log` records the final native mapper build/run after the populated dynamic variant. The earlier full mapper suite had 231 passes before those last test extensions. `git diff --check` passed.

## Native HTTP evidence

`schema-timestamp-fixed-final.json` records 57 passing checks. **39 concern this old-schema review; 18 concern the separately reviewed timestamp work.** I independently revalidated every schema response against fixture-derived expectations, rather than accepting the report's status field. Results and source hashes are retained in `old-schema-independent-final-evidence.json`.

The harness uses a real mapping update, two distinct mapping UIDs, one live old row and one current row, no merge, untagged `family`, and no timestamp selection bounds. The final run retains the same two split IDs as the old-binary baseline. Its plain match-all control asserts IDs `[1,2]`, exact total two and both successful shards.

For Tanimoto, fingerprint containment and molecular graph, explicit candidates and necessary sibling filters in both clause orders return the expected exact counts and ID `[2]`; empty candidates return exact zero. Count and hit requests assert both splits succeeded, zero failed/skipped shards and no timeout. Live-old, unbounded and timestamp-sorted exact-count requests return strict HTTP 500 with the requested physical-contract cause and the old split ID. Malformed chemical inputs return HTTP 400 with their input-validation cause despite absent candidates. These stronger status/cause/shard oracles close the earlier harness gaps.

The old-binary `schema-timestamp-baseline5.json` genuinely reproduces **15 old-schema failures** for those irrelevant old splits, plus two separate timestamp failures. The final harness has additional sibling-order/count cases and stricter oracles, so its request count and probe hash differ from that baseline.

At inspection, the actual retained binary and current probe bytes match the final report:

- Native binary SHA-256: `5f92e5079f676e7bd6cb21df2e89e3334d8c976abbed69c17d058cb72c7e048d`
- Probe SHA-256: `2949f97a09c784d221c3a1b12f08799216d14009686580b7e3518d519cc80328`
- Final HTTP report SHA-256: `c1522e0005e50ec7cc6aee189ada0f1fd47685bd7714b1a461205326f58ee725`

The native build status records exit zero without a disk-headroom stop. This is working-tree/binary attribution, not a claim that the runtime was built from a new committed tip. I inspected the retained HTTP execution and independently checked its responses; I did not execute that HTTP harness again.

## Limits retained

HTTP coverage here is the missing-chemistry-field migration on one native worker. Other incompatible physical variants have mapper/scorer and warmup-metadata coverage; they have not all been exercised through native HTTP. Count/hit pairs reuse the same candidate query but do not establish general cache or restart behavior.

Compatible-but-damaged column I/O can still occur during segment opening or warmup before candidate emptiness is known. General OR relevance, arbitrary ordinary-field evolution, broad NOT/should/MSM combinations on evolved schemas, distributed failure/restart, production migration/durability/HA, full workspace validation and publication remain separate gates. The core seven-test subset uses controlled verification fixtures; it is not an exhaustive chemistry oracle. No broader approval follows from this review.
