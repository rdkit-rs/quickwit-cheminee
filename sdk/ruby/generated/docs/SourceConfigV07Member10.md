# QuickwitCheminee::SourceConfigV07Member10

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **params** | **Object** |  |  |
| **source_type** | **String** |  |  |
| **desired_num_pipelines** | **Integer** |  | [optional] |
| **enabled** | **Boolean** |  | [optional] |
| **input_format** | [**SourceInputFormat**](SourceInputFormat.md) |  | [optional] |
| **max_num_pipelines_per_indexer** | **Integer** |  | [optional] |
| **source_id** | **String** |  |  |
| **transform** | [**TransformConfig**](TransformConfig.md) |  | [optional] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::SourceConfigV07Member10.new(
  params: null,
  source_type: null,
  desired_num_pipelines: null,
  enabled: null,
  input_format: null,
  max_num_pipelines_per_indexer: null,
  source_id: null,
  transform: null
)
```

