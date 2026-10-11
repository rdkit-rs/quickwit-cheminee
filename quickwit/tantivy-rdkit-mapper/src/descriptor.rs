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

//! Cheminee descriptor_v1 preparation. No network or subprocess work occurs here.
use std::collections::HashMap;
use std::sync::{Arc, Mutex, OnceLock};

use rdkit::{Properties, ROMol, SubstructMatchParameters, try_substruct_match};
pub use tantivy_rdkit::descriptor_v1::KNOWN_DESCRIPTORS;
use tantivy_rdkit::{FingerprintSpec, PackedFingerprint};

use crate::{CHEMINEE_PREPARATION_ID, MappingError, preparation, validate_spec};

#[derive(Debug)]
pub struct PreparedDocument {
    pub smiles: String,
    pub fingerprint: PackedFingerprint,
    pub pattern: Vec<u8>,
    pub descriptors: HashMap<String, f64>,
    pub scaffolds: Vec<i64>,
    pub cluster: i32,
}

struct Scaffold {
    molecule: ROMol,
    fingerprint: Vec<u8>,
    id: i64,
}

thread_local! {
    // RDKit molecules are thread confined. Initialization failure is retained and reported.
    static SCAFFOLDS: Result<Vec<Scaffold>, String> = load_scaffolds();
}

fn load_scaffolds() -> Result<Vec<Scaffold>, String> {
    let mut scaffolds = Vec::new();
    for line in include_str!("../assets/standardized_scaffolds_20240405.json").lines() {
        let value: serde_json::Value = serde_json::from_str(line).map_err(|e| e.to_string())?;
        let smiles = value["smiles"].as_str().ok_or("invalid scaffold SMILES")?;
        let molecule = ROMol::from_smiles(smiles).map_err(|e| e.to_string())?;
        let fingerprint = molecule
            .try_pattern_fingerprint()
            .map_err(|e| e.to_string())?;
        scaffolds.push(Scaffold {
            molecule,
            fingerprint: fingerprint.0.as_raw_slice().to_vec(),
            id: value["scaffold_id"].as_i64().ok_or("invalid scaffold ID")?,
        });
    }
    Ok(scaffolds)
}

fn scaffold_ids(molecule: &ROMol, pattern: &[u8]) -> Result<Vec<i64>, MappingError> {
    SCAFFOLDS.with(|result| {
        let scaffolds = result
            .as_ref()
            .map_err(|e| MappingError::Preparation(e.clone()))?;
        let params = SubstructMatchParameters::default();
        let mut matches = Vec::new();
        for scaffold in scaffolds {
            if scaffold.fingerprint.len() != pattern.len() {
                return Err(MappingError::Preparation(
                    "scaffold fingerprint width mismatch".into(),
                ));
            }
            if scaffold
                .fingerprint
                .iter()
                .zip(pattern)
                .all(|(s, p)| s & p == *s)
                && !try_substruct_match(molecule, &scaffold.molecule, &params)?.is_empty()
            {
                matches.push(scaffold.id);
            }
        }
        if matches.is_empty() {
            matches.push(-1);
        }
        Ok(matches)
    })
}

impl PreparedDocument {
    pub fn from_smiles(smiles: &str, spec: &FingerprintSpec) -> Result<Self, MappingError> {
        validate_spec(spec)?;
        if spec.preparation_id != CHEMINEE_PREPARATION_ID {
            return Err(MappingError::Contract(
                "descriptor_v1 requires Cheminee canonical preparation".into(),
            ));
        }
        let molecule = preparation::prepare_original(smiles, spec)?;
        let descriptors = Properties::try_new()?.try_compute_properties(&molecule)?;
        for name in KNOWN_DESCRIPTORS {
            if !matches!(descriptors.get(name), Some(value) if value.is_finite()) {
                return Err(MappingError::Preparation(format!(
                    "missing or nonfinite descriptor {name}"
                )));
            }
        }
        let pattern = molecule
            .try_pattern_fingerprint()?
            .0
            .as_raw_slice()
            .to_vec();
        let morgan = molecule.try_morgan_fingerprint()?;
        let fingerprint = PackedFingerprint::from_bytes(morgan.0.as_raw_slice())
            .map_err(|e| MappingError::Preparation(e.to_string()))?;
        let validated = ROMol::from_smiles(&molecule.try_as_smiles()?)
            .map_err(|e| MappingError::Preparation(e.to_string()))?;
        if validated.try_morgan_fingerprint()?.0.as_raw_slice() != fingerprint.as_bytes() {
            return Err(MappingError::Contract(
                "Cheminee fingerprint differs from graph-query round-trip contract".into(),
            ));
        }
        let scaffolds = scaffold_ids(&molecule, &pattern)?;
        let cluster = crate::cluster::assign(&fingerprint)?;
        Ok(Self {
            smiles: molecule.try_as_smiles()?,
            fingerprint,
            pattern,
            descriptors,
            scaffolds,
            cluster,
        })
    }
}

// A process-local, bounded optimization shared by ingester validation and actor mapping.
// Only native outputs enter this cache; metadata is always validated separately. Eviction,
// a restart, or a remote indexing worker recomputes chemistry and never trusts client data.
#[derive(Default)]
struct PreparationCache {
    entries: HashMap<String, Arc<PreparedDocument>>,
    bytes: usize,
}
static CACHE: OnceLock<Mutex<PreparationCache>> = OnceLock::new();
const CACHE_BUDGET: usize = 64 * 1024 * 1024;

pub fn prepare_cached(
    smiles: &str,
    spec: &FingerprintSpec,
) -> Result<Arc<PreparedDocument>, MappingError> {
    validate_spec(spec)?;
    if spec.preparation_id != CHEMINEE_PREPARATION_ID {
        return Err(MappingError::Contract(
            "descriptor_v1 requires Cheminee canonical preparation".into(),
        ));
    }
    let cache = CACHE.get_or_init(|| Mutex::new(PreparationCache::default()));
    {
        let entries = cache
            .lock()
            .map_err(|e| MappingError::Preparation(e.to_string()))?;
        if let Some(prepared) = entries.entries.get(smiles) {
            return Ok(prepared.clone());
        }
    }
    let prepared = Arc::new(PreparedDocument::from_smiles(smiles, spec)?);
    // Conservative owned-capacity accounting; allocator/RSS are measured separately.
    let bytes = smiles.len()
        + prepared.smiles.capacity()
        + prepared.pattern.capacity()
        + prepared.scaffolds.capacity() * 8
        + prepared.descriptors.capacity() * 96
        + 512;
    if bytes <= CACHE_BUDGET {
        let mut entries = cache
            .lock()
            .map_err(|e| MappingError::Preparation(e.to_string()))?;
        if entries.bytes + bytes > CACHE_BUDGET {
            entries.entries.clear();
            entries.bytes = 0;
        }
        if !entries.entries.contains_key(smiles) {
            entries.entries.insert(smiles.to_owned(), prepared.clone());
            entries.bytes += bytes;
        }
    }
    Ok(prepared)
}
