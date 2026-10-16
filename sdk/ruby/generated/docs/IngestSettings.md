# QuickwitCheminee::IngestSettings

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **min_shards** | **Integer** | Configures the minimum number of shards to use for ingestion. | [optional][default to 1] |
| **validate_docs** | **Boolean** | Whether to validate documents against the current doc mapping during ingestion. Defaults to true. When false, documents will be written directly to the WAL without validation, but might still be rejected during indexing when applying the doc mapping in the doc processor, in that case the documents are dropped and a warning is logged.  Note that when a source has a VRL transform configured, documents are not validated against the doc mapping during ingestion either. | [optional][default to true] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::IngestSettings.new(
  min_shards: null,
  validate_docs: null
)
```

