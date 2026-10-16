# QuickwitCheminee::MergePolicyConfig

## Class instance methods

### `openapi_one_of`

Returns the list of classes defined in oneOf.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::MergePolicyConfig.openapi_one_of
# =>
# [
#   :'MergePolicyConfigVariant0',
#   :'MergePolicyConfigVariant1',
#   :'MergePolicyConfigVariant2'
# ]
```

### `openapi_discriminator_name`

Returns the discriminator's property name.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::MergePolicyConfig.openapi_discriminator_name
# => :'type'
```

### `openapi_discriminator_name`

Returns the discriminator's mapping.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::MergePolicyConfig.openapi_discriminator_mapping
# =>
# {
#   :'limit_merge' => :'MergePolicyConfigVariant1',
#   :'no_merge' => :'MergePolicyConfigVariant0',
#   :'stable_log' => :'MergePolicyConfigVariant2'
# }
```

### build

Find the appropriate object from the `openapi_one_of` list and casts the data into it.

#### Example

```ruby
require 'quickwit-cheminee'

QuickwitCheminee::MergePolicyConfig.build(data)
# => #<MergePolicyConfigVariant0:0x00007fdd4aab02a0>

QuickwitCheminee::MergePolicyConfig.build(data_that_doesnt_match)
# => nil
```

#### Parameters

| Name | Type | Description |
| ---- | ---- | ----------- |
| **data** | **Mixed** | data to be matched against the list of oneOf items |

#### Return type

- `MergePolicyConfigVariant0`
- `MergePolicyConfigVariant1`
- `MergePolicyConfigVariant2`
- `nil` (if no type matches)

