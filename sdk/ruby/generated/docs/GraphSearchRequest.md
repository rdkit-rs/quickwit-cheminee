# QuickwitCheminee::GraphSearchRequest

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **extra_query** | **String** |  | [optional] |
| **include_identity** | **Boolean** |  | [optional] |
| **prepared_smiles_field** | **String** |  | [optional] |
| **ranking** | [**GraphRanking**](GraphRanking.md) |  | [optional] |
| **result_limit** | **Integer** |  | [optional][default to 100] |
| **smiles** | **String** |  |  |
| **spec** | [**FingerprintSpec**](FingerprintSpec.md) |  |  |
| **use_chirality** | **Boolean** |  | [optional] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::GraphSearchRequest.new(
  extra_query: null,
  include_identity: null,
  prepared_smiles_field: null,
  ranking: null,
  result_limit: null,
  smiles: null,
  spec: null,
  use_chirality: null
)
```

