# QuickwitCheminee::VersionedSourceConfig

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedSourceConfig.openapi_one_of
# =>
# [
#   :'VersionedSourceConfigVariant0',
#   :'VersionedSourceConfigVariant1'
# ]
```

### `openapi_discriminator_name`

Returns the discriminator's property name.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedSourceConfig.openapi_discriminator_name
# => :'version'
```

### `openapi_discriminator_name`

Returns the discriminator's mapping.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedSourceConfig.openapi_discriminator_mapping
# =>
# {
#   :'0.7' => :'VersionedSourceConfigVariant1',
#   :'0.9' => :'VersionedSourceConfigVariant0'
# }
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedSourceConfig.build(data)
# => #<VersionedSourceConfigVariant0:0x00007fdd4aab02a0>

QuickwitCheminee::VersionedSourceConfig.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `VersionedSourceConfigVariant0`
- `VersionedSourceConfigVariant1`
- `nil` (if no type matches)

