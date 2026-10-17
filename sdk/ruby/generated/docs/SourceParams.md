# QuickwitCheminee::SourceParams

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::SourceParams.openapi_one_of
# =>
# [
#   :'SourceParamsVariant0',
#   :'SourceParamsVariant1',
#   :'SourceParamsVariant10',
#   :'SourceParamsVariant2',
#   :'SourceParamsVariant3',
#   :'SourceParamsVariant4',
#   :'SourceParamsVariant5',
#   :'SourceParamsVariant6',
#   :'SourceParamsVariant7',
#   :'SourceParamsVariant8',
#   :'SourceParamsVariant9'
# ]
```

### `openapi_discriminator_name`

Returns the discriminator's property name.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::SourceParams.openapi_discriminator_name
# => :'source_type'
```

### `openapi_discriminator_name`

Returns the discriminator's mapping.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::SourceParams.openapi_discriminator_mapping
# =>
# {
#   :'file' => :'SourceParamsVariant0',
#   :'ingest' => :'SourceParamsVariant1',
#   :'ingest-api' => :'SourceParamsVariant2',
#   :'ingest-cli' => :'SourceParamsVariant3',
#   :'kafka' => :'SourceParamsVariant4',
#   :'kinesis' => :'SourceParamsVariant5',
#   :'pubsub' => :'SourceParamsVariant6',
#   :'pulsar' => :'SourceParamsVariant7',
#   :'stdin' => :'SourceParamsVariant8',
#   :'vec' => :'SourceParamsVariant9',
#   :'void' => :'SourceParamsVariant10'
# }
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::SourceParams.build(data)
# => #<SourceParamsVariant0:0x00007fdd4aab02a0>

QuickwitCheminee::SourceParams.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `SourceParamsVariant0`
- `SourceParamsVariant1`
- `SourceParamsVariant10`
- `SourceParamsVariant2`
- `SourceParamsVariant3`
- `SourceParamsVariant4`
- `SourceParamsVariant5`
- `SourceParamsVariant6`
- `SourceParamsVariant7`
- `SourceParamsVariant8`
- `SourceParamsVariant9`
- `nil` (if no type matches)

