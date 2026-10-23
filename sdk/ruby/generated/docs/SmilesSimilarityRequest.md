# QuickwitCheminee::SmilesSimilarityRequest

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **extra_query** | **String** |  | [optional][default to &#39;*&#39;] |
| **result_limit** | **Integer** |  | [optional][default to 100] |
| **smiles** | **String** |  |  |
| **spec** | [**FingerprintSpec**](FingerprintSpec.md) |  |  |
| **tanimoto_minimum** | **Float** |  | [optional][default to 0.4] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::SmilesSimilarityRequest.new(
  extra_query: null,
  result_limit: null,
  smiles: null,
  spec: null,
  tanimoto_minimum: null
)
```

