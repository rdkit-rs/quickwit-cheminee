# Generated Quickwit-Cheminee Ruby SDK

Local candidate: **0.9.1.pre.contract1**, generated from server source commit
`8009925c6b9757edc77ef8e6111309503028e7c5` on the local integration branch. No package has been published.
The exact unpublished DSL commit `276bd1ab7455d0141bd8d9427d00acb1bb7ad845` is preserved and integrated.

The client retains the existing shipping model: OpenAPI Generator, Faraday,
`DefaultApi`, generated models, `Configuration`, and `ApiError`. Its namespace is
`QuickwitCheminee`; `require 'quickwit-cheminee'`. The old `Cheminee` namespace can
be loaded in the same process. A narrow opt-in `ExactSearch` adapter enforces completeness policy for composable queries;
there is no global monkeypatch.

## What has been checked

- Actual server schema export, four OpenAPI regression tests, six non-native
  chemistry-route tests and thirteen ingestion tests passed.
- Sixteen installed-gem tests / 319 assertions passed against a controlled real
  HTTP peer: exact Unicode NDJSON bytes and Content-Length, false query options,
  mixed rejection counts, unknown counts as nil, metadata/discriminator handling,
  five search request shapes, full u64 document IDs, error status/request IDs,
  no automatic write retry after timeout, legacy namespace coexistence, and strict
  search/count policies with malformed-success rejection and bounded diagnostics.
- Nested field mappings preserve their additional JSON options; boolean and object
  fast-field variants round-trip. Activated dependencies match the lock.
- All eleven source types round-trip under supported source versions 0.7 and 0.9;
  four tokenizer variants round-trip; unknown/missing discriminators raise.
- Live non-native server smoke passed: create a dynamic index and retain its mapping options, accept two rows/reject one,
  filtered basic search with nested Unicode metadata, published count and delete.
  All four native-only chemistry methods returned capability errors as expected.
- Two generations from the same schema, tools and manifest inputs matched
  byte-for-byte. This does not claim reproducible native binaries or gem tar timestamps.

The native distributed harness passed 16 HTTP cases. The installed gem passed
[native_smoke.rb](native_smoke.rb) against restarted fixture services: graph and
Tanimoto counts, complete offset enumeration with ties, and failed-leaf rejection
for search and count. Unchecked partial responses reproduced the misleading exact
total. These tiny fixtures do not measure paging performance or crash durability.

Selective candidate equivalence and precise timestamp tests passed on the continuation
server: 68 HTTP cases, plus 105 assertions in the existing 109-request probe (4 cases
remain observation-only). See the campaign evidence for exact binary hashes and
source-review scope. The new candidate preserves the unchanged exported API schema,
updates server provenance and documents uncertain acknowledgement handling.
Broader OR relevance, old-schema compilation/warmup, timestamp-sort pruning, Compose
coexistence, durability and HA remain open. Fixture response tests do not establish
chemistry truth. The manual CI preparation workflow is committed for review but has
not been run in GitHub.

Fresh core/query tests on recovered code passed (174 tests without native chemistry;
185 across core/query/native-mapper suites with native chemistry). These overlap
and must not be added as independent cases. Broader native document-mapper/server
validation is recorded separately in the campaign evidence.

## Import and filtered search

Use a disposable index with the mapping in [live_smoke.rb](live_smoke.rb) to try the
tested non-native importer path. Production chemistry indexes also need the pinned
preparation/fingerprint mapping and native-enabled server; readiness alone does
not prove either condition.

```ruby
require 'quickwit-cheminee'
require 'json'

config = QuickwitCheminee::Configuration.new
config.host = '127.0.0.1:7280'
config.scheme = 'http'
config.base_path = ''
api = QuickwitCheminee::DefaultApi.new(QuickwitCheminee::ApiClient.new(config))

# One supplier offer per document. Stable IDs do not turn this into an upsert.
rows = [{record_id: 1, smiles: 'CCO', metadata: {
  supplier: 'Acme', offer_id: 'ACME-123', available: true,
  observed_at: '2026-10-16T00:00:00Z'
}}]
raise 'Empty batch' if rows.empty?
ndjson = rows.map { |row| JSON.generate(row) }.join("\n") + "\n"
batch = api.ingest('offers-staging', ndjson, commit: 'wait_for', detailed_response: true)
unless batch.num_ingested_docs == rows.length && batch.num_rejected_docs == 0
  raise 'Batch acceptance incomplete or unknown; do not activate this catalog'
end

result = api.cheminee_v1_basic('offers-staging', {
  query: 'metadata.supplier:Acme', extra_query: 'metadata.available:true', result_limit: 100
})
```

Use `*_with_http_info` to obtain `[model, HTTP_status, response_headers]`. A
`QuickwitCheminee::ApiError` retains `code`, `response_body` and `response_headers`
for HTTP errors. A timeout, failed transport, or missing/inconsistent acknowledgement
after dispatch has an uncertain write outcome. The client does not retry it automatically. Do not wrap
ingestion in a blanket retry middleware. Quarantine/reconcile an uncertain staging
generation; activation/rollback automation still needs its own tested contract.

Do not routinely log `parse_failures`, response bodies or `ApiError#to_s`: they may
contain original documents. Leave `config.debugging` false. Log operation name,
bounded outcome category, counts and available request ID; put import/request IDs
in structured logs or traces, not metric labels. A request ID header is preserved
when a server/proxy supplies one; this SDK does not promise that PR3 creates one.

Availability is a dated scrape observation, not live stock. Neither a successful
batch nor a published count proves unique offer IDs or a complete scrape. A partial
scrape must never withdraw missing offers from the last complete catalog.

## Strict composable search

```ruby
require 'quickwit-cheminee/exact_search'
search = QuickwitCheminee::ExactSearch.new(api: api, generation: 'offers-immutable-001')
result = search.search(query: {term: {'metadata.supplier': 'Acme'}}, limit: 20)
count = search.count(query: {match_all: {}})
```

The adapter pins `allow_partial_search_results=false`, `track_total_hits:true`,
`_score` descending and `record_id` ascending. It validates completeness metadata,
page length, generation and lossless numeric sort IDs. `IncompleteResponse` exposes
a bounded `reason`, HTTP `status` and sanitized optional `request_id`; its message
contains no query, document or response body. HTTP failures remain generated `ApiError`.
Do not use the separate server `_count` route for exact counts: it drops split failures.

The generated `search_composable_unchecked` preserves the raw JSON response and the
server's partial-by-default behavior. It is intentionally named unchecked. Use the
adapter for exhaustive requests. An `eq` total alone is insufficient proof.

Provide one concrete generation with unique stored u64 `record_id` values. The adapter
does not make the index immutable, prove uniqueness across pages, or activate a catalog.
`offset` is bounded with `offset + limit <= 10000`; this is a safety bound, not a
benchmark-derived recommendation. No cursor helper is offered yet. Even immutable
documents may change mixed text/chemistry score order after split merges; generic
snapshot pagination has not been established.

Outer clauses use the supported ES-shaped DSL; operator `candidates` use tagged
Quickwit QueryAst. Prepared fingerprints/SMILES and matching chemistry contracts are
required. The adapter never pushes sibling filters into candidates or changes scoring.
Executed chemistry reports bad candidate data, but Boolean simplification and split
pruning can skip branches entirely. Search is not a global catalog-validation scan.
The current contract requires eager query-input validation and failure when an
unresolved stored-data error could affect membership, count or rank. It permits
skipping logically irrelevant corrupt records. The old global-verification proposal
is superseded; the full relevance-based regression gate remains open.

## Migration from Cheminee

```ruby
# Existing Cheminee GET basic search:
old_api.v1_indexes_index_search_basic_get('offers', 'supplier:Acme')

# New explicit POST request (use the new index's field paths):
api.cheminee_v1_basic('offers', {query: 'metadata.supplier:Acme', result_limit: 100})

# Native-enabled server required; these values must match the index contract:
api.cheminee_v1_substructure('offers', {
  smiles: 'CCO', use_chirality: true, include_identity: false,
  spec: {format: 'morgan-r3-2048-lsb0-v1',
         rdkit_version: '2026.09.1', preparation_id: 'sanitize-only-v1'},
  extra_query: 'metadata.supplier:Acme', result_limit: 100
})
```

The graph request explicitly chooses chirality and identity behavior; PR3 defaults
chirality to false and include_identity to true. Preserve salts, stereochemistry,
structure identity, supplier offer identity and provenance separately. Fingerprint
matching is not a substitute for exhaustive graph verification. No arbitrary
Searchkick/Elasticsearch compatibility or arrays-of-offers correlation is claimed.

The eleven generated operations are readiness, create/delete/describe index, ingestion,
five legacy chemistry searches, and an explicitly unchecked composable search transport. `describe_index` reports published counts, not
offer uniqueness. Legacy `result_limit` is 1–10,000; it is not an offset or cursor.
Stable record-ID ties do not provide a snapshot across refreshes. The unchecked composable transport exposes the server response; use `ExactSearch`
for fail-closed queries and counts. Installed native tests verify rejection of failed
leaves, exact counts and record-ID ties. Server legacy chemistry routes reject
incomplete searches. Scroll/cursor traversal is not provided. No production concurrency, timeout, deep-pagination or
batch-size recommendation has been established for this new client.

## Reproduce generation

Rust source export (without native chemistry) uses the real server schema:

```sh
cd quickwit
cargo +1.96.1 run --locked -p quickwit-serve --example export_openapi > /tmp/server-openapi.json
cd ..
python3 sdk/ruby/projection_test.py /tmp/server-openapi.json
python3 sdk/ruby/generate.py \
  --combined-schema /tmp/server-openapi.json \
  --generator-jar /path/to/openapi-generator-cli-7.11.0.jar \
  --server-revision "$(git rev-parse HEAD)" \
  --gem-version 0.9.1.pre.contract1 --output /tmp/new-ruby-sdk
```

The output directory must be empty. Obtain the JAR from Maven Central at
`org/openapitools/openapi-generator-cli/7.11.0/`; the script requires SHA-256
`113c25df5a781d5a1fc2b883f12fe8f263db285ab12e15854d5b15306e1bf7fc`.
It selects explicit operations, closes component references, names tagged variants,
and distributes union intersections without discarding constraints. New authentication,
unresolved references, cycles, ambiguous mappings and excessive expansion fail.

The checked-in templates derive from that exact generator JAR. The union template
adds nested-union dispatch and rejects unknown discriminators instead of silently
returning nil, including preserving boolean false. The mapping templates retain
type-specific additional JSON options under a guarded schema extension. The README
template includes the publication hold and safe logging guidance. The gemspec template bounds tested dependency families and selects
package files explicitly so an existing `.gem` cannot be packaged recursively.
`Gemfile.lock` pins the tested dependency graph; consumer runtime requirements remain
bounded ranges. No generated Ruby source is patched after generation.

`generated/provenance.json` records server revision, combined/projected schema hashes,
generator/config/projection/template hashes and dependency-lock hash. Source revision
is supplied by the export job: when using an externally supplied schema, the caller
must establish its source provenance. `schema/server-openapi.json` retains this run's
full export; `generated/openapi.json` is the SDK contract. Re-export from source on
every server revision rather than editing either JSON file by hand.

## Release preparation and hold

[prepare-ruby-sdk.yml](../../.github/workflows/prepare-ruby-sdk.yml) is manual-only,
read-only toward repository contents, and produces review artifacts. It does not
push commits/tags, publish packages or create credentials. The generation and
installed-gem tests run before candidate artifacts are uploaded when someone
explicitly runs the workflow.

Every server API revision requires a corresponding reviewed gem candidate. Record
the tested server SHA and gem version together. Breaking request/response shapes,
defaults, error/completeness behavior or chemistry preparation require an explicit
breaking-version decision and migration tests; matching version numbers alone do
not prove compatibility. During this prerelease phase, consumers should pin the
exact gem and tested server commit. No stable-version promise is made yet.

Before external publication: resolve the demonstrated error-domain gap, pass importer
safety and operational gates, resolve independent readiness findings, and obtain separate publication
approval. Keep historical benchmark claims separate from these functional tests.
