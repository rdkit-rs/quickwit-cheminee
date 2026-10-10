// Copyright 2021-Present Datadog, Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

mod smiles;
use std::sync::Arc;

use quickwit_config::validate_index_id_pattern;
use quickwit_proto::search::{SearchRequest, SortField, SortOrder, SortValue};
use quickwit_query::query_ast::{QueryAst, TanimotoQueryAst, query_ast_from_user_text};
use quickwit_search::{SearchError, SearchService};
use serde::{Deserialize, Serialize};
use smiles::SmilesSimilarityRequest;
pub use smiles::smiles_similarity_handler;
use tantivy_rdkit::{FingerprintFormat, FingerprintSpec, PackedFingerprint};
use warp::{Filter, Rejection};

use crate::rest_api_response::into_rest_api_response;
use crate::{BodyFormat, with_arg};

fn default_minimum() -> f32 {
    0.4
}
fn default_limit() -> u32 {
    100
}
fn default_filter() -> String {
    "*".to_string()
}

#[derive(Debug, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SimilarityRequest {
    pub spec: FingerprintSpec,
    #[schema(min_length = 512, max_length = 512, pattern = "^[0-9a-fA-F]{512}$")]
    pub fingerprint_hex: String,
    #[serde(default = "default_minimum")]
    #[schema(default = 0.4, minimum = 0, maximum = 1)]
    pub tanimoto_minimum: f32,
    #[serde(default = "default_limit")]
    #[schema(default = 100, minimum = 1, maximum = 10000)]
    pub result_limit: u32,
    #[serde(default = "default_filter")]
    #[schema(default = "*")]
    pub extra_query: String,
}

#[derive(Debug, Serialize, Deserialize, utoipa::ToSchema)]
pub struct SimilarityHit {
    pub record_id: String,
    #[schema(minimum = 0, maximum = 1)]
    pub score: f32,
    #[schema(value_type = Object)]
    pub document: serde_json::Value,
}

#[derive(Debug, Serialize, Deserialize, utoipa::ToSchema)]
pub struct SimilarityResponse {
    pub num_hits: u64,
    pub hits: Vec<SimilarityHit>,
    pub searched_splits: u64,
    pub elapsed_time_micros: u64,
}

#[derive(Serialize, utoipa::ToSchema)]
pub struct ChemistryError {
    pub message: String,
}

#[derive(utoipa::OpenApi)]
#[openapi(
    paths(similarity_handler, smiles::smiles_similarity_handler),
    components(schemas(
        SimilarityRequest,
        SmilesSimilarityRequest,
        FingerprintSpec,
        FingerprintFormat,
        SimilarityResponse,
        SimilarityHit,
        ChemistryError
    ))
)]
pub struct ChemineeApi;

impl SimilarityRequest {
    fn into_search_request(self, index_id: String) -> Result<SearchRequest, SearchError> {
        let invalid = |error: String| SearchError::InvalidArgument(error);
        validate_index_id_pattern(&index_id, false).map_err(|error| invalid(error.to_string()))?;
        self.spec
            .validate()
            .map_err(|error| invalid(error.to_string()))?;
        PackedFingerprint::from_hex(&self.fingerprint_hex)
            .map_err(|error| invalid(error.to_string()))?;
        if !self.tanimoto_minimum.is_finite() || !(0.0..=1.0).contains(&self.tanimoto_minimum) {
            return Err(invalid("tanimoto_minimum must be between 0 and 1".into()));
        }
        if !(1..=10_000).contains(&self.result_limit) {
            return Err(invalid("result_limit must be between 1 and 10000".into()));
        }
        let query = QueryAst::Tanimoto(TanimotoQueryAst {
            candidates: Box::new(query_ast_from_user_text(&self.extra_query, None)),
            spec: self.spec,
            fingerprint_hex: self.fingerprint_hex,
            minimum: self
                .tanimoto_minimum
                .try_into()
                .map_err(|error: &str| invalid(error.to_string()))?,
        });
        Ok(SearchRequest {
            index_id_patterns: vec![index_id],
            query_ast: serde_json::to_string(&query)
                .map_err(|error| SearchError::Internal(error.to_string()))?,
            max_hits: self.result_limit as u64,
            sort_fields: vec![
                SortField {
                    field_name: "_score".into(),
                    sort_order: SortOrder::Desc as i32,
                    sort_datetime_format: None,
                },
                SortField {
                    field_name: "record_id".into(),
                    sort_order: SortOrder::Asc as i32,
                    sort_datetime_format: None,
                },
            ],
            ..Default::default()
        })
    }
}

#[utoipa::path(
    post,
    operation_id = "chemineeSearchSimilarity",
    tag = "Cheminee",
    path = "/{index_id}/cheminee/search/similarity",
    request_body = SimilarityRequest,
    params(("index_id" = String, Path, description = "One concrete molecule index.")),
    responses(
        (status = 200, description = "Exact fingerprint top-k within the property filter; score descending, record_id ascending.", body = SimilarityResponse),
        (status = 400, description = "Invalid request, filter, or fingerprint specification.", body = ChemistryError),
        (status = 404, description = "Index not found.", body = ChemistryError),
        (status = 411, description = "Content length required.", body = ChemistryError),
        (status = 413, description = "Request exceeds 32 KiB.", body = ChemistryError),
        (status = 415, description = "JSON content type required.", body = ChemistryError),
        (status = 429, description = "Search capacity exhausted.", body = ChemistryError),
        (status = 500, description = "Internal execution failure, including no available searcher nodes.", body = ChemistryError),
        (status = 503, description = "Unavailable service or incomplete split search.", body = ChemistryError),
        (status = 504, description = "Search timed out.", body = ChemistryError)
    )
)]
pub fn similarity_handler(
    service: Arc<dyn SearchService>,
) -> impl Filter<Extract = (impl warp::Reply,), Error = Rejection> + Clone {
    warp::path!(String / "cheminee" / "search" / "similarity")
        .and(warp::post())
        .and(warp::body::content_length_limit(32 * 1024))
        .and(warp::body::json())
        .and(with_arg(service))
        .then(search)
}

async fn search(
    index_id: String,
    request: SimilarityRequest,
    service: Arc<dyn SearchService>,
) -> impl warp::Reply {
    let result: Result<SimilarityResponse, SearchError> = async {
        let response = service
            .root_search(request.into_search_request(index_id)?)
            .await?;
        if !response.failed_splits.is_empty() || !response.errors.is_empty() {
            return Err(SearchError::Unavailable(format!(
                "incomplete chemistry search: {:?} {:?}",
                response.failed_splits, response.errors
            )));
        }
        let mut hits = Vec::with_capacity(response.hits.len());
        for hit in response.hits {
            let partial = hit
                .partial_hit
                .ok_or_else(|| SearchError::Internal("missing chemistry score".into()))?;
            let score = match partial.sort_value.and_then(|value| value.sort_value) {
                Some(SortValue::F64(value)) => value as f32,
                _ => return Err(SearchError::Internal("invalid chemistry score type".into())),
            };
            let document: serde_json::Value = serde_json::from_str(&hit.json)
                .map_err(|error| SearchError::Internal(error.to_string()))?;
            let record_id = document
                .get("record_id")
                .and_then(serde_json::Value::as_u64)
                .ok_or_else(|| SearchError::Internal("record_id must be a stored u64".into()))?
                .to_string();
            hits.push(SimilarityHit {
                record_id,
                score,
                document,
            });
        }
        Ok(SimilarityResponse {
            num_hits: response.num_hits,
            hits,
            searched_splits: response.num_successful_splits,
            elapsed_time_micros: response.elapsed_time_micros,
        })
    }
    .await;
    into_rest_api_response(result, BodyFormat::default())
}

pub fn openapi_handler() -> impl Filter<Extract = (impl warp::Reply,), Error = Rejection> + Clone {
    use utoipa::OpenApi;

    use crate::openapi::OpenApiMerger;
    warp::path!("cheminee" / "openapi.json")
        .and(warp::get())
        .map(|| warp::reply::json(&ChemineeApi::openapi().with_path_prefix("/api/v1")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn body() -> serde_json::Value {
        serde_json::json!({"spec":{"format":"morgan-r3-2048-lsb0-v1","rdkit_version":"2025.03.1","preparation_id":"sanitize-only-v1"},"fingerprint_hex":format!("01{}", "00".repeat(255))})
    }

    #[test]
    fn defaults_and_worker_query_serialization() {
        let request: SimilarityRequest = serde_json::from_value(body()).unwrap();
        assert_eq!(request.tanimoto_minimum, 0.4);
        assert_eq!(request.result_limit, 100);
        let request = request.into_search_request("molecules".into()).unwrap();
        let ast: QueryAst = serde_json::from_str(&request.query_ast).unwrap();
        assert!(matches!(ast, QueryAst::Tanimoto(_)));
        assert_eq!(request.sort_fields[0].field_name, "_score");
        assert_eq!(request.sort_fields[1].field_name, "record_id");
    }

    #[test]
    fn null_unknown_and_invalid_values_are_rejected() {
        for field in [
            "spec",
            "fingerprint_hex",
            "result_limit",
            "tanimoto_minimum",
            "extra_query",
        ] {
            let mut value = body();
            value[field] = serde_json::Value::Null;
            assert!(serde_json::from_value::<SimilarityRequest>(value).is_err());
        }
        let mut value = body();
        value["unknown"] = true.into();
        assert!(serde_json::from_value::<SimilarityRequest>(value).is_err());
        for (field, value) in [
            ("result_limit", serde_json::json!(0)),
            ("result_limit", serde_json::json!(10001)),
            ("tanimoto_minimum", serde_json::json!(-0.1)),
            ("tanimoto_minimum", serde_json::json!(1.01)),
        ] {
            let mut request = body();
            request[field] = value;
            assert!(
                serde_json::from_value::<SimilarityRequest>(request)
                    .unwrap()
                    .into_search_request("molecules".into())
                    .is_err()
            );
        }
    }

    #[tokio::test]
    async fn specification_is_deterministic_and_exposes_only_similarity() {
        let first = warp::test::request()
            .path("/cheminee/openapi.json")
            .reply(&openapi_handler())
            .await;
        let second = warp::test::request()
            .path("/cheminee/openapi.json")
            .reply(&openapi_handler())
            .await;
        assert_eq!(first.body(), second.body());
        let spec: serde_json::Value = serde_json::from_slice(first.body()).unwrap();
        assert_eq!(spec["openapi"], "3.0.3");
        assert_eq!(spec["paths"].as_object().unwrap().len(), 2);
        assert_eq!(
            spec["paths"]["/api/v1/{index_id}/cheminee/search/similarity"]["post"]["operationId"],
            "chemineeSearchSimilarity"
        );
    }
}
