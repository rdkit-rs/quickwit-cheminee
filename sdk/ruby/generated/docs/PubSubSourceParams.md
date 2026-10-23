# QuickwitCheminee::PubSubSourceParams

## Properties

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **credentials_file** | **String** | GCP service account credentials (&#x60;None&#x60; will use default via GOOGLE_APPLICATION_CREDENTIALS) Path to a google_cloud_auth::credentials::CredentialsFile serialized in JSON. See also &#x60;&lt;https://cloud.google.com/docs/authentication/application-default-credentials&gt;&#x60; and &#x60;&lt;https://github.com/yoshidan/google-cloud-rust/tree/main/pubsub#automatically&gt;&#x60; and &#x60;&lt;https://docs.rs/google-cloud-auth/0.12.0/google_cloud_auth/credentials/struct.CredentialsFile.html&gt;&#x60;. | [optional] |
| **enable_backfill_mode** | **Boolean** | When backfill mode is enabled, the source exits after reaching the end of the topic. | [optional] |
| **max_messages_per_pull** | **Integer** | Maximum number of messages returned by a pull request (default 1,000) | [optional] |
| **project_id** | **String** | GCP project ID (Defaults to credentials file project ID). | [optional] |
| **subscription** | **String** | Name of the subscription that the source consumes. |  |

## Example

```ruby
require 'quickwit-cheminee'

instance = QuickwitCheminee::PubSubSourceParams.new(
  credentials_file: null,
  enable_backfill_mode: null,
  max_messages_per_pull: null,
  project_id: null,
  subscription: null
)
```

