# QuickwitCheminee::TokenizerEntry

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::TokenizerEntry.openapi_one_of
# =>
# [
#   :'TokenizerEntryMember0',
#   :'TokenizerEntryMember1',
#   :'TokenizerEntryMember2',
#   :'TokenizerEntryMember3'
# ]
```

### `openapi_discriminator_name`

Returns the discriminator's property name.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::TokenizerEntry.openapi_discriminator_name
# => :'type'
```

### `openapi_discriminator_name`

Returns the discriminator's mapping.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::TokenizerEntry.openapi_discriminator_mapping
# =>
# {
#   :'ngram' => :'TokenizerEntryMember0',
#   :'regex' => :'TokenizerEntryMember1',
#   :'simple' => :'TokenizerEntryMember2',
#   :'source_code' => :'TokenizerEntryMember3'
# }
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::TokenizerEntry.build(data)
# => #<TokenizerEntryMember0:0x00007fdd4aab02a0>

QuickwitCheminee::TokenizerEntry.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `TokenizerEntryMember0`
- `TokenizerEntryMember1`
- `TokenizerEntryMember2`
- `TokenizerEntryMember3`
- `nil` (if no type matches)

