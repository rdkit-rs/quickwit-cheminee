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

use quickwit_search::{SearchError, SearchService};
use serde::{Deserialize, Serialize};
use tantivy_rdkit::FingerprintSpec;
use warp::{Filter, Rejection, Reply};

use super::{
    SimilarityRequest, SimilarityResponse, default_filter, default_limit,
    default_minimum,
};
use crate::rest_api_response::into_rest_api_response;
use crate::{BodyFormat, with_arg};

#[derive(Debug, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SmilesSimilarityRequest {
    pub spec: FingerprintSpec,
    #[schema(min_length = 1)]
    pub smiles: String,
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

impl SmilesSimilarityRequest {
    #[cfg(feature = "native-chemistry")]
    fn prepare(self) -> Result<SimilarityRequest, SearchError> {
        let prepared =
            tantivy_rdkit_mapper::PreparedMolecule::from_smiles(&self.smiles, &self.spec)
                .map_err(|error| SearchError::InvalidArgument(error.to_string()))?;
        Ok(SimilarityRequest {
            spec: self.spec,
            fingerprint_hex: prepared.fingerprint.to_hex(),
            tanimoto_minimum: self.tanimoto_minimum,
            result_limit: self.result_limit,
            extra_query: self.extra_query,
        })
    }

    #[cfg(not(feature = "native-chemistry"))]
    fn prepare(self) -> Result<SimilarityRequest, SearchError> {
        Err(SearchError::InvalidArgument(
            "SMILES queries require a Quickwit build with the native-chemistry feature".into(),
        ))
    }
}

#[utoipa::path(
    post,
    operation_id = "chemineeSearchSimilaritySmiles",
    tag = "Cheminee",
    path = "/{index_id}/cheminee/search/similarity/smiles",
    request_body = SmilesSimilarityRequest,
    params(("index_id" = String, Path, description = "One concrete molecule index.")),
    responses(
        (status = 200, description = "SMILES prepared once at the root; packed fingerprints scored by leaf workers.", body = SimilarityResponse),
        (status = 400, description = "Invalid SMILES, request or contract; native preparation unavailable.", body = ChemistryError),
        (status = 404, description = "Index not found.", body = ChemistryError),
        (status = 411, description = "Content length required.", body = ChemistryError),
        (status = 413, description = "Request exceeds 32 KiB.", body = ChemistryError),
        (status = 415, description = "JSON content type required.", body = ChemistryError),
        (status = 429, description = "Search capacity exhausted.", body = ChemistryError),
        (status = 500, description = "Internal execution failure.", body = ChemistryError),
        (status = 503, description = "Unavailable service or incomplete split search.", body = ChemistryError),
        (status = 504, description = "Search timed out.", body = ChemistryError)
    )
)]
pub fn smiles_similarity_handler(
    service: Arc<dyn SearchService>,
) -> impl Filter<Extract = (impl Reply,), Error = Rejection> + Clone {
    warp::path!(String / "cheminee" / "search" / "similarity" / "smiles")
        .and(warp::post())
        .and(warp::body::content_length_limit(32 * 1024))
        .and(warp::body::json())
        .and(with_arg(service))
        .then(search_smiles)
}

async fn search_smiles(
    index_id: String,
    request: SmilesSimilarityRequest,
    service: Arc<dyn SearchService>,
) -> warp::reply::Response {
    let prepared = quickwit_common::thread_pool::run_cpu_intensive(move || request.prepare()).await;
    match prepared {
        Ok(Ok(packed)) => super::search(index_id, packed, service)
            .await
            .into_response(),
        Ok(Err(error)) => into_rest_api_response(
            Result::<SimilarityResponse, _>::Err(error),
            BodyFormat::default(),
        )
        .into_response(),
        Err(error) => into_rest_api_response(
            Result::<SimilarityResponse, _>::Err(SearchError::Internal(error.to_string())),
            BodyFormat::default(),
        )
        .into_response(),
    }
}

#[cfg(all(test, feature = "native-chemistry"))]
mod tests {
    use quickwit_query::query_ast::QueryAst;

    use super::*;

    #[test]
    fn native_query_contains_only_packed_fingerprint() {
        let request: SmilesSimilarityRequest = serde_json::from_value(
            serde_json::json!({"spec": tantivy_rdkit_mapper::fingerprint_spec(), "smiles": "CCO"}),
        )
        .unwrap();
        let packed = request
            .prepare()
            .unwrap()
            .into_search_request("molecules".into())
            .unwrap();
        assert!(!packed.query_ast.contains("smiles"));
        let QueryAst::Tanimoto(query) = serde_json::from_str(&packed.query_ast).unwrap() else {
            panic!()
        };
        let indexed =
            tantivy_rdkit_mapper::PreparedMolecule::from_smiles("CCO", &query.spec).unwrap();
        assert_eq!(query.fingerprint_hex, indexed.fingerprint.to_hex());
    }

    #[tokio::test]
    async fn invalid_smiles_returns_typed_http_error_without_search() {
        let service = Arc::new(quickwit_search::MockSearchService::new());
        let response = warp::test::request().method("POST").path("/molecules/cheminee/search/similarity/smiles")
            .json(&serde_json::json!({"spec": tantivy_rdkit_mapper::fingerprint_spec(), "smiles": "bad-smiles"}))
            .reply(&smiles_similarity_handler(service)).await;
        assert_eq!(response.status(), 400);
        let error: serde_json::Value = serde_json::from_slice(response.body()).unwrap();
        assert!(
            error["message"]
                .as_str()
                .unwrap()
                .contains("invalid SMILES")
        );
    }
}
