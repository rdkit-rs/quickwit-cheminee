# QuickwitCheminee::VersionedIndexMetadataVariant0

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **checkpoint** | **Object** |  |  |
| **create_timestamp** | **Integer** |  | [optional] |
| **index_config** | [**VersionedIndexConfig**](VersionedIndexConfig.md) |  |  |
| **index_uid** | **String** |  |  |
| **sources** | [**Array&lt;VersionedSourceConfig&gt;**](VersionedSourceConfig.md) |  |  |
| **version** | **String** |  |  |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::VersionedIndexMetadataVariant0.new(
  checkpoint: null,
  create_timestamp: null,
  index_config: null,
  index_uid: null,
  sources: null,
  version: null
)
```

