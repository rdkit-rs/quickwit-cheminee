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

use std::sync::Arc;

use quickwit_config::validate_index_id_pattern;
use quickwit_proto::search::{SearchRequest, SearchResponse, SortField, SortOrder};
use quickwit_query::query_ast::{BoolQuery, QueryAst, query_ast_from_user_text};
use quickwit_search::{SearchError, SearchService};
use serde::{Deserialize, Serialize};
use tantivy_rdkit::{FingerprintSpec, GraphPredicate, GraphRanking};
use warp::{Filter, Rejection, Reply};

use super::smiles::SmilesSimilarityRequest;
use super::{ChemistryError, SimilarityResponse, default_filter, default_limit};
use crate::rest_api_response::into_rest_api_response;
use crate::{BodyFormat, with_arg};

fn prepared_field() -> String {
    "prepared_smiles".into()
}
fn include_identity() -> bool {
    true
}

#[derive(Debug, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct GraphSearchRequest {
    pub spec: FingerprintSpec,
    pub smiles: String,
    #[serde(default = "prepared_field")]
    pub prepared_smiles_field: String,
    #[serde(default)]
    pub use_chirality: bool,
    #[serde(default = "include_identity")]
    pub include_identity: bool,
    #[serde(default)]
    pub ranking: GraphRanking,
    #[serde(default = "default_limit")]
    #[schema(default = 100, minimum = 1, maximum = 10000)]
    pub result_limit: u32,
    #[serde(default = "default_filter")]
    pub extra_query: String,
}

#[derive(Debug, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct BasicSearchRequest {
    #[serde(default = "default_filter")]
    pub query: String,
    #[serde(default = "default_filter")]
    pub extra_query: String,
    #[serde(default = "default_limit")]
    #[schema(default = 100, minimum = 1, maximum = 10000)]
    pub result_limit: u32,
    #[serde(default)]
    pub sort_field: Option<String>,
    #[serde(default)]
    pub sort_ascending: bool,
}

#[derive(Debug, Serialize, Deserialize, utoipa::ToSchema)]
pub struct BasicSearchResponse {
    pub num_hits: u64,
    #[schema(value_type = Vec<Object>)]
    pub hits: Vec<serde_json::Value>,
    pub searched_splits: u64,
    pub elapsed_time_micros: u64,
}

fn validate(index_id: &str, limit: u32) -> Result<(), SearchError> {
    validate_index_id_pattern(index_id, false)
        .map_err(|e| SearchError::InvalidArgument(e.to_string()))?;
    if !(1..=10_000).contains(&limit) {
        return Err(SearchError::InvalidArgument(
            "result_limit must be between 1 and 10000".into(),
        ));
    }
    Ok(())
}

fn request(
    index_id: String,
    ast: QueryAst,
    limit: u32,
    field: &str,
    ascending: bool,
) -> Result<SearchRequest, SearchError> {
    validate(&index_id, limit)?;
    let mut sort_fields = vec![SortField {
        field_name: field.into(),
        sort_order: if ascending {
            SortOrder::Asc
        } else {
            SortOrder::Desc
        } as i32,
        sort_datetime_format: None,
    }];
    if field != "record_id" {
        sort_fields.push(SortField {
            field_name: "record_id".into(),
            sort_order: SortOrder::Asc as i32,
            sort_datetime_format: None,
        });
    }
    Ok(SearchRequest {
        index_id_patterns: vec![index_id],
        query_ast: serde_json::to_string(&ast).map_err(|e| SearchError::Internal(e.to_string()))?,
        max_hits: limit as u64,
        sort_fields,
        ..Default::default()
    })
}

impl GraphSearchRequest {
    #[cfg(feature = "native-chemistry")]
    fn prepare(
        self,
        index_id: String,
        predicate: GraphPredicate,
    ) -> Result<SearchRequest, SearchError> {
        validate(&index_id, self.result_limit)?;
        let prepared =
            tantivy_rdkit_mapper::PreparedMolecule::from_smiles(&self.smiles, &self.spec)
                .map_err(|e| SearchError::InvalidArgument(e.to_string()))?;
        request(
            index_id,
            QueryAst::Graph(quickwit_query::query_ast::GraphQueryAst {
                candidates: Box::new(query_ast_from_user_text(&self.extra_query, None)),
                spec: self.spec,
                prepared_field: self.prepared_smiles_field,
                prepared_smiles: prepared.smiles,
                predicate,
                ranking: self.ranking,
                use_chirality: self.use_chirality,
                include_identity: self.include_identity,
            }),
            self.result_limit,
            "_score",
            false,
        )
    }

    #[cfg(not(feature = "native-chemistry"))]
    fn prepare(
        self,
        _index_id: String,
        _predicate: GraphPredicate,
    ) -> Result<SearchRequest, SearchError> {
        Err(SearchError::InvalidArgument(
            "graph search requires native-chemistry on root and every worker".into(),
        ))
    }
}

fn complete(response: &SearchResponse) -> Result<(), SearchError> {
    if !response.failed_splits.is_empty() || !response.errors.is_empty() {
        return Err(SearchError::Unavailable(format!(
            "incomplete chemistry search: {:?} {:?}",
            response.failed_splits, response.errors
        )));
    }
    Ok(())
}

async fn graph_search(
    index_id: String,
    body: GraphSearchRequest,
    predicate: GraphPredicate,
    service: Arc<dyn SearchService>,
) -> warp::reply::Response {
    let result: Result<SimilarityResponse, SearchError> = async {
        let prepared = quickwit_common::thread_pool::run_cpu_intensive(move || {
            body.prepare(index_id, predicate)
        })
        .await
        .map_err(|e| SearchError::Internal(e.to_string()))??;
        super::chemistry_response(service.root_search(prepared).await?)
    }
    .await;
    into_rest_api_response(result, BodyFormat::default()).into_response()
}

async fn basic_search(
    index_id: String,
    body: BasicSearchRequest,
    service: Arc<dyn SearchService>,
) -> warp::reply::Response {
    let result: Result<BasicSearchResponse, SearchError> = async {
        let ast = QueryAst::Bool(BoolQuery {
            must: vec![query_ast_from_user_text(&body.query, None)],
            filter: vec![query_ast_from_user_text(&body.extra_query, None)],
            ..Default::default()
        });
        let prepared = request(
            index_id,
            ast,
            body.result_limit,
            body.sort_field.as_deref().unwrap_or("_score"),
            body.sort_ascending,
        )?;
        let response = service.root_search(prepared).await?;
        complete(&response)?;
        let hits = response
            .hits
            .iter()
            .map(|hit| serde_json::from_str(&hit.json))
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| SearchError::Internal(e.to_string()))?;
        Ok(BasicSearchResponse {
            num_hits: response.num_hits,
            hits,
            searched_splits: response.num_successful_splits,
            elapsed_time_micros: response.elapsed_time_micros,
        })
    }
    .await;
    into_rest_api_response(result, BodyFormat::default()).into_response()
}

#[utoipa::path(
    post, operation_id = "chemineeV1Basic", tag = "Cheminee",
    path = "/indexes/{index_id}/search/basic", request_body = BasicSearchRequest,
    params(("index_id" = String, Path, description = "One concrete molecule index.")),
    responses(
        (status = 200, description = "Complete distributed results with stable record_id ties.", body = BasicSearchResponse),
        (status = 400, description = "Invalid input, filter, contract or native feature unavailable.", body = ChemistryError),
        (status = 404, description = "Index not found.", body = ChemistryError),
        (status = 411, description = "Content length required.", body = ChemistryError),
        (status = 413, description = "Request exceeds 32 KiB.", body = ChemistryError),
        (status = 415, description = "JSON required.", body = ChemistryError),
        (status = 429, description = "Capacity exhausted.", body = ChemistryError),
        (status = 500, description = "Internal execution failure.", body = ChemistryError),
        (status = 503, description = "Unavailable or incomplete split search.", body = ChemistryError),
        (status = 504, description = "Search timed out.", body = ChemistryError)
    )
)]
pub fn basic_handler(
    service: Arc<dyn SearchService>,
) -> impl Filter<Extract = (impl Reply,), Error = Rejection> + Clone {
    warp::path!("indexes" / String / "search" / "basic")
        .and(warp::post())
        .and(warp::body::content_length_limit(32 * 1024))
        .and(warp::body::json())
        .and(with_arg(service))
        .then(basic_search)
}

#[utoipa::path(
    post, operation_id = "chemineeV1Identity", tag = "Cheminee",
    path = "/indexes/{index_id}/search/identity", request_body = GraphSearchRequest,
    params(("index_id" = String, Path, description = "One concrete molecule index.")),
    responses(
        (status = 200, description = "Complete distributed results with stable record_id ties.", body = SimilarityResponse),
        (status = 400, description = "Invalid input, filter, contract or native feature unavailable.", body = ChemistryError),
        (status = 404, description = "Index not found.", body = ChemistryError),
        (status = 411, description = "Content length required.", body = ChemistryError),
        (status = 413, description = "Request exceeds 32 KiB.", body = ChemistryError),
        (status = 415, description = "JSON required.", body = ChemistryError),
        (status = 429, description = "Capacity exhausted.", body = ChemistryError),
        (status = 500, description = "Internal execution failure.", body = ChemistryError),
        (status = 503, description = "Unavailable or incomplete split search.", body = ChemistryError),
        (status = 504, description = "Search timed out.", body = ChemistryError)
    )
)]
pub fn identity_handler(
    service: Arc<dyn SearchService>,
) -> impl Filter<Extract = (impl Reply,), Error = Rejection> + Clone {
    warp::path!("indexes" / String / "search" / "identity")
        .and(warp::post())
        .and(warp::body::content_length_limit(32 * 1024))
        .and(warp::body::json())
        .and(with_arg(service))
        .then(|index_id, body, service| {
            graph_search(index_id, body, GraphPredicate::Identity, service)
        })
}

#[utoipa::path(
    post, operation_id = "chemineeV1Substructure", tag = "Cheminee",
    path = "/indexes/{index_id}/search/substructure", request_body = GraphSearchRequest,
    params(("index_id" = String, Path, description = "One concrete molecule index.")),
    responses(
        (status = 200, description = "Complete distributed results with stable record_id ties.", body = SimilarityResponse),
        (status = 400, description = "Invalid input, filter, contract or native feature unavailable.", body = ChemistryError),
        (status = 404, description = "Index not found.", body = ChemistryError),
        (status = 411, description = "Content length required.", body = ChemistryError),
        (status = 413, description = "Request exceeds 32 KiB.", body = ChemistryError),
        (status = 415, description = "JSON required.", body = ChemistryError),
        (status = 429, description = "Capacity exhausted.", body = ChemistryError),
        (status = 500, description = "Internal execution failure.", body = ChemistryError),
        (status = 503, description = "Unavailable or incomplete split search.", body = ChemistryError),
        (status = 504, description = "Search timed out.", body = ChemistryError)
    )
)]
pub fn substructure_handler(
    service: Arc<dyn SearchService>,
) -> impl Filter<Extract = (impl Reply,), Error = Rejection> + Clone {
    warp::path!("indexes" / String / "search" / "substructure")
        .and(warp::post())
        .and(warp::body::content_length_limit(32 * 1024))
        .and(warp::body::json())
        .and(with_arg(service))
        .then(|index_id, body, service| {
            graph_search(index_id, body, GraphPredicate::Substructure, service)
        })
}

#[utoipa::path(
    post, operation_id = "chemineeV1Superstructure", tag = "Cheminee",
    path = "/indexes/{index_id}/search/superstructure", request_body = GraphSearchRequest,
    params(("index_id" = String, Path, description = "One concrete molecule index.")),
    responses(
        (status = 200, description = "Complete distributed results with stable record_id ties.", body = SimilarityResponse),
        (status = 400, description = "Invalid input, filter, contract or native feature unavailable.", body = ChemistryError),
        (status = 404, description = "Index not found.", body = ChemistryError),
        (status = 411, description = "Content length required.", body = ChemistryError),
        (status = 413, description = "Request exceeds 32 KiB.", body = ChemistryError),
        (status = 415, description = "JSON required.", body = ChemistryError),
        (status = 429, description = "Capacity exhausted.", body = ChemistryError),
        (status = 500, description = "Internal execution failure.", body = ChemistryError),
        (status = 503, description = "Unavailable or incomplete split search.", body = ChemistryError),
        (status = 504, description = "Search timed out.", body = ChemistryError)
    )
)]
pub fn superstructure_handler(
    service: Arc<dyn SearchService>,
) -> impl Filter<Extract = (impl Reply,), Error = Rejection> + Clone {
    warp::path!("indexes" / String / "search" / "superstructure")
        .and(warp::post())
        .and(warp::body::content_length_limit(32 * 1024))
        .and(warp::body::json())
        .and(with_arg(service))
        .then(|index_id, body, service| {
            graph_search(index_id, body, GraphPredicate::Superstructure, service)
        })
}

#[utoipa::path(
    post, operation_id = "chemineeV1Similarity", tag = "Cheminee",
    path = "/indexes/{index_id}/search/similarity", request_body = SmilesSimilarityRequest,
    params(("index_id" = String, Path, description = "One concrete molecule index.")),
    responses(
        (status = 200, description = "Complete distributed results with stable record_id ties.", body = SimilarityResponse),
        (status = 400, description = "Invalid input, filter, contract or native feature unavailable.", body = ChemistryError),
        (status = 404, description = "Index not found.", body = ChemistryError),
        (status = 411, description = "Content length required.", body = ChemistryError),
        (status = 413, description = "Request exceeds 32 KiB.", body = ChemistryError),
        (status = 415, description = "JSON required.", body = ChemistryError),
        (status = 429, description = "Capacity exhausted.", body = ChemistryError),
        (status = 500, description = "Internal execution failure.", body = ChemistryError),
        (status = 503, description = "Unavailable or incomplete split search.", body = ChemistryError),
        (status = 504, description = "Search timed out.", body = ChemistryError)
    )
)]
pub fn similarity_handler(
    service: Arc<dyn SearchService>,
) -> impl Filter<Extract = (impl Reply,), Error = Rejection> + Clone {
    warp::path!("indexes" / String / "search" / "similarity")
        .and(warp::post())
        .and(warp::body::content_length_limit(32 * 1024))
        .and(warp::body::json())
        .and(with_arg(service))
        .then(super::smiles::search_smiles)
}

#[derive(utoipa::OpenApi)]
#[openapi(
    paths(
        basic_handler,
        identity_handler,
        substructure_handler,
        superstructure_handler,
        similarity_handler
    ),
    components(schemas(
        BasicSearchRequest,
        BasicSearchResponse,
        GraphSearchRequest,
        GraphRanking,
        SmilesSimilarityRequest,
        tantivy_rdkit::FingerprintSpec,
        tantivy_rdkit::FingerprintFormat,
        SimilarityResponse,
        super::SimilarityHit,
        ChemistryError
    ))
)]
pub struct ChemineeV1Api;

pub fn routes(
    service: Arc<dyn SearchService>,
) -> impl Filter<Extract = (impl Reply,), Error = Rejection> + Clone {
    use utoipa::OpenApi;

    use crate::openapi::OpenApiMerger;
    warp::path("v1")
        .and(
            basic_handler(service.clone())
                .or(identity_handler(service.clone()))
                .or(substructure_handler(service.clone()))
                .or(superstructure_handler(service.clone()))
                .or(similarity_handler(service))
                .or(warp::path!("openapi.json")
                    .and(warp::get())
                    .map(|| warp::reply::json(&ChemineeV1Api::openapi().with_path_prefix("/v1")))),
        )
        .recover(crate::rest::recover_fn)
        .boxed()
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    fn body() -> serde_json::Value {
        json!({"spec":{"format":"morgan-r3-2048-lsb0-v1","rdkit_version":"2026.09.1","preparation_id":"sanitize-only-v1"},"smiles":"CCO"})
    }

    #[tokio::test]
    async fn five_routes_validate_limits_and_unknown_fields() {
        for kind in [
            "basic",
            "identity",
            "substructure",
            "superstructure",
            "similarity",
        ] {
            for key in ["result_limit", "unknown"] {
                let mut value = if kind == "basic" {
                    json!({"query":"*"})
                } else {
                    body()
                };
                value[key] = json!(0);
                let response = warp::test::request()
                    .method("POST")
                    .path(&format!("/v1/indexes/molecules/search/{kind}"))
                    .json(&value)
                    .reply(&routes(Arc::new(quickwit_search::MockSearchService::new())))
                    .await;
                assert_eq!(response.status(), 400, "{kind}: {:?}", response.body());
            }
        }
    }

    #[cfg(feature = "native-chemistry")]
    #[tokio::test]
    async fn graph_routes_dispatch_predicates_filter_and_stable_sort() {
        for (kind, predicate) in [
            ("identity", GraphPredicate::Identity),
            ("substructure", GraphPredicate::Substructure),
            ("superstructure", GraphPredicate::Superstructure),
        ] {
            let mut service = quickwit_search::MockSearchService::new();
            service
                .expect_root_search()
                .times(1)
                .returning(move |request| {
                    assert_eq!(request.index_id_patterns, ["molecules"]);
                    assert_eq!(request.sort_fields[0].field_name, "_score");
                    assert_eq!(request.sort_fields[1].field_name, "record_id");
                    let QueryAst::Graph(graph) = serde_json::from_str(&request.query_ast).unwrap()
                    else {
                        panic!()
                    };
                    assert_eq!(graph.predicate, predicate);
                    assert!(matches!(*graph.candidates, QueryAst::UserInput(_)));
                    Ok(SearchResponse {
                        num_hits: 42,
                        num_successful_splits: 3,
                        ..Default::default()
                    })
                });
            let response = warp::test::request()
                .method("POST")
                .path(&format!("/v1/indexes/molecules/search/{kind}"))
                .json(&body())
                .reply(&routes(Arc::new(service)))
                .await;
            assert_eq!(response.status(), 200, "{:?}", response.body());
            let response: serde_json::Value = serde_json::from_slice(response.body()).unwrap();
            assert_eq!(response["num_hits"], 42);
            assert_eq!(response["searched_splits"], 3);
        }
    }

    #[tokio::test]
    async fn basic_preserves_filter_sort_and_reports_incomplete_search() {
        let mut service = quickwit_search::MockSearchService::new();
        service.expect_root_search().times(1).returning(|request| {
            assert_eq!(request.sort_fields[0].field_name, "mass");
            assert_eq!(request.sort_fields[0].sort_order, SortOrder::Asc as i32);
            assert_eq!(request.sort_fields[1].field_name, "record_id");
            let QueryAst::Bool(ast) = serde_json::from_str(&request.query_ast).unwrap() else {
                panic!()
            };
            assert_eq!(ast.must.len(), 1);
            assert_eq!(ast.filter.len(), 1);
            Ok(SearchResponse {
                errors: vec!["incomplete leaf".into()],
                ..Default::default()
            })
        });
        let response = warp::test::request().method("POST").path("/v1/indexes/molecules/search/basic")
            .json(&json!({"query":"name:ethanol","extra_query":"family:public","sort_field":"mass","sort_ascending":true}))
            .reply(&routes(Arc::new(service))).await;
        assert_eq!(response.status(), 503);
    }

    #[tokio::test]
    async fn v1_schema_has_all_routes() {
        let response = warp::test::request()
            .path("/v1/openapi.json")
            .reply(&routes(Arc::new(quickwit_search::MockSearchService::new())))
            .await;
        let schema: serde_json::Value = serde_json::from_slice(response.body()).unwrap();
        assert_eq!(schema["paths"].as_object().unwrap().len(), 5);
        for kind in [
            "basic",
            "identity",
            "substructure",
            "superstructure",
            "similarity",
        ] {
            assert!(
                schema["paths"][format!("/v1/indexes/{{index_id}}/search/{kind}")]["post"]
                    ["responses"]["400"]
                    .is_object()
            );
        }
    }
}
