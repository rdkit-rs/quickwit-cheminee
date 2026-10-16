# QuickwitCheminee::KinesisSourceParams

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **region** | **String** |  |  |
| **endpoint** | **String** |  |  |
| **enable_backfill_mode** | **Boolean** | When backfill mode is enabled, the source exits after reaching the end of the stream. | [optional] |
| **stream_name** | **String** |  |  |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::KinesisSourceParams.new(
  region: null,
  endpoint: null,
  enable_backfill_mode: null,
  stream_name: null
)
```

