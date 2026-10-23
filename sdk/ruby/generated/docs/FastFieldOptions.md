# QuickwitCheminee::FastFieldOptions

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::FastFieldOptions.openapi_one_of
# =>
# [
#   :'Boolean',
#   :'FastFieldOptionsOneOf'
# ]
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::FastFieldOptions.build(data)
# => #<Boolean:0x00007fdd4aab02a0>

QuickwitCheminee::FastFieldOptions.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `Boolean`
- `FastFieldOptionsOneOf`
- `nil` (if no type matches)

