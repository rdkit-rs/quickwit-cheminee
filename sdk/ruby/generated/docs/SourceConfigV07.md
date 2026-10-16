# QuickwitCheminee::SourceConfigV07

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::SourceConfigV07.openapi_one_of
# =>
# [
#   :'SourceConfigV07Member0',
#   :'SourceConfigV07Member1',
#   :'SourceConfigV07Member10',
#   :'SourceConfigV07Member2',
#   :'SourceConfigV07Member3',
#   :'SourceConfigV07Member4',
#   :'SourceConfigV07Member5',
#   :'SourceConfigV07Member6',
#   :'SourceConfigV07Member7',
#   :'SourceConfigV07Member8',
#   :'SourceConfigV07Member9'
# ]
```

### `openapi_discriminator_name`

Returns the discriminator's property name.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::SourceConfigV07.openapi_discriminator_name
# => :'source_type'
```

### `openapi_discriminator_name`

Returns the discriminator's mapping.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::SourceConfigV07.openapi_discriminator_mapping
# =>
# {
#   :'file' => :'SourceConfigV07Member0',
#   :'ingest' => :'SourceConfigV07Member1',
#   :'ingest-api' => :'SourceConfigV07Member2',
#   :'ingest-cli' => :'SourceConfigV07Member3',
#   :'kafka' => :'SourceConfigV07Member4',
#   :'kinesis' => :'SourceConfigV07Member5',
#   :'pubsub' => :'SourceConfigV07Member6',
#   :'pulsar' => :'SourceConfigV07Member7',
#   :'stdin' => :'SourceConfigV07Member8',
#   :'vec' => :'SourceConfigV07Member9',
#   :'void' => :'SourceConfigV07Member10'
# }
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::SourceConfigV07.build(data)
# => #<SourceConfigV07Member0:0x00007fdd4aab02a0>

QuickwitCheminee::SourceConfigV07.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `SourceConfigV07Member0`
- `SourceConfigV07Member1`
- `SourceConfigV07Member10`
- `SourceConfigV07Member2`
- `SourceConfigV07Member3`
- `SourceConfigV07Member4`
- `SourceConfigV07Member5`
- `SourceConfigV07Member6`
- `SourceConfigV07Member7`
- `SourceConfigV07Member8`
- `SourceConfigV07Member9`
- `nil` (if no type matches)

