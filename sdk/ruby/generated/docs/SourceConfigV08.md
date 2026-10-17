# QuickwitCheminee::SourceConfigV08

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::SourceConfigV08.openapi_one_of
# =>
# [
#   :'SourceConfigV08Member0',
#   :'SourceConfigV08Member1',
#   :'SourceConfigV08Member10',
#   :'SourceConfigV08Member2',
#   :'SourceConfigV08Member3',
#   :'SourceConfigV08Member4',
#   :'SourceConfigV08Member5',
#   :'SourceConfigV08Member6',
#   :'SourceConfigV08Member7',
#   :'SourceConfigV08Member8',
#   :'SourceConfigV08Member9'
# ]
```

### `openapi_discriminator_name`

Returns the discriminator's property name.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::SourceConfigV08.openapi_discriminator_name
# => :'source_type'
```

### `openapi_discriminator_name`

Returns the discriminator's mapping.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::SourceConfigV08.openapi_discriminator_mapping
# =>
# {
#   :'file' => :'SourceConfigV08Member0',
#   :'ingest' => :'SourceConfigV08Member1',
#   :'ingest-api' => :'SourceConfigV08Member2',
#   :'ingest-cli' => :'SourceConfigV08Member3',
#   :'kafka' => :'SourceConfigV08Member4',
#   :'kinesis' => :'SourceConfigV08Member5',
#   :'pubsub' => :'SourceConfigV08Member6',
#   :'pulsar' => :'SourceConfigV08Member7',
#   :'stdin' => :'SourceConfigV08Member8',
#   :'vec' => :'SourceConfigV08Member9',
#   :'void' => :'SourceConfigV08Member10'
# }
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::SourceConfigV08.build(data)
# => #<SourceConfigV08Member0:0x00007fdd4aab02a0>

QuickwitCheminee::SourceConfigV08.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `SourceConfigV08Member0`
- `SourceConfigV08Member1`
- `SourceConfigV08Member10`
- `SourceConfigV08Member2`
- `SourceConfigV08Member3`
- `SourceConfigV08Member4`
- `SourceConfigV08Member5`
- `SourceConfigV08Member6`
- `SourceConfigV08Member7`
- `SourceConfigV08Member8`
- `SourceConfigV08Member9`
- `nil` (if no type matches)

