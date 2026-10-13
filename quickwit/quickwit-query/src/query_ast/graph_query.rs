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

use serde::{Deserialize, Serialize};
use tantivy_rdkit::{FingerprintSpec, GraphPredicate, GraphRanking};

use super::{BuildTantivyAst, BuildTantivyAstContext, QueryAst, TantivyQueryAst};
use crate::InvalidQuery;

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GraphQueryAst {
    #[serde(default = "super::chemistry_match_all")]
    pub candidates: Box<QueryAst>,
    pub spec: FingerprintSpec,
    pub prepared_field: String,
    pub prepared_smiles: String,
    pub predicate: GraphPredicate,
    pub ranking: GraphRanking,
    pub use_chirality: bool,
    pub include_identity: bool,
}

impl BuildTantivyAst for GraphQueryAst {
    #[cfg(feature = "native-chemistry")]
    fn build_tantivy_ast_impl(
        &self,
        context: &BuildTantivyAstContext,
    ) -> Result<TantivyQueryAst, InvalidQuery> {
        let verifier = tantivy_rdkit_mapper::NativeGraphVerifier {
            spec: self.spec.clone(),
            prepared_smiles: self.prepared_smiles.clone(),
            predicate: self.predicate,
            ranking: self.ranking,
            use_chirality: self.use_chirality,
            include_identity: self.include_identity,
        };
        verifier
            .validate()
            .map_err(|error| InvalidQuery::InvalidChemistry(error.to_string()))?;
        let candidates = self
            .candidates
            .build_tantivy_ast_call(context)?
            .simplify()
            .into();
        let query = tantivy_rdkit::GraphQuery::new(
            candidates,
            context.schema,
            &self.spec,
            self.prepared_field.clone(),
            std::sync::Arc::new(verifier),
        )
        .map_err(|error| InvalidQuery::InvalidChemistry(error.to_string()))?;
        Ok(query.into())
    }

    #[cfg(not(feature = "native-chemistry"))]
    fn build_tantivy_ast_impl(
        &self,
        _context: &BuildTantivyAstContext,
    ) -> Result<TantivyQueryAst, InvalidQuery> {
        Err(InvalidQuery::InvalidChemistry(
            "graph search requires native-chemistry on every worker".into(),
        ))
    }
}

#[cfg(all(test, not(feature = "native-chemistry")))]
mod tests {
    use super::*;
    #[test]
    fn graph_native_unavailable_fails_even_without_schema_validation() {
        let ast = QueryAst::Graph(GraphQueryAst {
            candidates: Box::new(QueryAst::MatchAll),
            spec: FingerprintSpec {
                format: tantivy_rdkit::FingerprintFormat::MorganR3Bits2048Lsb0V1,
                rdkit_version: "2026.09.1".into(),
                preparation_id: "sanitize-only-v1".into(),
            },
            prepared_field: "prepared_smiles".into(),
            prepared_smiles: "CC".into(),
            predicate: GraphPredicate::Identity,
            ranking: GraphRanking::BestMatch,
            use_chirality: false,
            include_identity: true,
        });
        let schema = tantivy::schema::Schema::builder().build();
        let mut context = BuildTantivyAstContext::for_test(&schema);
        context.with_validation = false;
        assert!(matches!(
            ast.build_tantivy_ast_call(&context),
            Err(InvalidQuery::InvalidChemistry(_))
        ));
    }
}
