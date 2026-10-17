# QuickwitCheminee::BasicSearchRequest

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **extra_query** | **String** |  | [optional] |
| **query** | **String** |  | [optional] |
| **result_limit** | **Integer** |  | [optional][default to 100] |
| **sort_ascending** | **Boolean** |  | [optional] |
| **sort_field** | **String** |  | [optional] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::BasicSearchRequest.new(
  extra_query: null,
  query: null,
  result_limit: null,
  sort_ascending: null,
  sort_field: null
)
```

