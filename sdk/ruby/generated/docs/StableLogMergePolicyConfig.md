# QuickwitCheminee::StableLogMergePolicyConfig

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **maturation_period** | **String** | Duration relative to &#x60;split.created_timestamp&#x60; after which a split becomes mature. If &#x60;now() &gt;&#x3D; split.created_timestamp + maturation_period&#x60; then the split is mature. | [optional] |
| **max_merge_factor** | **Integer** | Maximum number of splits that can be merged together in a single merge operation. | [optional] |
| **merge_factor** | **Integer** | Number of splits to merge together in a single merge operation. | [optional] |
| **min_level_num_docs** | **Integer** | Number of docs below which all splits are considered as belonging to the same level. | [optional] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::StableLogMergePolicyConfig.new(
  maturation_period: null,
  max_merge_factor: null,
  merge_factor: null,
  min_level_num_docs: null
)
```

