# QuickwitCheminee::TokenizerConfig

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::TokenizerConfig.openapi_one_of
# =>
# [
#   :'TokenizerConfigMember0',
#   :'TokenizerConfigMember1',
#   :'TokenizerConfigMember2',
#   :'TokenizerConfigMember3'
# ]
```

### `openapi_discriminator_name`

Returns the discriminator's property name.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::TokenizerConfig.openapi_discriminator_name
# => :'type'
```

### `openapi_discriminator_name`

Returns the discriminator's mapping.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::TokenizerConfig.openapi_discriminator_mapping
# =>
# {
#   :'ngram' => :'TokenizerConfigMember0',
#   :'regex' => :'TokenizerConfigMember1',
#   :'simple' => :'TokenizerConfigMember2',
#   :'source_code' => :'TokenizerConfigMember3'
# }
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::TokenizerConfig.build(data)
# => #<TokenizerConfigMember0:0x00007fdd4aab02a0>

QuickwitCheminee::TokenizerConfig.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `TokenizerConfigMember0`
- `TokenizerConfigMember1`
- `TokenizerConfigMember2`
- `TokenizerConfigMember3`
- `nil` (if no type matches)

