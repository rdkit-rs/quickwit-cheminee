# QuickwitCheminee::VersionedSourceConfigVariant1

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedSourceConfigVariant1.openapi_one_of
# =>
# [
#   :'VersionedSourceConfigVariant1Member0',
#   :'VersionedSourceConfigVariant1Member1',
#   :'VersionedSourceConfigVariant1Member10',
#   :'VersionedSourceConfigVariant1Member2',
#   :'VersionedSourceConfigVariant1Member3',
#   :'VersionedSourceConfigVariant1Member4',
#   :'VersionedSourceConfigVariant1Member5',
#   :'VersionedSourceConfigVariant1Member6',
#   :'VersionedSourceConfigVariant1Member7',
#   :'VersionedSourceConfigVariant1Member8',
#   :'VersionedSourceConfigVariant1Member9'
# ]
```

### `openapi_discriminator_name`

Returns the discriminator's property name.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedSourceConfigVariant1.openapi_discriminator_name
# => :'source_type'
```

### `openapi_discriminator_name`

Returns the discriminator's mapping.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedSourceConfigVariant1.openapi_discriminator_mapping
# =>
# {
#   :'file' => :'VersionedSourceConfigVariant1Member0',
#   :'ingest' => :'VersionedSourceConfigVariant1Member1',
#   :'ingest-api' => :'VersionedSourceConfigVariant1Member2',
#   :'ingest-cli' => :'VersionedSourceConfigVariant1Member3',
#   :'kafka' => :'VersionedSourceConfigVariant1Member4',
#   :'kinesis' => :'VersionedSourceConfigVariant1Member5',
#   :'pubsub' => :'VersionedSourceConfigVariant1Member6',
#   :'pulsar' => :'VersionedSourceConfigVariant1Member7',
#   :'stdin' => :'VersionedSourceConfigVariant1Member8',
#   :'vec' => :'VersionedSourceConfigVariant1Member9',
#   :'void' => :'VersionedSourceConfigVariant1Member10'
# }
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedSourceConfigVariant1.build(data)
# => #<VersionedSourceConfigVariant1Member0:0x00007fdd4aab02a0>

QuickwitCheminee::VersionedSourceConfigVariant1.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `VersionedSourceConfigVariant1Member0`
- `VersionedSourceConfigVariant1Member1`
- `VersionedSourceConfigVariant1Member10`
- `VersionedSourceConfigVariant1Member2`
- `VersionedSourceConfigVariant1Member3`
- `VersionedSourceConfigVariant1Member4`
- `VersionedSourceConfigVariant1Member5`
- `VersionedSourceConfigVariant1Member6`
- `VersionedSourceConfigVariant1Member7`
- `VersionedSourceConfigVariant1Member8`
- `VersionedSourceConfigVariant1Member9`
- `nil` (if no type matches)

