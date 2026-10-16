# A small search interface for the catalog importer

The unpublished `quickwit-cheminee` gem can provide a short search call familiar
to Searchkick users. It does not implement Searchkick's model callbacks, `where`
translation, result objects, reindexing or Elasticsearch compatibility. Keep the
scraper's import/activation workflow separate from this read interface.

```ruby
require 'quickwit-cheminee'
require 'quickwit-cheminee/exact_search'

config = QuickwitCheminee::Configuration.new
config.scheme = 'http'
config.host = '127.0.0.1:7280'
config.base_path = ''
api = QuickwitCheminee::DefaultApi.new(QuickwitCheminee::ApiClient.new(config))
offers = QuickwitCheminee::ExactSearch.new(api: api, generation: 'offers-001')

query = {term: {'metadata.supplier': 'Acme'}}
page = offers.search(query: query, limit: 20, offset: 0)
documents = page.fetch(:hits).fetch(:hits).map { |hit| hit.fetch(:_source) }
total = page.fetch(:hits).fetch(:total).fetch(:value)
# Use the same query for a separate count when no documents are needed:
total_only = offers.count(query: query)
```

Use field paths and field types from your index mapping. Results are symbol-keyed
hashes, not ActiveRecord models. `count` issues a strict zero-hit search; it is a
separate observation, not a snapshot shared with an earlier page. The supplied
gem is `0.9.1.pre.contract1`, built from `8009925c…`; fixture checks against it do
not establish compatibility with every later server change.

## Pagination contract

For a second bounded request, use `offers.search(query: query, limit: 20,
offset: 20)`. `limit` and `offset` must be nonnegative integers whose sum is at
most 10,000. The default limit is 20. Zero limit is valid for count-only requests.
At or beyond the reported total, a valid response has an empty hit list. A final
page may be shorter than the limit; an unexpectedly short earlier page is rejected.

The adapter requests score descending, then numeric `record_id` ascending, and
checks each page's order, unique IDs, generation and completeness. Keep u64 IDs
as Ruby integers, including values above JavaScript's exact integer range. The
adapter does not detect duplicates across separate pages or enforce immutable
indexes. Split merges can change scores even when documents are unchanged. These
offset calls are not a snapshot or a supported exhaustive catalog-export recipe;
no cursor/scroll API or deep-pagination performance recommendation is provided.
The legacy `cheminee_v1_basic` method's `result_limit` only caps one response and
does not provide offset pagination.

## Handle distinct failure types

* Local type/value and pagination checks raise `ArgumentError` before HTTP;
  query serialization can also raise JSON errors, such as `JSON::GeneratorError`
  for invalid UTF-8 strings.
* HTTP errors raise `QuickwitCheminee::ApiError`; `code`, `response_headers` and
  `response_body` retain server details. A 429 or 503 is not retried automatically.
* A successful HTTP response with partial or inconsistent search metadata raises
  `QuickwitCheminee::ExactSearch::IncompleteResponse`. Its bounded `reason`,
  `status` and sanitized optional `request_id` are suitable diagnostic fields.
* Timeouts and connection failures are wrapped in `ApiError`; do not assume these
  errors have an HTTP status or request ID. Other transport exceptions, such as
  `Faraday::SSLError`, can propagate directly. Never convert a failed search into
  zero hits.

Leave debugging disabled. Avoid routinely logging `ApiError#to_s` or response
bodies, which can contain catalog data. A request ID is available only when the
server or proxy supplies it; sanitize it before using it in logs.

For ingestion, a timeout or missing/inconsistent acknowledgement after dispatch
has an uncertain write outcome. Stable record IDs do not provide upserts or make
retries idempotent. Quarantine and reconcile the staging generation; do not
activate it or withdraw missing offers after a partial scrape. See the
[SDK README](README.md) for acknowledgement checks and native chemistry contracts.

## Local validation scope

`wire_test.rb` exercises the installed packaged gem against loopback HTTP fixtures,
including offset boundaries, terminal pages, lossless IDs, invalid page order,
short pages and HTTP errors. Fixtures verify client behavior, not chemistry,
server pagination stability, scale or durability. Live integration with the v5
server remains pending; this checkpoint supplies no native runtime.
