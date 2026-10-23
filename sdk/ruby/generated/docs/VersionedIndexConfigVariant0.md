# QuickwitCheminee::VersionedIndexConfigVariant0

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **doc_mapping** | [**DocMapping**](DocMapping.md) |  |  |
| **index_id** | **String** |  |  |
| **index_uri** | **String** |  | [optional] |
| **indexing_settings** | [**IndexingSettings**](IndexingSettings.md) |  | [optional] |
| **ingest_settings** | [**IngestSettings**](IngestSettings.md) |  | [optional] |
| **retention** | [**RetentionPolicy**](RetentionPolicy.md) |  | [optional] |
| **search_settings** | [**SearchSettings**](SearchSettings.md) |  | [optional] |
| **version** | **String** |  |  |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::VersionedIndexConfigVariant0.new(
  doc_mapping: null,
  index_id: null,
  index_uri: null,
  indexing_settings: null,
  ingest_settings: null,
  retention: null,
  search_settings: null,
  version: null
)
```

