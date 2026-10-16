# QuickwitCheminee::IndexMetadataV08

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **checkpoint** | **Object** |  |  |
| **create_timestamp** | **Integer** |  | [optional] |
| **index_config** | [**VersionedIndexConfig**](VersionedIndexConfig.md) |  |  |
| **index_uid** | **String** |  |  |
| **sources** | [**Array&lt;VersionedSourceConfig&gt;**](VersionedSourceConfig.md) |  |  |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::IndexMetadataV08.new(
  checkpoint: null,
  create_timestamp: null,
  index_config: null,
  index_uid: null,
  sources: null
)
```

