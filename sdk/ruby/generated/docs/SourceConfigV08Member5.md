# QuickwitCheminee::SourceConfigV08Member5

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **params** | [**KinesisSourceParams**](KinesisSourceParams.md) |  |  |
| **source_type** | **String** |  |  |
| **enabled** | **Boolean** |  | [optional] |
| **input_format** | [**SourceInputFormat**](SourceInputFormat.md) |  | [optional] |
| **num_pipelines** | **Integer** |  | [optional] |
| **source_id** | **String** |  |  |
| **transform** | [**TransformConfig**](TransformConfig.md) |  | [optional] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::SourceConfigV08Member5.new(
  params: null,
  source_type: null,
  enabled: null,
  input_format: null,
  num_pipelines: null,
  source_id: null,
  transform: null
)
```

