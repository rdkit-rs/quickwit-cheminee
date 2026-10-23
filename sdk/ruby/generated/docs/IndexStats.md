# QuickwitCheminee::IndexStats

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **index_id** | **String** |  |  |
| **index_uri** | **String** |  |  |
| **max_timestamp** | **Integer** |  | [optional] |
| **min_timestamp** | **Integer** |  | [optional] |
| **num_published_docs** | **Integer** |  |  |
| **num_published_splits** | **Integer** |  |  |
| **size_published_docs_uncompressed** | **Integer** |  |  |
| **size_published_splits** | **Integer** |  |  |
| **timestamp_field_name** | **String** |  | [optional] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::IndexStats.new(
  index_id: null,
  index_uri: null,
  max_timestamp: null,
  min_timestamp: null,
  num_published_docs: null,
  num_published_splits: null,
  size_published_docs_uncompressed: null,
  size_published_splits: null,
  timestamp_field_name: null
)
```

