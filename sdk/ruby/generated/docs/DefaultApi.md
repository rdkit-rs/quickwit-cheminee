# QuickwitCheminee::DefaultApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------ | ------------ | ----------- |
| [**cheminee_v1_basic**](DefaultApi.md#cheminee_v1_basic) | **POST** /v1/indexes/{index_id}/search/basic |  |
| [**cheminee_v1_identity**](DefaultApi.md#cheminee_v1_identity) | **POST** /v1/indexes/{index_id}/search/identity |  |
| [**cheminee_v1_similarity**](DefaultApi.md#cheminee_v1_similarity) | **POST** /v1/indexes/{index_id}/search/similarity |  |
| [**cheminee_v1_substructure**](DefaultApi.md#cheminee_v1_substructure) | **POST** /v1/indexes/{index_id}/search/substructure |  |
| [**cheminee_v1_superstructure**](DefaultApi.md#cheminee_v1_superstructure) | **POST** /v1/indexes/{index_id}/search/superstructure |  |
| [**create_index**](DefaultApi.md#create_index) | **POST** /api/v1/indexes | Creates index. |
| [**delete_index**](DefaultApi.md#delete_index) | **DELETE** /api/v1/indexes/{index_id} | Deletes index. |
| [**describe_index**](DefaultApi.md#describe_index) | **GET** /api/v1/indexes/{index_id}/describe | Describes an index. |
| [**ingest**](DefaultApi.md#ingest) | **POST** /api/v1/{index_id}/ingest | Ingest documents |
| [**ready**](DefaultApi.md#ready) | **GET** /health/readyz | Get Node Readiness |


## cheminee_v1_basic

> <BasicSearchResponse> cheminee_v1_basic(index_id, basic_search_request)



### Examples

```ruby
require 'time'
require 'quickwit-cheminee'

api_instance = QuickwitCheminee::DefaultApi.new
index_id = 'index_id_example' # String | One concrete molecule index.
basic_search_request = QuickwitCheminee::BasicSearchRequest.new # BasicSearchRequest | 

begin
  
  result = api_instance.cheminee_v1_basic(index_id, basic_search_request)
  p result
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->cheminee_v1_basic: #{e}"
end
```

#### Using the cheminee_v1_basic_with_http_info variant

This returns an Array which contains the response data, status code and headers.

> <Array(<BasicSearchResponse>, Integer, Hash)> cheminee_v1_basic_with_http_info(index_id, basic_search_request)

```ruby
begin
  
  data, status_code, headers = api_instance.cheminee_v1_basic_with_http_info(index_id, basic_search_request)
  p status_code # => 2xx
  p headers # => { ... }
  p data # => <BasicSearchResponse>
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->cheminee_v1_basic_with_http_info: #{e}"
end
```

### Parameters

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **index_id** | **String** | One concrete molecule index. |  |
| **basic_search_request** | [**BasicSearchRequest**](BasicSearchRequest.md) |  |  |

### Return type

[**BasicSearchResponse**](BasicSearchResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json


## cheminee_v1_identity

> <SimilarityResponse> cheminee_v1_identity(index_id, graph_search_request)



### Examples

```ruby
require 'time'
require 'quickwit-cheminee'

api_instance = QuickwitCheminee::DefaultApi.new
index_id = 'index_id_example' # String | One concrete molecule index.
graph_search_request = QuickwitCheminee::GraphSearchRequest.new({smiles: 'smiles_example', spec: QuickwitCheminee::FingerprintSpec.new({format: QuickwitCheminee::FingerprintFormat::MORGAN_R3_2048_LSB0_V1, preparation_id: 'preparation_id_example', rdkit_version: 'rdkit_version_example'})}) # GraphSearchRequest | 

begin
  
  result = api_instance.cheminee_v1_identity(index_id, graph_search_request)
  p result
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->cheminee_v1_identity: #{e}"
end
```

#### Using the cheminee_v1_identity_with_http_info variant

This returns an Array which contains the response data, status code and headers.

> <Array(<SimilarityResponse>, Integer, Hash)> cheminee_v1_identity_with_http_info(index_id, graph_search_request)

```ruby
begin
  
  data, status_code, headers = api_instance.cheminee_v1_identity_with_http_info(index_id, graph_search_request)
  p status_code # => 2xx
  p headers # => { ... }
  p data # => <SimilarityResponse>
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->cheminee_v1_identity_with_http_info: #{e}"
end
```

### Parameters

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **index_id** | **String** | One concrete molecule index. |  |
| **graph_search_request** | [**GraphSearchRequest**](GraphSearchRequest.md) |  |  |

### Return type

[**SimilarityResponse**](SimilarityResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json


## cheminee_v1_similarity

> <SimilarityResponse> cheminee_v1_similarity(index_id, smiles_similarity_request)



### Examples

```ruby
require 'time'
require 'quickwit-cheminee'

api_instance = QuickwitCheminee::DefaultApi.new
index_id = 'index_id_example' # String | One concrete molecule index.
smiles_similarity_request = QuickwitCheminee::SmilesSimilarityRequest.new({smiles: 'smiles_example', spec: QuickwitCheminee::FingerprintSpec.new({format: QuickwitCheminee::FingerprintFormat::MORGAN_R3_2048_LSB0_V1, preparation_id: 'preparation_id_example', rdkit_version: 'rdkit_version_example'})}) # SmilesSimilarityRequest | 

begin
  
  result = api_instance.cheminee_v1_similarity(index_id, smiles_similarity_request)
  p result
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->cheminee_v1_similarity: #{e}"
end
```

#### Using the cheminee_v1_similarity_with_http_info variant

This returns an Array which contains the response data, status code and headers.

> <Array(<SimilarityResponse>, Integer, Hash)> cheminee_v1_similarity_with_http_info(index_id, smiles_similarity_request)

```ruby
begin
  
  data, status_code, headers = api_instance.cheminee_v1_similarity_with_http_info(index_id, smiles_similarity_request)
  p status_code # => 2xx
  p headers # => { ... }
  p data # => <SimilarityResponse>
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->cheminee_v1_similarity_with_http_info: #{e}"
end
```

### Parameters

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **index_id** | **String** | One concrete molecule index. |  |
| **smiles_similarity_request** | [**SmilesSimilarityRequest**](SmilesSimilarityRequest.md) |  |  |

### Return type

[**SimilarityResponse**](SimilarityResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json


## cheminee_v1_substructure

> <SimilarityResponse> cheminee_v1_substructure(index_id, graph_search_request)



### Examples

```ruby
require 'time'
require 'quickwit-cheminee'

api_instance = QuickwitCheminee::DefaultApi.new
index_id = 'index_id_example' # String | One concrete molecule index.
graph_search_request = QuickwitCheminee::GraphSearchRequest.new({smiles: 'smiles_example', spec: QuickwitCheminee::FingerprintSpec.new({format: QuickwitCheminee::FingerprintFormat::MORGAN_R3_2048_LSB0_V1, preparation_id: 'preparation_id_example', rdkit_version: 'rdkit_version_example'})}) # GraphSearchRequest | 

begin
  
  result = api_instance.cheminee_v1_substructure(index_id, graph_search_request)
  p result
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->cheminee_v1_substructure: #{e}"
end
```

#### Using the cheminee_v1_substructure_with_http_info variant

This returns an Array which contains the response data, status code and headers.

> <Array(<SimilarityResponse>, Integer, Hash)> cheminee_v1_substructure_with_http_info(index_id, graph_search_request)

```ruby
begin
  
  data, status_code, headers = api_instance.cheminee_v1_substructure_with_http_info(index_id, graph_search_request)
  p status_code # => 2xx
  p headers # => { ... }
  p data # => <SimilarityResponse>
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->cheminee_v1_substructure_with_http_info: #{e}"
end
```

### Parameters

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **index_id** | **String** | One concrete molecule index. |  |
| **graph_search_request** | [**GraphSearchRequest**](GraphSearchRequest.md) |  |  |

### Return type

[**SimilarityResponse**](SimilarityResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json


## cheminee_v1_superstructure

> <SimilarityResponse> cheminee_v1_superstructure(index_id, graph_search_request)



### Examples

```ruby
require 'time'
require 'quickwit-cheminee'

api_instance = QuickwitCheminee::DefaultApi.new
index_id = 'index_id_example' # String | One concrete molecule index.
graph_search_request = QuickwitCheminee::GraphSearchRequest.new({smiles: 'smiles_example', spec: QuickwitCheminee::FingerprintSpec.new({format: QuickwitCheminee::FingerprintFormat::MORGAN_R3_2048_LSB0_V1, preparation_id: 'preparation_id_example', rdkit_version: 'rdkit_version_example'})}) # GraphSearchRequest | 

begin
  
  result = api_instance.cheminee_v1_superstructure(index_id, graph_search_request)
  p result
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->cheminee_v1_superstructure: #{e}"
end
```

#### Using the cheminee_v1_superstructure_with_http_info variant

This returns an Array which contains the response data, status code and headers.

> <Array(<SimilarityResponse>, Integer, Hash)> cheminee_v1_superstructure_with_http_info(index_id, graph_search_request)

```ruby
begin
  
  data, status_code, headers = api_instance.cheminee_v1_superstructure_with_http_info(index_id, graph_search_request)
  p status_code # => 2xx
  p headers # => { ... }
  p data # => <SimilarityResponse>
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->cheminee_v1_superstructure_with_http_info: #{e}"
end
```

### Parameters

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **index_id** | **String** | One concrete molecule index. |  |
| **graph_search_request** | [**GraphSearchRequest**](GraphSearchRequest.md) |  |  |

### Return type

[**SimilarityResponse**](SimilarityResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json


## create_index

> <VersionedIndexMetadata> create_index(versioned_index_config, opts)

Creates index.

### Examples

```ruby
require 'time'
require 'quickwit-cheminee'

api_instance = QuickwitCheminee::DefaultApi.new
versioned_index_config = QuickwitCheminee::VersionedIndexConfigVariant0.new({doc_mapping: QuickwitCheminee::DocMapping.new, index_id: 'index_id_example', version: '0.9'}) # VersionedIndexConfig | 
opts = {
  overwrite: true # Boolean | 
}

begin
  # Creates index.
  result = api_instance.create_index(versioned_index_config, opts)
  p result
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->create_index: #{e}"
end
```

#### Using the create_index_with_http_info variant

This returns an Array which contains the response data, status code and headers.

> <Array(<VersionedIndexMetadata>, Integer, Hash)> create_index_with_http_info(versioned_index_config, opts)

```ruby
begin
  # Creates index.
  data, status_code, headers = api_instance.create_index_with_http_info(versioned_index_config, opts)
  p status_code # => 2xx
  p headers # => { ... }
  p data # => <VersionedIndexMetadata>
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->create_index_with_http_info: #{e}"
end
```

### Parameters

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **versioned_index_config** | [**VersionedIndexConfig**](VersionedIndexConfig.md) |  |  |
| **overwrite** | **Boolean** |  | [optional] |

### Return type

[**VersionedIndexMetadata**](VersionedIndexMetadata.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json


## delete_index

> <Array<SplitInfo>> delete_index(index_id, opts)

Deletes index.

### Examples

```ruby
require 'time'
require 'quickwit-cheminee'

api_instance = QuickwitCheminee::DefaultApi.new
index_id = 'index_id_example' # String | The index ID to delete.
opts = {
  dry_run: true # Boolean | 
}

begin
  # Deletes index.
  result = api_instance.delete_index(index_id, opts)
  p result
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->delete_index: #{e}"
end
```

#### Using the delete_index_with_http_info variant

This returns an Array which contains the response data, status code and headers.

> <Array(<Array<SplitInfo>>, Integer, Hash)> delete_index_with_http_info(index_id, opts)

```ruby
begin
  # Deletes index.
  data, status_code, headers = api_instance.delete_index_with_http_info(index_id, opts)
  p status_code # => 2xx
  p headers # => { ... }
  p data # => <Array<SplitInfo>>
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->delete_index_with_http_info: #{e}"
end
```

### Parameters

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **index_id** | **String** | The index ID to delete. |  |
| **dry_run** | **Boolean** |  | [optional] |

### Return type

[**Array&lt;SplitInfo&gt;**](SplitInfo.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json


## describe_index

> <IndexStats> describe_index(index_id)

Describes an index.

### Examples

```ruby
require 'time'
require 'quickwit-cheminee'

api_instance = QuickwitCheminee::DefaultApi.new
index_id = 'index_id_example' # String | The index ID to describe.

begin
  # Describes an index.
  result = api_instance.describe_index(index_id)
  p result
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->describe_index: #{e}"
end
```

#### Using the describe_index_with_http_info variant

This returns an Array which contains the response data, status code and headers.

> <Array(<IndexStats>, Integer, Hash)> describe_index_with_http_info(index_id)

```ruby
begin
  # Describes an index.
  data, status_code, headers = api_instance.describe_index_with_http_info(index_id)
  p status_code # => 2xx
  p headers # => { ... }
  p data # => <IndexStats>
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->describe_index_with_http_info: #{e}"
end
```

### Parameters

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **index_id** | **String** | The index ID to describe. |  |

### Return type

[**IndexStats**](IndexStats.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json


## ingest

> <RestIngestResponse> ingest(index_id, body, opts)

Ingest documents

### Examples

```ruby
require 'time'
require 'quickwit-cheminee'

api_instance = QuickwitCheminee::DefaultApi.new
index_id = 'index_id_example' # String | The index ID to add docs to.
body = 'body_example' # String | Raw newline-delimited JSON documents, not a JSON-encoded string. Limited by the configured ingestion body size.
opts = {
  commit: QuickwitCheminee::CommitType::AUTO, # CommitType | Force or wait for commit at the end of the indexing operation.
  detailed_response: true # Boolean | Include per-document parse failures. Requires ingest v2; details contain original documents and must not be routinely logged.
}

begin
  # Ingest documents
  result = api_instance.ingest(index_id, body, opts)
  p result
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->ingest: #{e}"
end
```

#### Using the ingest_with_http_info variant

This returns an Array which contains the response data, status code and headers.

> <Array(<RestIngestResponse>, Integer, Hash)> ingest_with_http_info(index_id, body, opts)

```ruby
begin
  # Ingest documents
  data, status_code, headers = api_instance.ingest_with_http_info(index_id, body, opts)
  p status_code # => 2xx
  p headers # => { ... }
  p data # => <RestIngestResponse>
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->ingest_with_http_info: #{e}"
end
```

### Parameters

| Name | Type | Description | Notes |
| ---- | ---- | ----------- | ----- |
| **index_id** | **String** | The index ID to add docs to. |  |
| **body** | **String** | Raw newline-delimited JSON documents, not a JSON-encoded string. Limited by the configured ingestion body size. |  |
| **commit** | [**CommitType**](.md) | Force or wait for commit at the end of the indexing operation. | [optional] |
| **detailed_response** | **Boolean** | Include per-document parse failures. Requires ingest v2; details contain original documents and must not be routinely logged. | [optional] |

### Return type

[**RestIngestResponse**](RestIngestResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/x-ndjson
- **Accept**: application/json


## ready

> Boolean ready

Get Node Readiness

### Examples

```ruby
require 'time'
require 'quickwit-cheminee'

api_instance = QuickwitCheminee::DefaultApi.new

begin
  # Get Node Readiness
  result = api_instance.ready
  p result
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->ready: #{e}"
end
```

#### Using the ready_with_http_info variant

This returns an Array which contains the response data, status code and headers.

> <Array(Boolean, Integer, Hash)> ready_with_http_info

```ruby
begin
  # Get Node Readiness
  data, status_code, headers = api_instance.ready_with_http_info
  p status_code # => 2xx
  p headers # => { ... }
  p data # => Boolean
rescue QuickwitCheminee::ApiError => e
  puts "Error when calling DefaultApi->ready_with_http_info: #{e}"
end
```

### Parameters

This endpoint does not need any parameter.

### Return type

**Boolean**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: text/plain

