# QuickwitCheminee::VersionedIndexConfig

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedIndexConfig.openapi_one_of
# =>
# [
#   :'VersionedIndexConfigVariant0',
#   :'VersionedIndexConfigVariant1'
# ]
```

### `openapi_discriminator_name`

Returns the discriminator's property name.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedIndexConfig.openapi_discriminator_name
# => :'version'
```

### `openapi_discriminator_name`

Returns the discriminator's mapping.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedIndexConfig.openapi_discriminator_mapping
# =>
# {
#   :'0.8' => :'VersionedIndexConfigVariant1',
#   :'0.9' => :'VersionedIndexConfigVariant0'
# }
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedIndexConfig.build(data)
# => #<VersionedIndexConfigVariant0:0x00007fdd4aab02a0>

QuickwitCheminee::VersionedIndexConfig.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `VersionedIndexConfigVariant0`
- `VersionedIndexConfigVariant1`
- `nil` (if no type matches)

