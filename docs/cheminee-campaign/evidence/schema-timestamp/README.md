# Old physical schemas and timestamp top-hit correctness

Source commits: `2882a340` (schema/candidate boundary), `8a895900` (timestamp pruning).
Native binary SHA256 `5f92e5079f676e7bd6cb21df2e89e3334d8c976abbed69c17d058cb72c7e048d`.
Built from the working production changes before commits; subsequent mapper changes
were test-only. Native build exited0. Rust 1.96.1, RDKit 2026.09.1, Linux amd64.
This is scoped correctness evidence over synthetic fixtures, not performance/HA proof.

The retained old-binary baseline has 15 old-schema failures and 2 wrong cold top hits.
Both wrong hits had exact total 3 and zero failed shards. Its exact script is retained
with matching probe hash; the final harness adds stricter assertions and sibling cases.
The final native HTTP report passes 57 checks: 39 old-schema and 18 timestamp checks.
It checks independent IDs/counts, all expected shards, error causes and old split ID,
no timeout/early termination, and explicit timestamp sort tuples. Same physical
fixture splits are retained between baseline and replacement. Warm baseline queries
masked the two timestamp defects; cold checks are essential.

Native coverage includes 231 mapper tests before the final boundary additions, final
five mapper tests covering the expanded physical-schema matrix, seven core scorer
regressions, and five timestamp units. These overlap and are not additive unique-case
counts. Existing regression probes pass 68 selective cases and 105 assertions in 109
requests; four general count-only OR requests remain observations, not passing oracles.
Both independent Astra max reviewers approved their bounded gates; reports are retained.

Scoped native Clippy (query, mapper, search, core, with tests and warnings denied),
targeted Rust 2024 formatting, repository license/log policy and diff whitespace checks
pass. Stable rustfmt warns that nightly-only formatting settings are unavailable;
this is not a nightly whole-workspace formatting claim. Full all-features Clippy's
default TensorFlow download failed with HTTP 403. The explicit retry with existing TensorFlow 2.15.1 avoided that download, then
stopped at the 640 MiB disk guard (exit -15). Library hashes and both logs are retained.
After archiving the runtime context with file-by-file hash/mode verification, a
retry reached krb5-src 0.3.4 and failed on discarded const qualifiers under GCC 15.2.
Explicit CFLAGS=-std=gnu17 was visible in the actual compiler command but did not
resolve it. Logs/status are retained; no warning suppression was used. Neither
scoped success nor an interrupted/failed run establishes full workspace CI.
Subsequent diagnostic inspection found the existing CI wrapper
`quickwit/scripts/ci/with-krb5-c23.sh` already handles that dependency. Raw Cargo
retries bypassed it: this was an avoidable process error, not an unresolved
repository defect. The correct wrapped validation remains unrun.

Run the HTTP harness inside the trusted native builder, with a fresh work directory
and output (it owns its temporary server and synthetic indexes):

```sh
python3 tantivy-rdkit/poc/schema_timestamp.py --binary target/debug/quickwit \
  --work-dir /tmp/schema-timestamp-new --output /tmp/schema-timestamp-new.json
```

`--reuse` intentionally retains fixture indexes and starts a fresh server. The probe
never changes production catalogs. The bounded Cargo runner records command, exit,
headroom and disk samples; it terminates its own process group below 640 MiB free.
Library v4 and original source recovery remain preserved. Removed runtime/Ruby
containers were reproducible; their build context, image identity and bound gem
installation remain. The inventory explains the VFS disk constraint. No scale run,
image publication, merge or deployment occurred.

Limitations: incompatible-column cases beyond missing columns have mapper-level
coverage only. Compatible-but-corrupt column I/O can still occur before candidates
are known. General OR/NOT/should/MSM relevance, representative benchmarking,
Elasticsearch coexistence, catalog promotion/HA/durability and a newly attributed
gem release candidate remain separate gates. `.pre.contract1` remains attributed to
its earlier tested server; these changes do not silently expand its compatibility.

## Searcher process-loss observation

The final `leaf_loss.py` probe records 62 HTTP 200 samples: 20 before, 18 during
membership transition, 20 on the surviving leaf and 4 after rejoin. Every sampled
response matches independently known IDs/counts for broad/selective/empty/novel
graph queries. Membership convergence was 4.186 seconds; this is **not observed
downtime** because no sampled request failed. All nodes were restored.

The retained fixture has 12 CC and 4 CCC rows across four immutable splits. Both
searchers use the same local filesystem on one host. Empty-family queries may
prune all splits by tags; they do not prove physical candidate handling. HTTP
wall time, server-reported took and per-process RSS/HWM are observations only.
Five samples per variant before/survivor and one after restoration cannot justify
percentiles, capacity or batch/concurrency recommendations. No stage instrumentation
separates parsing/RDKit/decoding, and no storage/node/host/power-loss test occurred.

The first report and exact first script are retained. Its reviewer found that a
recovery exception could skip report writing; the final harness guards restoration
and writes evidence on that failure path, then exits nonzero. Both synthetic runs
passed; neither grants campaign HA/durability acceptance.
