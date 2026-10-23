# QuickwitCheminee::DocMapping

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **chemistry** | [**ChemistryMapping**](ChemistryMapping.md) |  | [optional] |
| **doc_mapping_uid** | **String** | Unique identifier for a document mapping. | [optional] |
| **dynamic_mapping** | [**QuickwitJsonOptions**](QuickwitJsonOptions.md) |  | [optional] |
| **field_mappings** | [**Array&lt;FieldMappingEntryForSerialization&gt;**](FieldMappingEntryForSerialization.md) | Defines the schema of ingested documents and describes how each field value should be parsed, tokenized, indexed, and stored. | [optional] |
| **index_field_presence** | **Boolean** | Whether to record the presence of the fields of each indexed document to allow &#x60;exists&#x60; queries. | [optional] |
| **max_num_partitions** | **Integer** | The maximum number of partitions that an indexer can generate. | [optional] |
| **mode** | [**ModeType**](ModeType.md) |  | [optional] |
| **partition_key** | **String** | Expresses via a \&quot;mini-DSL\&quot; how to route documents to split partitions. | [optional] |
| **store_document_size** | **Boolean** | Whether to record and store the size (bytes) of each ingested document in a fast field. | [optional] |
| **store_source** | **Boolean** | Whether to store the original source documents in the doc store. | [optional] |
| **tag_fields** | **Array&lt;String&gt;** | Declares the low cardinality fields for which the values ​​are recorded directly in the splits metadata. | [optional] |
| **timestamp_field** | **String** | Declares the field which contains the date or timestamp at which the document was emitted. | [optional] |
| **tokenizers** | [**Array&lt;TokenizerEntry&gt;**](TokenizerEntry.md) | A set of additional user-defined tokenizers to be used during indexing. | [optional] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::DocMapping.new(
  chemistry: null,
  doc_mapping_uid: null,
  dynamic_mapping: null,
  field_mappings: null,
  index_field_presence: null,
  max_num_partitions: null,
  mode: null,
  partition_key: null,
  store_document_size: null,
  store_source: null,
  tag_fields: null,
  timestamp_field: null,
  tokenizers: null
)
```

