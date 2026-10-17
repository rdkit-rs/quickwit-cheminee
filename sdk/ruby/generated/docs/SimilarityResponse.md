# QuickwitCheminee::SimilarityResponse

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **elapsed_time_micros** | **Integer** |  |  |
| **hits** | [**Array&lt;SimilarityHit&gt;**](SimilarityHit.md) |  |  |
| **num_hits** | **Integer** |  |  |
| **searched_splits** | **Integer** |  |  |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::SimilarityResponse.new(
  elapsed_time_micros: null,
  hits: null,
  num_hits: null,
  searched_splits: null
)
```

