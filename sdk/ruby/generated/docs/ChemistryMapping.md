# QuickwitCheminee::ChemistryMapping

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **descriptor_layout** | [**DescriptorLayout**](DescriptorLayout.md) |  | [optional] |
| **descriptor_v1** | **Boolean** | Generate the complete Cheminee descriptor_v1 contract in process. | [optional] |
| **prepared_smiles_field** | **String** |  |  |
| **smiles_field** | **String** |  |  |
| **spec** | [**FingerprintSpec**](FingerprintSpec.md) |  |  |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::ChemistryMapping.new(
  descriptor_layout: null,
  descriptor_v1: null,
  prepared_smiles_field: null,
  smiles_field: null,
  spec: null
)
```

