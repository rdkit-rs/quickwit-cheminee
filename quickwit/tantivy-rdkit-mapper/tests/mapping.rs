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

use rdkit::ROMol;
use tantivy::collector::Count;
use tantivy::query::AllQuery;
use tantivy::schema::Schema;
use tantivy::{Index, TantivyDocument};
use tantivy_rdkit::{MoleculeFields, PackedFingerprint, TanimotoQuery};
use tantivy_rdkit_mapper::{PreparedMolecule, fingerprint_spec};

#[test]
fn native_mapping_and_query_contract_agree() {
    let spec = fingerprint_spec();
    let mut builder = Schema::builder();
    let fields = MoleculeFields::add_to_schema(&mut builder, &spec, "prepared_smiles").unwrap();
    let schema = builder.build();
    let index = Index::create_in_ram(schema.clone());
    let mut writer = index
        .writer_with_num_threads::<TantivyDocument>(1, 15_000_000)
        .unwrap();
    for smiles in [
        "CCO",
        "CC(=O)[O-].[Na+]",
        "c1ccccc1",
        "C1=CC=CC=C1",
        "C[C@H](O)C(=O)O",
        "C[C@@H](O)C(=O)O",
        "[13CH3]CO",
    ] {
        let prepared = PreparedMolecule::from_smiles(smiles, &spec).unwrap();
        let reference = ROMol::from_smiles(smiles).unwrap().morgan_fingerprint();
        assert_eq!(
            prepared.fingerprint.as_bytes().as_slice(),
            reference.0.as_raw_slice()
        );
        assert_eq!(prepared.fingerprint.to_hex().len(), 512);
        for bit in reference.0.iter_ones() {
            assert_ne!(
                prepared.fingerprint.as_bytes()[bit / 8] & (1 << (bit % 8)),
                0
            );
        }
        let reparsed = PreparedMolecule::from_smiles(&prepared.smiles, &spec).unwrap();
        assert_eq!(reparsed.fingerprint, prepared.fingerprint);
        let mut doc = TantivyDocument::new();
        prepared.add_to_document(&mut doc, fields);
        writer.add_document(doc).unwrap();
    }
    writer.commit().unwrap();
    let query_molecule = PreparedMolecule::from_smiles("CCO", &spec).unwrap();
    let packed = PackedFingerprint::from_hex(&query_molecule.fingerprint.to_hex()).unwrap();
    let query = TanimotoQuery::new(Box::new(AllQuery), &schema, &spec, packed, 1.0).unwrap();
    let reader = index.reader().unwrap();
    assert_eq!(reader.searcher().search(&query, &Count).unwrap(), 2);
}

#[test]
fn rejects_invalid_empty_and_incompatible_inputs() {
    for smiles in ["bad-smiles", "C1CC", "[CH5]", "", " "] {
        assert!(
            PreparedMolecule::from_smiles(smiles, &fingerprint_spec()).is_err(),
            "{smiles}"
        );
    }
    let mut spec = fingerprint_spec();
    spec.preparation_id = "neutralize-v1".into();
    assert!(PreparedMolecule::from_smiles("CCO", &spec).is_err());
    spec = fingerprint_spec();
    spec.rdkit_version = "2025.03.1".into();
    assert!(PreparedMolecule::from_smiles("CCO", &spec).is_err());
}

#[test]
fn preserves_salts_aromaticity_and_stereochemistry_without_chiral_fingerprints() {
    let prepare = |smiles| PreparedMolecule::from_smiles(smiles, &fingerprint_spec()).unwrap();
    let salt = prepare("CC(=O)[O-].[Na+]");
    assert_eq!(prepare("CCO").fingerprint, prepare("[13CH3]CO").fingerprint);
    assert!(prepare("[13CH3]CO").smiles.contains("13"));
    assert!(salt.smiles.contains("[Na+]"));
    assert!(salt.smiles.contains("[O-]"));
    assert_eq!(
        prepare("c1ccccc1").fingerprint,
        prepare("C1=CC=CC=C1").fingerprint
    );
    let left = prepare("C[C@H](O)C(=O)O");
    let right = prepare("C[C@@H](O)C(=O)O");
    assert_eq!(left.fingerprint, right.fingerprint);
    assert_ne!(left.smiles, right.smiles);
}
