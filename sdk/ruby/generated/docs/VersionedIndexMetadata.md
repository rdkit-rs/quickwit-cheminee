# QuickwitCheminee::VersionedIndexMetadata

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedIndexMetadata.openapi_one_of
# =>
# [
#   :'VersionedIndexMetadataVariant0'
# ]
```

### `openapi_discriminator_name`

Returns the discriminator's property name.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedIndexMetadata.openapi_discriminator_name
# => :'version'
```

### `openapi_discriminator_name`

Returns the discriminator's mapping.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedIndexMetadata.openapi_discriminator_mapping
# =>
# {
#   :'0.9' => :'VersionedIndexMetadataVariant0'
# }
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedIndexMetadata.build(data)
# => #<VersionedIndexMetadataVariant0:0x00007fdd4aab02a0>

QuickwitCheminee::VersionedIndexMetadata.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `VersionedIndexMetadataVariant0`
- `nil` (if no type matches)

