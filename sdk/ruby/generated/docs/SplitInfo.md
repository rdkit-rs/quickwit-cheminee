# QuickwitCheminee::SplitInfo

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **file_name** | **String** | The name of the split file on disk. |  |
| **file_size_bytes** | **Integer** | The size of the split file on disk in bytes. |  |
| **num_docs** | **Integer** | The number of documents in the split. |  |
| **split_id** | **String** | The split ID. |  |
| **uncompressed_docs_size_bytes** | **Integer** | The sum of the sizes of the original JSON payloads in bytes. |  |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::SplitInfo.new(
  file_name: null,
  file_size_bytes: null,
  num_docs: null,
  split_id: null,
  uncompressed_docs_size_bytes: null
)
```

