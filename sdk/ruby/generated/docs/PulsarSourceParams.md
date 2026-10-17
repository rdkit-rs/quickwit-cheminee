# QuickwitCheminee::PulsarSourceParams

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **address** | **String** | The connection URI for pulsar. |  |
| **authentication** | [**PulsarSourceAuth**](PulsarSourceAuth.md) |  | [optional] |
| **consumer_name** | **String** | The name to register with the pulsar source. | [optional][default to &#39;quickwit&#39;] |
| **topics** | **Array&lt;String&gt;** | List of the topics that the source consumes. |  |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::PulsarSourceParams.new(
  address: null,
  authentication: null,
  consumer_name: null,
  topics: null
)
```

