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

use anyhow::{bail, ensure};
use serde::{Deserialize, Serialize};
use tantivy_rdkit::FingerprintSpec;

use crate::{
    BinaryFormat, Cardinality, DocParsingError, FastFieldOptions, FieldMappingEntry,
    FieldMappingType, JsonObject,
};

/// Storage layout for the numeric descriptor contract. Existing indexes remain flat.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum DescriptorLayout {
    #[default]
    Flat,
    Nested,
}

impl DescriptorLayout {
    fn is_flat(&self) -> bool {
        *self == Self::Flat
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ChemistryMapping {
    pub spec: FingerprintSpec,
    /// Generate the complete Cheminee descriptor_v1 contract in process.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub descriptor_v1: bool,
    /// Nested stores all 43 numeric properties in one indexed, fast JSON object.
    #[serde(default, skip_serializing_if = "DescriptorLayout::is_flat")]
    pub descriptor_layout: DescriptorLayout,
    pub smiles_field: String,
    pub prepared_smiles_field: String,
}

impl ChemistryMapping {
    pub(crate) fn validate_mapping(&self, mappings: &[FieldMappingEntry]) -> anyhow::Result<()> {
        self.spec.validate()?;
        ensure!(
            self.descriptor_v1 || self.descriptor_layout == DescriptorLayout::Flat,
            "nested descriptors require descriptor_v1"
        );
        if self.descriptor_v1 {
            validate_descriptor_mapping(self, mappings)?;
        }
        let fingerprint_name = self.spec.field_name();
        ensure!(
            self.smiles_field != self.prepared_smiles_field,
            "SMILES input and prepared fields must differ"
        );
        for name in [&self.smiles_field, &self.prepared_smiles_field] {
            ensure!(
                !name.is_empty()
                    && !name.contains(['.', '\\'])
                    && name != "record_id"
                    && name != &fingerprint_name,
                "chemistry fields must be distinct top-level fields"
            );
        }
        let mapping = |name: &str| {
            mappings
                .iter()
                .find(|field| field.name == name)
                .map(|field| &field.mapping_type)
        };
        ensure!(
            matches!(
                mapping(&self.smiles_field),
                Some(FieldMappingType::Text(_, Cardinality::SingleValued))
            ),
            "SMILES input must be a single text field"
        );
        match mapping(&self.prepared_smiles_field) {
            Some(FieldMappingType::Text(options, Cardinality::SingleValued)) if options.stored => {}
            _ => bail!("prepared SMILES must be a single stored text field"),
        }
        match mapping(&fingerprint_name) {
            Some(FieldMappingType::Bytes(options, Cardinality::SingleValued))
                if options.fast && options.input_format == BinaryFormat::Hex => {}
            _ => {
                bail!("derived fingerprint must be a single fast bytes field with input_format=hex")
            }
        }
        match mapping("record_id") {
            Some(FieldMappingType::U64(options, Cardinality::SingleValued))
                if options.fast && options.stored => {}
            _ => bail!("record_id must be a single stored u64 fast field"),
        }
        Ok(())
    }

    pub(crate) fn prepare(&self, mut document: JsonObject) -> Result<JsonObject, DocParsingError> {
        let invalid =
            |message: String| DocParsingError::ValueError(self.smiles_field.clone(), message);
        for output in [self.spec.field_name(), self.prepared_smiles_field.clone()] {
            if document.contains_key(&output) {
                return Err(invalid(format!(
                    "derived field `{output}` must not be supplied"
                )));
            }
        }
        if document
            .get("record_id")
            .and_then(serde_json::Value::as_u64)
            .is_none()
        {
            return Err(invalid("record_id must be an unsigned integer".into()));
        }
        let smiles = document
            .get(&self.smiles_field)
            .and_then(serde_json::Value::as_str)
            .ok_or_else(|| invalid("a single SMILES string is required".into()))?;
        if self.descriptor_v1 {
            if self.descriptor_layout == DescriptorLayout::Nested {
                for name in std::iter::once("descriptors")
                    .chain(tantivy_rdkit::descriptor_v1::KNOWN_DESCRIPTORS)
                {
                    if document.contains_key(name) {
                        return Err(invalid(format!(
                            "derived field `{name}` must not be supplied"
                        )));
                    }
                }
            }
            let mut outputs = prepare_descriptors(smiles, &self.spec).map_err(invalid)?;
            if self.descriptor_layout == DescriptorLayout::Nested {
                let mut descriptors = JsonObject::new();
                for name in tantivy_rdkit::descriptor_v1::KNOWN_DESCRIPTORS {
                    let value = outputs.remove(name).ok_or_else(|| {
                        invalid(format!("prepared descriptor `{name}` is missing"))
                    })?;
                    descriptors.insert(name.into(), value);
                }
                outputs.insert("descriptors".into(), descriptors.into());
            }
            for (name, value) in outputs {
                let output = if name == "smiles" {
                    self.prepared_smiles_field.clone()
                } else {
                    name
                };
                if document.contains_key(&output) {
                    return Err(invalid(format!(
                        "derived field `{output}` must not be supplied"
                    )));
                }
                document.insert(output, value);
            }
            return Ok(document);
        }
        let (fingerprint, prepared) = prepare_smiles(smiles, &self.spec).map_err(invalid)?;
        document.insert(self.spec.field_name(), fingerprint.into());
        document.insert(self.prepared_smiles_field.clone(), prepared.into());
        Ok(document)
    }
}

fn validate_descriptor_mapping(
    chemistry: &ChemistryMapping,
    mappings: &[FieldMappingEntry],
) -> anyhow::Result<()> {
    ensure!(
        chemistry.spec.preparation_id == "cheminee-fragment-tautomer-neutralize-v1",
        "descriptor_v1 requires Cheminee canonical preparation"
    );
    if chemistry.descriptor_layout == DescriptorLayout::Nested {
        ensure!(
            mappings.iter().any(|field| field.name == "descriptors"
                && matches!(&field.mapping_type,
                FieldMappingType::Json(options, Cardinality::SingleValued)
                    if options.indexing_options.is_some()
                        && !matches!(options.fast, FastFieldOptions::Disabled)
                        && options.stored)),
            "nested descriptor_v1 requires one stored, indexed, fast descriptors JSON field"
        );
        ensure!(
            !mappings
                .iter()
                .any(|field| tantivy_rdkit::descriptor_v1::KNOWN_DESCRIPTORS
                    .contains(&field.name.as_str())),
            "nested descriptor_v1 must not also map top-level numeric descriptors"
        );
    } else {
        for name in tantivy_rdkit::descriptor_v1::KNOWN_DESCRIPTORS {
            let field = mappings
                .iter()
                .find(|field| field.name == name)
                .ok_or_else(|| anyhow::anyhow!("descriptor_v1 requires field `{name}`"))?;
            let valid = if name.starts_with("Num") || name.starts_with("lipinski") {
                matches!(
                    &field.mapping_type,
                    FieldMappingType::I64(_, Cardinality::SingleValued)
                )
            } else {
                matches!(
                    &field.mapping_type,
                    FieldMappingType::F64(_, Cardinality::SingleValued)
                )
            };
            ensure!(
                valid,
                "descriptor_v1 field `{name}` has the wrong numeric type"
            );
        }
    }
    ensure!(mappings.iter().any(|field| field.name == "pattern_fingerprint"
        && matches!(&field.mapping_type, FieldMappingType::Bytes(options, Cardinality::SingleValued)
            if options.input_format == BinaryFormat::Base64)),
        "descriptor_v1 requires a base64 pattern_fingerprint bytes field");
    ensure!(
        mappings
            .iter()
            .any(|field| field.name == "other_descriptors"
                && matches!(
                    &field.mapping_type,
                    FieldMappingType::Json(_, Cardinality::SingleValued)
                )),
        "descriptor_v1 requires other_descriptors JSON"
    );
    Ok(())
}

#[cfg(not(feature = "descriptor-v1"))]
fn prepare_descriptors(_: &str, _: &FingerprintSpec) -> Result<JsonObject, String> {
    Err("descriptor_v1 requires a Quickwit build with the descriptor-v1 feature".into())
}

#[cfg(feature = "descriptor-v1")]
fn prepare_descriptors(smiles: &str, spec: &FingerprintSpec) -> Result<JsonObject, String> {
    use base64::Engine;
    use tantivy_rdkit_mapper::descriptor::{KNOWN_DESCRIPTORS, prepare_cached};
    let prepared = prepare_cached(smiles, spec).map_err(|error| error.to_string())?;
    let mut output = JsonObject::new();
    output.insert("smiles".into(), prepared.smiles.clone().into());
    output.insert(spec.field_name(), prepared.fingerprint.to_hex().into());
    output.insert(
        "pattern_fingerprint".into(),
        base64::engine::general_purpose::STANDARD
            .encode(&prepared.pattern)
            .into(),
    );
    output.insert(
        "other_descriptors".into(),
        serde_json::json!({
            "scaffolds": prepared.scaffolds, "similarity_cluster": prepared.cluster
        }),
    );
    for name in KNOWN_DESCRIPTORS {
        let value = prepared.descriptors[name];
        output.insert(
            name.into(),
            if name.starts_with("Num") || name.starts_with("lipinski") {
                serde_json::Value::from(value as i64)
            } else {
                serde_json::Value::from(value)
            },
        );
    }
    Ok(output)
}

#[cfg(feature = "native-chemistry")]
fn prepare_smiles(smiles: &str, spec: &FingerprintSpec) -> Result<(String, String), String> {
    let molecule = tantivy_rdkit_mapper::PreparedMolecule::from_smiles(smiles, spec)
        .map_err(|error| error.to_string())?;
    Ok((molecule.fingerprint.to_hex(), molecule.smiles))
}

#[cfg(not(feature = "native-chemistry"))]
fn prepare_smiles(_smiles: &str, _spec: &FingerprintSpec) -> Result<(String, String), String> {
    Err("SMILES mapping requires a Quickwit build with the native-chemistry feature".into())
}

pub(crate) fn validate_graph_contract(
    query: &quickwit_query::query_ast::QueryAst,
    mapping: Option<&ChemistryMapping>,
) -> Result<(), quickwit_query::InvalidQuery> {
    use quickwit_query::query_ast::{GraphQueryAst, QueryAstVisitor};
    struct Validator<'a>(Option<&'a ChemistryMapping>);
    impl<'a> QueryAstVisitor<'a> for Validator<'_> {
        type Err = quickwit_query::InvalidQuery;
        fn visit_graph(&mut self, query: &'a GraphQueryAst) -> Result<(), Self::Err> {
            let mapping = self.0.ok_or_else(|| {
                Self::Err::InvalidChemistry(
                    "graph search requires a native chemistry mapping".into(),
                )
            })?;
            if mapping.spec != query.spec || mapping.prepared_smiles_field != query.prepared_field {
                return Err(Self::Err::InvalidChemistry(
                    "graph query contract or prepared field differs from index mapping; reindex \
                     for normalization changes"
                        .into(),
                ));
            }
            self.visit(&query.candidates)
        }
    }
    Validator(mapping).visit(query)
}

#[cfg(test)]
mod tests;
