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

#[cfg(feature = "descriptor-v1")]
mod cluster;
#[cfg(feature = "descriptor-v1")]
pub mod descriptor;
#[cfg(all(test, feature = "descriptor-v1"))]
mod descriptor_tests;
mod graph;
mod native;
mod preparation;
pub use graph::NativeGraphVerifier;
pub use preparation::{CHEMINEE_PREPARATION_ID, PRESERVE_TAUTOMER_PREPARATION_ID};
use tantivy::TantivyDocument;
use tantivy_rdkit::{FingerprintFormat, FingerprintSpec, MoleculeFields, PackedFingerprint};

pub const RDKIT_VERSION: &str = "2026.09.1";
pub const PREPARATION_ID: &str = "sanitize-only-v1";

#[derive(Debug, thiserror::Error)]
pub enum MappingError {
    #[error("incompatible fingerprint contract: {0}")]
    Contract(String),
    #[error("invalid SMILES: {0}")]
    InvalidSmiles(String),
    #[error("molecule preparation failed: {0}")]
    Preparation(String),
}

pub fn fingerprint_spec() -> FingerprintSpec {
    FingerprintSpec {
        format: FingerprintFormat::MorganR3Bits2048Lsb0V1,
        rdkit_version: RDKIT_VERSION.into(),
        preparation_id: PREPARATION_ID.into(),
    }
}

pub fn validate_spec(spec: &FingerprintSpec) -> Result<(), MappingError> {
    if spec.format != FingerprintFormat::MorganR3Bits2048Lsb0V1
        || spec.rdkit_version != RDKIT_VERSION
        || ![
            PREPARATION_ID,
            CHEMINEE_PREPARATION_ID,
            PRESERVE_TAUTOMER_PREPARATION_ID,
        ]
        .contains(&spec.preparation_id.as_str())
    {
        return Err(MappingError::Contract(format!(
            "expected {:?}, received {spec:?}",
            fingerprint_spec()
        )));
    }
    let version = native::ffi::rdkit_version();
    if version != RDKIT_VERSION {
        return Err(MappingError::Contract(format!(
            "linked RDKit is {version}, expected {RDKIT_VERSION}"
        )));
    }
    Ok(())
}

#[derive(Debug)]
pub struct PreparedMolecule {
    pub fingerprint: PackedFingerprint,
    pub smiles: String,
}

impl PreparedMolecule {
    pub fn from_smiles(smiles: &str, spec: &FingerprintSpec) -> Result<Self, MappingError> {
        validate_spec(spec)?;
        let molecule = preparation::prepare(smiles, spec)?;
        let native_fingerprint = molecule
            .try_morgan_fingerprint()
            .map_err(|error| MappingError::Preparation(error.to_string()))?;
        if native_fingerprint.0.len() != 2048 {
            return Err(MappingError::Preparation(
                "RDKit returned a fingerprint with the wrong width".into(),
            ));
        }
        let fingerprint = PackedFingerprint::from_bytes(native_fingerprint.0.as_raw_slice())
            .map_err(|error| MappingError::InvalidSmiles(error.to_string()))?;
        let prepared_smiles = molecule
            .try_as_smiles()
            .map_err(|error| MappingError::Preparation(error.to_string()))?;
        Ok(Self {
            fingerprint,
            smiles: prepared_smiles,
        })
    }

    pub fn add_to_document(&self, document: &mut TantivyDocument, fields: MoleculeFields) {
        document.add_bytes(fields.fingerprint, self.fingerprint.as_bytes());
        document.add_text(fields.prepared_smiles, &self.smiles);
    }
}

impl From<cxx::Exception> for MappingError {
    fn from(error: cxx::Exception) -> Self {
        Self::Preparation(error.to_string())
    }
}
