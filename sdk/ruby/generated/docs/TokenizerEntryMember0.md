# QuickwitCheminee::TokenizerEntryMember0

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **max_gram** | **Integer** |  |  |
| **min_gram** | **Integer** |  |  |
| **prefix_only** | **Boolean** |  | [optional] |
| **type** | **String** |  |  |
| **filters** | [**Array&lt;TokenFilterType&gt;**](TokenFilterType.md) |  | [optional] |
| **name** | **String** | Tokenizer name. |  |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::TokenizerEntryMember0.new(
  max_gram: null,
  min_gram: null,
  prefix_only: null,
  type: null,
  filters: null,
  name: null
)
```

