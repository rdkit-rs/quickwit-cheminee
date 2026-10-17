# QuickwitCheminee::PulsarSourceAuth

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::PulsarSourceAuth.openapi_one_of
# =>
# [
#   :'PulsarSourceAuthOneOf',
#   :'PulsarSourceAuthOneOf1'
# ]
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::PulsarSourceAuth.build(data)
# => #<PulsarSourceAuthOneOf:0x00007fdd4aab02a0>

QuickwitCheminee::PulsarSourceAuth.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `PulsarSourceAuthOneOf`
- `PulsarSourceAuthOneOf1`
- `nil` (if no type matches)

