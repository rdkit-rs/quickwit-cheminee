# QuickwitCheminee::FileSourceSqs

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **deduplication_cleanup_interval_secs** | **Integer** |  | [optional] |
| **deduplication_window_duration_secs** | **Integer** |  | [optional] |
| **deduplication_window_max_messages** | **Integer** |  | [optional] |
| **message_type** | [**FileSourceMessageType**](FileSourceMessageType.md) |  |  |
| **queue_url** | **String** |  |  |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::FileSourceSqs.new(
  deduplication_cleanup_interval_secs: null,
  deduplication_window_duration_secs: null,
  deduplication_window_max_messages: null,
  message_type: null,
  queue_url: null
)
```

