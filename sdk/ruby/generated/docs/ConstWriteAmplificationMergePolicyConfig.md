# QuickwitCheminee::ConstWriteAmplificationMergePolicyConfig

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **maturation_period** | **String** | Duration relative to &#x60;split.created_timestamp&#x60; after which a split becomes mature. If &#x60;now() &gt;&#x3D; split.created_timestamp + maturation_period&#x60; then the split is considered mature. | [optional] |
| **max_finalize_merge_operations** | **Integer** |  | [optional] |
| **max_finalize_split_num_docs** | **Integer** | Splits with a number of docs higher than &#x60;max_finalize_split_num_docs&#x60; will not be considered for finalize split merge operations. | [optional] |
| **max_merge_factor** | **Integer** | Maximum number of splits that can be merged together in a single merge operation. | [optional] |
| **max_merge_ops** | **Integer** | Maximum number of merges that a given split should undergo. | [optional] |
| **merge_factor** | **Integer** | Number of splits to merge together in a single merge operation. | [optional] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::ConstWriteAmplificationMergePolicyConfig.new(
  maturation_period: null,
  max_finalize_merge_operations: null,
  max_finalize_split_num_docs: null,
  max_merge_factor: null,
  max_merge_ops: null,
  merge_factor: null
)
```

