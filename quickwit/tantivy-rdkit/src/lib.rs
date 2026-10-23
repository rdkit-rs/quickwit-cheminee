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
use sha2::{Digest, Sha256};
use tantivy::columnar::BytesColumn;
use tantivy::query::{EnableScoring, Explanation, Query, Scorer, Weight};
use tantivy::schema::{FieldType, Schema};
use tantivy::{DocId, DocSet, Score, SegmentReader, TERMINATED, TantivyError, Term};

pub const FINGERPRINT_BYTES: usize = 256;

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "openapi", derive(utoipa::ToSchema))]
#[serde(deny_unknown_fields)]
pub struct FingerprintSpec {
    pub format: FingerprintFormat,
    #[cfg_attr(
        feature = "openapi",
        schema(min_length = 1, max_length = 128, pattern = "^[!-~]{1,128}$")
    )]
    pub rdkit_version: String,
    #[cfg_attr(
        feature = "openapi",
        schema(min_length = 1, max_length = 128, pattern = "^[!-~]{1,128}$")
    )]
    pub preparation_id: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "openapi", derive(utoipa::ToSchema))]
pub enum FingerprintFormat {
    #[serde(rename = "morgan-r3-2048-lsb0-v1")]
    MorganR3Bits2048Lsb0V1,
}

fn invalid(message: impl Into<String>) -> TantivyError {
    TantivyError::InvalidArgument(message.into())
}

impl FingerprintSpec {
    pub fn validate(&self) -> tantivy::Result<()> {
        for value in [&self.rdkit_version, &self.preparation_id] {
            if value.is_empty()
                || value.len() > 128
                || value.bytes().any(|byte| !byte.is_ascii_graphic())
            {
                return Err(invalid(
                    "fingerprint version identifiers must contain 1..128 ASCII bytes",
                ));
            }
        }
        Ok(())
    }

    pub fn field_name(&self) -> String {
        let digest = Sha256::digest(
            format!(
                "morgan-r3-2048-lsb0-chiral0-features0-v1\0{}\0{}",
                self.rdkit_version, self.preparation_id
            )
            .as_bytes(),
        );
        format!("morgan_{}", hex::encode(digest))
    }
}

#[derive(Clone, Debug)]
pub struct PackedFingerprint([u8; FINGERPRINT_BYTES]);

impl PackedFingerprint {
    pub fn from_hex(value: &str) -> tantivy::Result<Self> {
        let mut bytes = [0; FINGERPRINT_BYTES];
        hex::decode_to_slice(value, &mut bytes).map_err(|_| {
            invalid("fingerprint must encode exactly 2048 bits as 512 hexadecimal characters")
        })?;
        if bytes.iter().all(|byte| *byte == 0) {
            return Err(invalid(
                "query fingerprint must contain at least one set bit",
            ));
        }
        Ok(Self(bytes))
    }

    pub fn tanimoto(&self, other: &[u8]) -> tantivy::Result<f32> {
        if other.len() != FINGERPRINT_BYTES {
            return Err(invalid(
                "indexed fingerprint must contain exactly 256 bytes",
            ));
        }
        let mut intersection = 0;
        let mut union = 0;
        for (left, right) in self.0.iter().zip(other) {
            intersection += (left & right).count_ones();
            union += (left | right).count_ones();
        }
        Ok(intersection as f32 / union as f32)
    }
}

#[derive(Debug)]
pub struct TanimotoQuery {
    candidates: Box<dyn Query>,
    field_name: String,
    fingerprint: PackedFingerprint,
    minimum: f32,
}

impl Clone for TanimotoQuery {
    fn clone(&self) -> Self {
        Self {
            candidates: self.candidates.box_clone(),
            field_name: self.field_name.clone(),
            fingerprint: self.fingerprint.clone(),
            minimum: self.minimum,
        }
    }
}

impl TanimotoQuery {
    pub fn new(
        candidates: Box<dyn Query>,
        schema: &Schema,
        spec: &FingerprintSpec,
        fingerprint: PackedFingerprint,
        minimum: f32,
    ) -> tantivy::Result<Self> {
        spec.validate()?;
        if !minimum.is_finite() || !(0.0..=1.0).contains(&minimum) {
            return Err(invalid(
                "tanimoto_minimum must be finite and between 0 and 1",
            ));
        }
        let field_name = spec.field_name();
        let field = schema.get_field(&field_name).map_err(|_| {
            invalid("index does not contain the requested fingerprint specification")
        })?;
        let entry = schema.get_field_entry(field);
        if !matches!(entry.field_type(), FieldType::Bytes(_)) || !entry.is_fast() {
            return Err(invalid("fingerprint field must be bytes with fast=true"));
        }
        Ok(Self {
            candidates,
            field_name,
            fingerprint,
            minimum,
        })
    }
}

impl Query for TanimotoQuery {
    fn weight(&self, enable_scoring: EnableScoring<'_>) -> tantivy::Result<Box<dyn Weight>> {
        Ok(Box::new(TanimotoWeight {
            candidates: self.candidates.weight(EnableScoring::Disabled {
                schema: enable_scoring.schema(),
                searcher_opt: enable_scoring.searcher(),
            })?,
            field_name: self.field_name.clone(),
            fingerprint: self.fingerprint.clone(),
            minimum: self.minimum,
        }))
    }

    fn query_terms<'a>(&'a self, visitor: &mut dyn FnMut(&'a Term, bool)) {
        self.candidates.query_terms(visitor);
    }
}

struct TanimotoWeight {
    candidates: Box<dyn Weight>,
    field_name: String,
    fingerprint: PackedFingerprint,
    minimum: f32,
}

impl Weight for TanimotoWeight {
    fn scorer(&self, reader: &SegmentReader, boost: Score) -> tantivy::Result<Box<dyn Scorer>> {
        let column = reader
            .fast_fields()
            .bytes(&self.field_name)?
            .ok_or_else(|| invalid("missing fingerprint fast field"))?;
        let mut scores = Vec::with_capacity(column.num_terms());
        let mut bytes = Vec::new();
        for ordinal in 0..column.num_terms() {
            bytes.clear();
            if !column.ord_to_bytes(ordinal as u64, &mut bytes)? {
                return Err(invalid("missing fingerprint dictionary value"));
            }
            scores.push(self.fingerprint.tanimoto(&bytes)?);
        }
        for doc in 0..reader.max_doc() {
            let mut ordinals = column.term_ords(doc);
            if ordinals.next().is_none() || ordinals.next().is_some() {
                return Err(invalid("each document must have exactly one fingerprint"));
            }
        }
        let mut scorer = TanimotoScorer {
            candidates: self.candidates.scorer(reader, 1.0)?,
            column,
            scores,
            minimum: self.minimum,
            boost,
        };
        scorer.skip_rejected();
        Ok(Box::new(scorer))
    }

    fn explain(&self, reader: &SegmentReader, doc: DocId) -> tantivy::Result<Explanation> {
        let mut scorer = self.scorer(reader, 1.0)?;
        if scorer.seek(doc) != doc {
            return Err(invalid("document does not match chemistry query"));
        }
        Ok(Explanation::new(
            "Morgan fingerprint Tanimoto",
            scorer.score(),
        ))
    }
}

struct TanimotoScorer {
    candidates: Box<dyn Scorer>,
    column: BytesColumn,
    scores: Vec<f32>,
    minimum: f32,
    boost: Score,
}

impl TanimotoScorer {
    fn raw_score(&self) -> f32 {
        let ordinal = self
            .column
            .term_ords(self.candidates.doc())
            .next()
            .expect("fingerprint cardinality was validated when creating the scorer");
        self.scores[ordinal as usize]
    }

    fn skip_rejected(&mut self) -> DocId {
        while self.candidates.doc() != TERMINATED && self.raw_score() < self.minimum {
            self.candidates.advance();
        }
        self.candidates.doc()
    }
}

impl DocSet for TanimotoScorer {
    fn advance(&mut self) -> DocId {
        self.candidates.advance();
        self.skip_rejected()
    }
    fn seek(&mut self, target: DocId) -> DocId {
        self.candidates.seek(target);
        self.skip_rejected()
    }
    fn doc(&self) -> DocId {
        self.candidates.doc()
    }
    fn size_hint(&self) -> u32 {
        self.candidates.size_hint()
    }
}

impl Scorer for TanimotoScorer {
    fn score(&mut self) -> Score {
        self.raw_score() * self.boost
    }
}
