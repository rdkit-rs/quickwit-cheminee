# Selective queries, uncertain ingestion, and generated client checkpoint

Native runtime source: `8009925c6b9757edc77ef8e6111309503028e7c5`.
The final provenance manifest identifies the rebuilt native executable, generated
`.pre.contract1` gem, exact example sources, and live/exported schema comparison.
Two generation directories matched byte-for-byte (452 files). Gem archive timestamps
and native compilation are not claimed reproducible.

- Installed package wire tests: 16 tests / 319 assertions.
- Exact-runtime selective HTTP probe: 68 passing cases.
- Existing relevance probe: 109 requests, 105 passing assertions, 4 observations.
- Native installed-client smoke: graph/Tanimoto count and tied enumeration;
  strict search/count reject failed leaves despite unchecked `relation=eq`.
- Catalog journal experiment: 21 checks over real HTTP, including both process-exit
  boundaries, ambiguous acknowledgement, content audit across pages, empty catalog,
  stale refresh/promotion, identity preservation and rollback. Single-host cooperating
  writers only; no server write fence, power-loss, production or HA approval.
- Native query suite: 167 passing; empty-domain suite: 7; timestamp suite: 12;
  ingestion v2 suite: 157, independently rerun by Astra max. Totals overlap prior suites.
- Scoped native Clippy passed. Full workspace all-features Clippy was stopped for
  disk headroom and is **not passed**; see the status record.

Independent Astra max reviews approve their bounded source/artifact scopes only.
Count-only OR relevance, old-schema physical compilation/warmup, timestamp-sort
pruning, real corrupt-column I/O, measured Compose/Elasticsearch coexistence,
performance guidance and HA/durability remain open. Historical 100k results are not
new-code measurements; corpus/index artifacts have not been recovered.
