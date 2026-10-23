# QuickwitCheminee::IndexingSettings

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **commit_timeout_secs** | **Integer** |  | [optional][default to 60] |
| **docstore_blocksize** | **Integer** |  | [optional][default to 1000000] |
| **docstore_compression_level** | **Integer** |  | [optional][default to 8] |
| **merge_policy** | [**MergePolicyConfig**](MergePolicyConfig.md) |  | [optional] |
| **resources** | [**IndexingResources**](IndexingResources.md) |  | [optional] |
| **split_num_docs_target** | **Integer** | The merge policy aims to eventually produce mature splits that have a larger size but are within close range of &#x60;split_num_docs_target&#x60;.  In other words, splits that contain a number of documents greater than or equal to &#x60;split_num_docs_target&#x60; are considered mature and never merged. | [optional] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::IndexingSettings.new(
  commit_timeout_secs: null,
  docstore_blocksize: null,
  docstore_compression_level: null,
  merge_policy: null,
  resources: null,
  split_num_docs_target: null
)
```

