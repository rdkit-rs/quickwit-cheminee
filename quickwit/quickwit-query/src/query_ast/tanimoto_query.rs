use serde::{Deserialize, Serialize};
use tantivy_rdkit::{FingerprintSpec, PackedFingerprint, TanimotoQuery};

use super::{BuildTantivyAst, BuildTantivyAstContext, QueryAst, TantivyQueryAst};
use crate::{InvalidQuery, NotNaNf32};

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TanimotoQueryAst {
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
            context.schema,
            &self.spec,
            fingerprint,
            self.minimum.into(),
        )
        .map_err(|error| InvalidQuery::InvalidChemistry(error.to_string()))?;
        Ok(query.into())
    }
}
