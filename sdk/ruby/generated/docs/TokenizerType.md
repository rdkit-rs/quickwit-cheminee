# QuickwitCheminee::TokenizerType

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::TokenizerType.openapi_one_of
# =>
# [
#   :'TokenizerTypeVariant0',
#   :'TokenizerTypeVariant1',
#   :'TokenizerTypeVariant2',
#   :'TokenizerTypeVariant3'
# ]
```

### `openapi_discriminator_name`

Returns the discriminator's property name.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::TokenizerType.openapi_discriminator_name
# => :'type'
```

### `openapi_discriminator_name`

Returns the discriminator's mapping.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::TokenizerType.openapi_discriminator_mapping
# =>
# {
#   :'ngram' => :'TokenizerTypeVariant0',
#   :'regex' => :'TokenizerTypeVariant1',
#   :'simple' => :'TokenizerTypeVariant2',
#   :'source_code' => :'TokenizerTypeVariant3'
# }
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::TokenizerType.build(data)
# => #<TokenizerTypeVariant0:0x00007fdd4aab02a0>

QuickwitCheminee::TokenizerType.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `TokenizerTypeVariant0`
- `TokenizerTypeVariant1`
- `TokenizerTypeVariant2`
- `TokenizerTypeVariant3`
- `nil` (if no type matches)

