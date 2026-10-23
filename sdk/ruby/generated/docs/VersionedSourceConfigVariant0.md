# QuickwitCheminee::VersionedSourceConfigVariant0

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedSourceConfigVariant0.openapi_one_of
# =>
# [
#   :'VersionedSourceConfigVariant0Member0',
#   :'VersionedSourceConfigVariant0Member1',
#   :'VersionedSourceConfigVariant0Member10',
#   :'VersionedSourceConfigVariant0Member2',
#   :'VersionedSourceConfigVariant0Member3',
#   :'VersionedSourceConfigVariant0Member4',
#   :'VersionedSourceConfigVariant0Member5',
#   :'VersionedSourceConfigVariant0Member6',
#   :'VersionedSourceConfigVariant0Member7',
#   :'VersionedSourceConfigVariant0Member8',
#   :'VersionedSourceConfigVariant0Member9'
# ]
```

### `openapi_discriminator_name`

Returns the discriminator's property name.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedSourceConfigVariant0.openapi_discriminator_name
# => :'source_type'
```

### `openapi_discriminator_name`

Returns the discriminator's mapping.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedSourceConfigVariant0.openapi_discriminator_mapping
# =>
# {
#   :'file' => :'VersionedSourceConfigVariant0Member0',
#   :'ingest' => :'VersionedSourceConfigVariant0Member1',
#   :'ingest-api' => :'VersionedSourceConfigVariant0Member2',
#   :'ingest-cli' => :'VersionedSourceConfigVariant0Member3',
#   :'kafka' => :'VersionedSourceConfigVariant0Member4',
#   :'kinesis' => :'VersionedSourceConfigVariant0Member5',
#   :'pubsub' => :'VersionedSourceConfigVariant0Member6',
#   :'pulsar' => :'VersionedSourceConfigVariant0Member7',
#   :'stdin' => :'VersionedSourceConfigVariant0Member8',
#   :'vec' => :'VersionedSourceConfigVariant0Member9',
#   :'void' => :'VersionedSourceConfigVariant0Member10'
# }
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::VersionedSourceConfigVariant0.build(data)
# => #<VersionedSourceConfigVariant0Member0:0x00007fdd4aab02a0>

QuickwitCheminee::VersionedSourceConfigVariant0.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `VersionedSourceConfigVariant0Member0`
- `VersionedSourceConfigVariant0Member1`
- `VersionedSourceConfigVariant0Member10`
- `VersionedSourceConfigVariant0Member2`
- `VersionedSourceConfigVariant0Member3`
- `VersionedSourceConfigVariant0Member4`
- `VersionedSourceConfigVariant0Member5`
- `VersionedSourceConfigVariant0Member6`
- `VersionedSourceConfigVariant0Member7`
- `VersionedSourceConfigVariant0Member8`
- `VersionedSourceConfigVariant0Member9`
- `nil` (if no type matches)

