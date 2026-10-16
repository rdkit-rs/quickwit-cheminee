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
use tantivy_rdkit::{FingerprintSpec, PackedFingerprint, TanimotoQuery};

use super::{BuildTantivyAst, BuildTantivyAstContext, QueryAst, TantivyQueryAst};
use crate::{InvalidQuery, NotNaNf32};

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TanimotoQueryAst {
    #[serde(default = "super::chemistry_match_all")]
    pub candidates: Box<QueryAst>,
    pub spec: FingerprintSpec,
    pub fingerprint_hex: String,
    pub minimum: NotNaNf32,
}

impl BuildTantivyAst for TanimotoQueryAst {
    fn build_tantivy_ast_impl(
        &self,
        context: &BuildTantivyAstContext,
    ) -> Result<TantivyQueryAst, InvalidQuery> {
        let candidates = self
            .candidates
            .build_tantivy_ast_call(context)?
            .simplify()
            .into();
        let fingerprint = PackedFingerprint::from_hex(&self.fingerprint_hex)
            .map_err(|error| InvalidQuery::InvalidChemistry(error.to_string()))?;
        let query = TanimotoQuery::new(
            candidates,
            context.chemistry_schema,
            &self.spec,
            fingerprint,
            self.minimum.into(),
        )
        .map_err(|error| InvalidQuery::InvalidChemistry(error.to_string()))?;
        Ok(query.into())
    }
}
