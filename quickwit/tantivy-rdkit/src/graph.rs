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

use std::collections::HashMap;
use std::sync::Arc;

use serde::{Deserialize, Serialize};
use tantivy::query::{EnableScoring, Explanation, Query, Scorer, Weight};
use tantivy::schema::{FieldType, Schema};
use tantivy::{DocId, DocSet, Score, SegmentReader, TERMINATED, Term};

use crate::candidate_scores::CandidateScores;
use crate::{FingerprintSpec, MoleculeFields, invalid};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "openapi", derive(utoipa::ToSchema))]
#[serde(rename_all = "snake_case")]
pub enum GraphPredicate {
    Identity,
    Substructure,
    Superstructure,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "openapi", derive(utoipa::ToSchema))]
#[serde(rename_all = "snake_case")]
pub enum GraphRanking {
    #[default]
    BestMatch,
    FewestExtraHeavyAtoms,
    GreatestQueryCoverage,
    StableId,
}

pub trait MoleculeMatcher {
    fn score(&mut self, prepared_smiles: &str) -> tantivy::Result<Option<f32>>;
}

pub trait GraphVerifier: std::fmt::Debug + Send + Sync {
    fn matcher(&self) -> tantivy::Result<Box<dyn MoleculeMatcher>>;
}

#[derive(Debug)]
pub struct GraphQuery {
    candidates: Box<dyn Query>,
    prepared_field: String,
    spec: FingerprintSpec,
    verifier: Arc<dyn GraphVerifier>,
}

impl Clone for GraphQuery {
    fn clone(&self) -> Self {
        Self {
            candidates: self.candidates.box_clone(),
            prepared_field: self.prepared_field.clone(),
            spec: self.spec.clone(),
            verifier: self.verifier.clone(),
        }
    }
}

impl GraphQuery {
    pub fn new(
        candidates: Box<dyn Query>,
        schema: &Schema,
        spec: &FingerprintSpec,
        prepared_field: String,
        verifier: Arc<dyn GraphVerifier>,
    ) -> tantivy::Result<Self> {
        Self::validate_schema(schema, spec, &prepared_field)?;
        Ok(Self {
            candidates,
            prepared_field,
            spec: spec.clone(),
            verifier,
        })
    }
    /// Check both fingerprint identity and the raw prepared-text physical contract.
    pub fn validate_schema(
        schema: &Schema,
        spec: &FingerprintSpec,
        prepared_field: &str,
    ) -> tantivy::Result<()> {
        let fields = MoleculeFields::from_schema(schema, spec, prepared_field)?;
        if !schema.get_field_entry(fields.prepared_smiles).is_fast() {
            return Err(invalid(
                "graph search requires a raw fast prepared SMILES field; reindex with fast=true",
            ));
        }
        if let FieldType::Str(options) = schema.get_field_entry(fields.prepared_smiles).field_type()
            && matches!(options.get_fast_field_tokenizer_name(), Some(name) if name != "raw")
        {
            return Err(invalid(
                "prepared SMILES fast field must use the raw normalizer",
            ));
        }
        Ok(())
    }
}

impl Query for GraphQuery {
    fn weight(&self, enable_scoring: EnableScoring<'_>) -> tantivy::Result<Box<dyn Weight>> {
        Ok(Box::new(GraphWeight {
            candidates: self.candidates.weight(EnableScoring::Disabled {
                schema: enable_scoring.schema(),
                searcher_opt: enable_scoring.searcher(),
            })?,
            prepared_field: self.prepared_field.clone(),
            spec: self.spec.clone(),
            verifier: self.verifier.clone(),
        }))
    }

    fn query_terms<'a>(&'a self, visitor: &mut dyn FnMut(&'a Term, bool)) {
        self.candidates.query_terms(visitor);
    }
}

struct GraphWeight {
    candidates: Box<dyn Weight>,
    prepared_field: String,
    spec: FingerprintSpec,
    verifier: Arc<dyn GraphVerifier>,
}

impl Weight for GraphWeight {
    fn scorer(&self, reader: &SegmentReader, boost: Score) -> tantivy::Result<Box<dyn Scorer>> {
        let mut matcher = self.verifier.matcher()?;
        let mut candidates = self.candidates.scorer(reader, 1.0)?;
        // Only live candidates make stored chemistry values relevant. Construct
        // the candidate scorer first so its own errors are never suppressed.
        while candidates.doc() != TERMINATED && reader.is_deleted(candidates.doc()) {
            candidates.advance();
        }
        if candidates.doc() == TERMINATED {
            return Ok(Box::new(CandidateScores::new(Vec::new(), boost)));
        }
        GraphQuery::validate_schema(reader.schema(), &self.spec, &self.prepared_field)?;
        let column = reader
            .fast_fields()
            .str(&self.prepared_field)?
            .ok_or_else(|| invalid("missing prepared SMILES fast field"))?;
        let mut cache = HashMap::new();
        let mut scores = Vec::new();
        let mut smiles = String::new();
        while candidates.doc() != TERMINATED {
            let doc = candidates.doc();
            if reader.is_deleted(doc) {
                candidates.advance();
                continue;
            }
            let mut ordinals = column.term_ords(doc);
            let ordinal = ordinals
                .next()
                .ok_or_else(|| invalid("each candidate must have exactly one prepared molecule"))?;
            if ordinals.next().is_some() {
                return Err(invalid(
                    "each candidate must have exactly one prepared molecule",
                ));
            }
            let score = if let Some(score) = cache.get(&ordinal) {
                *score
            } else {
                smiles.clear();
                if !column.ord_to_str(ordinal, &mut smiles)? {
                    return Err(invalid("missing prepared molecule dictionary value"));
                }
                let score = matcher.score(&smiles)?;
                if matches!(score, Some(score) if !score.is_finite() || score < 0.0) {
                    return Err(invalid("invalid graph verification score"));
                }
                cache.insert(ordinal, score);
                score
            };
            if let Some(score) = score {
                scores.push((doc, score));
            }
            candidates.advance();
        }
        Ok(Box::new(CandidateScores::new(scores, boost)))
    }

    fn explain(&self, reader: &SegmentReader, doc: DocId) -> tantivy::Result<Explanation> {
        let mut scorer = self.scorer(reader, 1.0)?;
        if scorer.seek(doc) != doc {
            return Err(invalid("document does not match graph query"));
        }
        Ok(Explanation::new(
            "Verified molecular graph ranking",
            scorer.score(),
        ))
    }
}
