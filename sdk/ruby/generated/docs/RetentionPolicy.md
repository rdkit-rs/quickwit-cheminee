# QuickwitCheminee::RetentionPolicy

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **period** | **String** | Duration of time for which the splits should be retained, expressed in a human-friendly way (&#x60;1 hour&#x60;, &#x60;3 days&#x60;, &#x60;1 week&#x60;, ...). |  |
| **schedule** | **String** | Defines the frequency at which the retention policy is evaluated and applied, expressed in a human-friendly way (&#x60;hourly&#x60;, &#x60;daily&#x60;, ...) or as a cron expression (&#x60;0 0 * * * *&#x60;, &#x60;0 0 0 * * *&#x60;). | [optional] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::RetentionPolicy.new(
  period: null,
  schedule: null
)
```

