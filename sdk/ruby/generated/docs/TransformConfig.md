# QuickwitCheminee::TransformConfig

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **script** | **String** | [VRL] source code of the transform compiled to a VRL [&#x60;Program&#x60;](vrl::compiler::Program).  [VRL]: https://vector.dev/docs/reference/vrl/ |  |
| **timezone** | **String** | Timezone used in the VRL [&#x60;Program&#x60;](vrl::compiler::Program) for date and time manipulations. Defaults to &#x60;UTC&#x60; if not timezone is specified. | [optional] |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::TransformConfig.new(
  script: null,
  timezone: null
)
```

