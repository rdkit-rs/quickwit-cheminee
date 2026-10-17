# QuickwitCheminee::RestIngestResponse

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **num_docs_for_processing** | **Integer** | Number of rows in the request payload |  |
| **num_ingested_docs** | **Integer** | Number of docs successfully ingested | [optional] |
| **num_rejected_docs** | **Integer** | Number of docs rejected because of parsing errors | [optional] |
| **parse_failures** | [**Array&lt;RestParseFailure&gt;**](RestParseFailure.md) | Detailed description of parsing errors (available if the query param &#x60;detailed_response&#x60; is set to &#x60;true&#x60;) | [optional] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::RestIngestResponse.new(
  num_docs_for_processing: null,
  num_ingested_docs: null,
  num_rejected_docs: null,
  parse_failures: null
)
```

