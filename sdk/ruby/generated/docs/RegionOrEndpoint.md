# QuickwitCheminee::RegionOrEndpoint

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::RegionOrEndpoint.openapi_one_of
# =>
# [
#   :'RegionOrEndpointOneOf',
#   :'RegionOrEndpointOneOf1'
# ]
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::RegionOrEndpoint.build(data)
# => #<RegionOrEndpointOneOf:0x00007fdd4aab02a0>

QuickwitCheminee::RegionOrEndpoint.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `RegionOrEndpointOneOf`
- `RegionOrEndpointOneOf1`
- `nil` (if no type matches)

