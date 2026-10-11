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

use rdkit::{
    CleanupParameters, HybridizationType, ROMol, RWMol, SubstructMatchParameters,
    TautomerEnumerator, try_fragment_parent, try_set_hybridization, try_substruct_match,
};
use tantivy_rdkit::FingerprintSpec;

use crate::{MappingError, PREPARATION_ID};

pub const CHEMINEE_PREPARATION_ID: &str = "cheminee-fragment-tautomer-neutralize-v1";
pub const PRESERVE_TAUTOMER_PREPARATION_ID: &str = "cheminee-fragment-neutralize-v1";

pub(crate) fn prepare(smiles: &str, spec: &FingerprintSpec) -> Result<ROMol, MappingError> {
    let normalized = prepare_original(smiles, spec)?;
    if spec.preparation_id == PREPARATION_ID {
        return Ok(normalized);
    }
    ROMol::from_smiles(&normalized.try_as_smiles()?)
        .map_err(|error| MappingError::Preparation(error.to_string()))
}

// Cheminee computes descriptors and fingerprints before the validating SMILES round trip.
pub(crate) fn prepare_original(
    smiles: &str,
    spec: &FingerprintSpec,
) -> Result<ROMol, MappingError> {
    if smiles.trim().is_empty() || smiles.chars().any(char::is_whitespace) || smiles.contains('|') {
        return Err(MappingError::InvalidSmiles(
            "expected a nonempty plain SMILES without names or CXSMILES extensions".into(),
        ));
    }
    let molecule = ROMol::from_smiles(smiles)
        .map_err(|error| MappingError::InvalidSmiles(error.to_string()))?;
    if spec.preparation_id == PREPARATION_ID {
        return Ok(molecule);
    }
    let parent = try_fragment_parent(
        &molecule.try_as_rw_mol(false, -1)?,
        &CleanupParameters::default(),
        true,
    )?
    .to_ro_mol();
    let mut normalized = if spec.preparation_id == CHEMINEE_PREPARATION_ID {
        TautomerEnumerator::try_new()?.canonicalize(&parent)?
    } else {
        parent
    };
    let pattern = RWMol::from_smarts("[+1!h0!$([*]~[-1,-2,-3,-4]),-1!$([*]~[+1,+2,+3,+4])]")
        .map_err(|error| MappingError::Preparation(error.to_string()))?
        .to_ro_mol();
    let matches = try_substruct_match(&normalized, &pattern, &SubstructMatchParameters::default())?;
    if matches.len() >= 1000 {
        return Err(MappingError::Preparation(
            "neutralization reaches the RDKit 1000-match limit; this molecule is unsupported"
                .into(),
        ));
    }
    for matched in matches {
        let mut atom = normalized.try_atom_with_idx(matched[0].mol_atom_idx as u32)?;
        let charge = atom.try_get_formal_charge()?;
        if atom.try_get_is_aromatic()?
            || (atom.try_get_hybridization_type()? == HybridizationType::SP3 && charge < 0)
        {
            continue;
        }
        let hydrogens = atom.try_get_total_num_hs()? as i32;
        atom.try_set_formal_charge(0)?;
        atom.try_set_num_explicit_hs(hydrogens - charge)?;
        atom.update_property_cache(true)?;
        try_set_hybridization(&mut normalized)?;
    }
    Ok(normalized)
}
