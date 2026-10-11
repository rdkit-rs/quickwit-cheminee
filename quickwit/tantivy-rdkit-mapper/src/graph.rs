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

use rdkit::{ROMol, SubstructMatchParameters, try_substruct_match};
use tantivy_rdkit::{
    FingerprintSpec, GraphPredicate, GraphRanking, GraphVerifier, MoleculeMatcher,
};

use crate::{MappingError, PreparedMolecule, validate_spec};

#[derive(Debug)]
pub struct NativeGraphVerifier {
    pub spec: FingerprintSpec,
    pub prepared_smiles: String,
    pub predicate: GraphPredicate,
    pub ranking: GraphRanking,
    pub use_chirality: bool,
    pub include_identity: bool,
}

fn invalid(error: impl std::fmt::Display) -> tantivy::TantivyError {
    tantivy::TantivyError::InvalidArgument(error.to_string())
}

impl NativeGraphVerifier {
    pub fn validate(&self) -> Result<(), MappingError> {
        validate_spec(&self.spec)?;
        if matches!(self.ranking, GraphRanking::FewestExtraHeavyAtoms)
            && self.predicate != GraphPredicate::Substructure
            || matches!(self.ranking, GraphRanking::GreatestQueryCoverage)
                && self.predicate != GraphPredicate::Superstructure
        {
            return Err(MappingError::Contract(
                "ranking does not apply to the graph predicate".into(),
            ));
        }
        let prepared = PreparedMolecule::from_smiles(&self.prepared_smiles, &self.spec)?;
        let query = ROMol::from_smiles(&prepared.smiles)
            .map_err(|error| MappingError::InvalidSmiles(error.to_string()))?;
        if heavy_atoms(&query).map_err(|error| MappingError::InvalidSmiles(error.to_string()))? == 0
        {
            return Err(MappingError::InvalidSmiles(
                "graph queries require at least one heavy atom".into(),
            ));
        }
        if prepared.smiles != self.prepared_smiles {
            return Err(MappingError::Contract(
                "graph query must contain SMILES prepared under its declared contract".into(),
            ));
        }
        Ok(())
    }
}

impl GraphVerifier for NativeGraphVerifier {
    fn matcher(&self) -> tantivy::Result<Box<dyn MoleculeMatcher>> {
        self.validate().map_err(invalid)?;
        let query = ROMol::from_smiles(&self.prepared_smiles).map_err(invalid)?;
        let mut parameters = SubstructMatchParameters::default();
        parameters.set_use_chirality(self.use_chirality);
        let heavy_atoms = heavy_atoms(&query)?;
        if heavy_atoms == 0 {
            return Err(invalid("graph queries require at least one heavy atom"));
        }
        Ok(Box::new(NativeMatcher {
            query,
            parameters,
            heavy_atoms,
            predicate: self.predicate,
            ranking: self.ranking,
            include_identity: self.include_identity,
        }))
    }
}

fn heavy_atoms(molecule: &ROMol) -> tantivy::Result<u32> {
    let mut count = 0;
    for index in 0..molecule.num_atoms(true) {
        if molecule
            .atom_ref(index)
            .map_err(invalid)?
            .try_get_atomic_num()
            .map_err(invalid)?
            > 1
        {
            count += 1;
        }
    }
    Ok(count)
}

struct NativeMatcher {
    query: ROMol,
    parameters: SubstructMatchParameters,
    heavy_atoms: u32,
    predicate: GraphPredicate,
    ranking: GraphRanking,
    include_identity: bool,
}

impl MoleculeMatcher for NativeMatcher {
    fn score(&mut self, prepared_smiles: &str) -> tantivy::Result<Option<f32>> {
        let document = ROMol::from_smiles(prepared_smiles).map_err(invalid)?;
        let matches = |mol: &ROMol, query: &ROMol| -> tantivy::Result<bool> {
            Ok(!try_substruct_match(mol, query, &self.parameters)
                .map_err(invalid)?
                .is_empty())
        };
        let accepted = match self.predicate {
            GraphPredicate::Identity => {
                matches(&document, &self.query)? && matches(&self.query, &document)?
            }
            GraphPredicate::Substructure => {
                matches(&document, &self.query)?
                    && (self.include_identity || !matches(&self.query, &document)?)
            }
            GraphPredicate::Superstructure => {
                matches(&self.query, &document)?
                    && (self.include_identity || !matches(&document, &self.query)?)
            }
        };
        if !accepted {
            return Ok(None);
        }
        if self.ranking == GraphRanking::StableId {
            return Ok(Some(1.0));
        }
        let atoms = heavy_atoms(&document)?;
        let score = match self.predicate {
            GraphPredicate::Identity => 1.0,
            GraphPredicate::Substructure => {
                1.0 / (1.0 + atoms.saturating_sub(self.heavy_atoms) as f32)
            }
            GraphPredicate::Superstructure => atoms as f32 / self.heavy_atoms as f32,
        };
        Ok(Some(score))
    }
}
