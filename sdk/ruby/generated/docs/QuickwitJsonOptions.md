# QuickwitCheminee::QuickwitJsonOptions

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **description** | **String** | Optional description of JSON object. | [optional] |
| **expand_dots** | **Boolean** | If true, the &#39;.&#39; in json keys will be expanded. | [optional] |
| **fast** | [**FastFieldOptions**](FastFieldOptions.md) |  | [optional] |
| **indexed** | **Boolean** | If true, all of the element in the json object will be indexed. | [optional] |
| **record** | [**IndexRecordOptionSchema**](IndexRecordOptionSchema.md) |  | [optional] |
| **stored** | **Boolean** | If true, the field will be stored in the doc store. | [optional] |
| **tokenizer** | **String** |  | [optional] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::QuickwitJsonOptions.new(
  description: null,
  expand_dots: null,
  fast: null,
  indexed: null,
  record: null,
  stored: null,
  tokenizer: null
)
```

