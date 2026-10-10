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
    BinaryFormat, Cardinality, DocParsingError, FieldMappingEntry, FieldMappingType, JsonObject,
};

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ChemistryMapping {
    pub spec: FingerprintSpec,
    pub smiles_field: String,
    pub prepared_smiles_field: String,
}

impl ChemistryMapping {
    pub(crate) fn validate_mapping(&self, mappings: &[FieldMappingEntry]) -> anyhow::Result<()> {
        self.spec.validate()?;
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
        let (fingerprint, prepared) = prepare_smiles(smiles, &self.spec).map_err(invalid)?;
        document.insert(self.spec.field_name(), fingerprint.into());
        document.insert(self.prepared_smiles_field.clone(), prepared.into());
        Ok(document)
    }
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

#[cfg(test)]
mod tests;
