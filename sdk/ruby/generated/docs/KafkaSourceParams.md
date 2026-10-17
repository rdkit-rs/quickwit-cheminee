# QuickwitCheminee::KafkaSourceParams

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **client_log_level** | **String** | Kafka client log level. Possible values are &#x60;debug&#x60;, &#x60;info&#x60;, &#x60;warn&#x60;, and &#x60;error&#x60;. | [optional] |
| **client_params** | **Object** | Kafka client configuration parameters. | [optional] |
| **enable_backfill_mode** | **Boolean** | When backfill mode is enabled, the source exits after reaching the end of the topic. | [optional] |
| **topic** | **String** | Name of the topic that the source consumes. |  |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::KafkaSourceParams.new(
  client_log_level: null,
  client_params: null,
  enable_backfill_mode: null,
  topic: null
)
```

