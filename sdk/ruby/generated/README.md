# quickwit-cheminee 0.9.1.pre.contract1

Generated Ruby/Faraday candidate for Quickwit-Cheminee. **Publication hold: this
artifact is for local review; it has not been authorized for release.** Consult
`provenance.json` for the exact server revision, schemas, tooling and dependency
lock hashes. This candidate includes the recovered composable-query source; native and distributed
validation must be checked in the campaign evidence before deployment.

Pin the exact reviewed version in your application:

```ruby
gem 'quickwit-cheminee', '= 0.9.1.pre.contract1'
```

Install the locally built `.gem` before resolving that dependency. No RubyGems
publication or remote package availability is implied.

```ruby
require 'quickwit-cheminee'
config = QuickwitCheminee::Configuration.new
config.host = '127.0.0.1:7280'
config.scheme = 'http'
config.base_path = ''
api = QuickwitCheminee::DefaultApi.new(QuickwitCheminee::ApiClient.new(config))
result = api.cheminee_v1_basic('offers', {query: 'metadata.supplier:Acme', result_limit: 100})
```

For composable queries, opt into the narrow completeness adapter:

```ruby
require 'quickwit-cheminee/exact_search'
search = QuickwitCheminee::ExactSearch.new(api: api, generation: 'offers-immutable-001')
response = search.search(query: {term: {'metadata.supplier': 'Acme'}}, limit: 20)
count = search.count(query: {match_all: {}})
```

`ExactSearch` pins strict split failures, exact counting and the two-field sort;
it rejects incomplete or inconsistent success responses. It assumes one immutable
generation with unique stored numeric record_id values. It cannot enforce immutability,
validate all catalog IDs or prove snapshot pagination. The generated
`search_composable_unchecked` method faithfully exposes the underlying server, whose
default permits partial results; only use it when inspecting all completeness metadata.
Do not use the server's separate `_count` route for an exhaustive count.

The generated `DefaultApi`, models, `Configuration`, and `ApiError` retain the
existing Cheminee shipping pattern under the separate `QuickwitCheminee` namespace.
There is no runtime monkeypatch. See `docs/DefaultApi.md` for the eleven selected
operations. Native chemistry requires a native-enabled server and matching index
preparation/fingerprint contract. Readiness alone does not establish that capability.

Ingest takes a raw newline-delimited JSON string. Request `detailed_response: true`
and check both `num_ingested_docs` and `num_rejected_docs`; absent counts are unknown,
not zero. A timeout, transport failure, or missing/inconsistent acknowledgement after
dispatch has an uncertain write outcome and is not automatically retried. Quarantine
that staging generation; do not blindly replay the batch.
Accepted, persisted, published and searchable are distinct states. Repeated documents
are not guaranteed upserts; incomplete scrapes must not withdraw missing offers.

Keep `config.debugging` false. Do not routinely log `ApiError#to_s`, response bodies,
parse-failure documents or raw catalog content. Record bounded outcome categories,
status, counts and a request ID when supplied by the server/proxy. The client preserves
HTTP status, headers and error bodies for controlled debugging; PR3 does not promise
to generate request IDs. Availability is dated catalog information, not live stock.

This candidate passes installed transport tests and scoped native graph/fingerprint
smoke tests, including strict failed-leaf rejection and tied record-ID pagination.
Complete chemistry/error-domain semantics, general snapshot pagination, production
catalog promotion/rollback, crash durability, Elasticsearch coexistence and HA remain
unproven. Limits do not
provide stable pagination. No arbitrary Searchkick/Elasticsearch compatibility or
correlated arrays-of-offers support is claimed. Consult the repository's `sdk/ruby/README.md`
and campaign decision log for exact evidence and remaining release gates.

Runtime JSON is constrained to >= 3.1 and < 4 so duplicate response keys fail parsing.
For catalog enumeration choose `search(query: ..., order: :record_id)` to request
only the unique numeric record-ID order. Default score ordering can shift across
segment merges as BM25 statistics change, even with unchanged documents. Neither
mode creates a server snapshot; pin the generation and prevent writes/deletion.
