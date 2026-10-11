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

use std::sync::Arc;

use tantivy::collector::{Count, TopDocs};
use tantivy::query::AllQuery;
use tantivy::schema::Schema;
use tantivy::{Index, TantivyDocument};
use tantivy_rdkit::{GraphPredicate, GraphQuery, GraphRanking, GraphVerifier, MoleculeFields};
use tantivy_rdkit_mapper::{
    CHEMINEE_PREPARATION_ID, NativeGraphVerifier, PRESERVE_TAUTOMER_PREPARATION_ID,
    PreparedMolecule, fingerprint_spec,
};

fn verifier(smiles: &str, predicate: GraphPredicate, chirality: bool) -> NativeGraphVerifier {
    let spec = fingerprint_spec();
    NativeGraphVerifier {
        prepared_smiles: PreparedMolecule::from_smiles(smiles, &spec).unwrap().smiles,
        spec,
        predicate,
        ranking: GraphRanking::BestMatch,
        use_chirality: chirality,
        include_identity: true,
    }
}

#[test]
fn direction_ranking_and_identity() {
    for (predicate, expected) in [
        (GraphPredicate::Identity, vec![None, Some(1.0), None]),
        (
            GraphPredicate::Substructure,
            vec![None, Some(1.0), Some(0.5)],
        ),
        (
            GraphPredicate::Superstructure,
            vec![Some(0.5), Some(1.0), None],
        ),
    ] {
        let mut matcher = verifier("CC", predicate, false).matcher().unwrap();
        let scores: Vec<_> = ["C", "CC", "CCC"]
            .iter()
            .map(|s| matcher.score(s).unwrap())
            .collect();
        assert_eq!(scores, expected);
    }
    let mut strict = verifier("CC", GraphPredicate::Substructure, false);
    strict.include_identity = false;
    let mut matcher = strict.matcher().unwrap();
    assert_eq!(matcher.score("CC").unwrap(), None);
    assert_eq!(matcher.score("CCC").unwrap(), Some(0.5));
    strict.ranking = GraphRanking::StableId;
    assert_eq!(strict.matcher().unwrap().score("CCCC").unwrap(), Some(1.0));
}

#[test]
fn chirality_is_verified_even_when_morgan_fingerprints_are_equal() {
    let left = "F[C@H](Cl)Br";
    let right = "F[C@@H](Cl)Br";
    for predicate in [
        GraphPredicate::Identity,
        GraphPredicate::Substructure,
        GraphPredicate::Superstructure,
    ] {
        assert!(
            verifier(left, predicate, true)
                .matcher()
                .unwrap()
                .score(right)
                .unwrap()
                .is_none()
        );
        assert!(
            verifier(left, predicate, false)
                .matcher()
                .unwrap()
                .score(right)
                .unwrap()
                .is_some()
        );
    }
}

#[test]
fn normalization_parity_and_explicit_tautomer_contracts() {
    let mut spec = fingerprint_spec();
    spec.preparation_id = CHEMINEE_PREPARATION_ID.into();
    let prepare = |s: &str| PreparedMolecule::from_smiles(s, &spec).unwrap();
    for (left, right) in [
        ("CC(=O)[O-].[Na+]", "CC(=O)O"),
        ("CC(O)=C", "CC(=O)C"),
        ("C[NH3+]", "CN"),
    ] {
        assert_eq!(prepare(left).smiles, prepare(right).smiles);
        assert_eq!(prepare(left).fingerprint, prepare(right).fingerprint);
    }
    assert!(prepare("[CH2-]C").smiles.contains('-'));
    assert!(prepare("c1cc[nH+]cc1").smiles.contains('+'));
    for raw in ["CC(=O)[O-].[Na+]", "CC(O)=C", "C[NH3+]", "F[C@H](Cl)Br"] {
        let prepared = prepare(raw);
        assert_eq!(prepare(&prepared.smiles).smiles, prepared.smiles);
    }
    spec.preparation_id = PRESERVE_TAUTOMER_PREPARATION_ID.into();
    assert_ne!(
        PreparedMolecule::from_smiles("CC(O)=C", &spec)
            .unwrap()
            .smiles,
        PreparedMolecule::from_smiles("CC(=O)C", &spec)
            .unwrap()
            .smiles
    );
    for raw in ["CCO name", "CCO |atomProp:0.foo.bar|", "", "bad-smiles"] {
        assert!(PreparedMolecule::from_smiles(raw, &spec).is_err());
    }
}

#[test]
fn verification_precedes_top_k_and_totals_across_segments() {
    let spec = fingerprint_spec();
    let mut builder = Schema::builder();
    let fields = MoleculeFields::add_to_schema(&mut builder, &spec, "prepared_smiles").unwrap();
    let schema = builder.build();
    let index = Index::create_in_ram(schema.clone());
    let mut writer = index
        .writer_with_num_threads::<TantivyDocument>(1, 15_000_000)
        .unwrap();
    writer.set_merge_policy(Box::new(tantivy::merge_policy::NoMergePolicy));
    for count in 0..10_055 {
        let smiles = if count < 10_051 {
            "F[C@@H](Cl)Br"
        } else {
            "F[C@H](Cl)Br"
        };
        let prepared = PreparedMolecule::from_smiles(smiles, &spec).unwrap();
        let mut document = TantivyDocument::new();
        prepared.add_to_document(&mut document, fields);
        writer.add_document(document).unwrap();
        if count == 10_050 {
            writer.commit().unwrap();
        }
    }
    writer.commit().unwrap();
    let query = GraphQuery::new(
        Box::new(AllQuery),
        &schema,
        &spec,
        "prepared_smiles".into(),
        Arc::new(verifier("F[C@H](Cl)Br", GraphPredicate::Identity, true)),
    )
    .unwrap();
    let reader = index.reader().unwrap();
    let searcher = reader.searcher();
    assert!(searcher.segment_readers().len() >= 2);
    let (count, top) = searcher
        .search(&query, &(Count, TopDocs::with_limit(1).order_by_score()))
        .unwrap();
    assert_eq!(count, 4);
    assert_eq!(top.len(), 1);
    assert_eq!(top[0].0, 1.0);
}

#[test]
fn canonical_tautomer_stereo_loss_is_explicit_and_preserve_mode_retains_it() {
    let mut spec = fingerprint_spec();
    spec.preparation_id = CHEMINEE_PREPARATION_ID.into();
    let left = "C[C@H](O)C(=O)O";
    let right = "C[C@@H](O)C(=O)O";
    assert_eq!(
        PreparedMolecule::from_smiles(left, &spec).unwrap().smiles,
        PreparedMolecule::from_smiles(right, &spec).unwrap().smiles
    );
    spec.preparation_id = PRESERVE_TAUTOMER_PREPARATION_ID.into();
    assert_ne!(
        PreparedMolecule::from_smiles(left, &spec).unwrap().smiles,
        PreparedMolecule::from_smiles(right, &spec).unwrap().smiles
    );
}

#[test]
fn explicit_rankings_reject_the_wrong_direction() {
    let mut query = verifier("CC", GraphPredicate::Substructure, false);
    query.ranking = GraphRanking::FewestExtraHeavyAtoms;
    assert_eq!(query.matcher().unwrap().score("CCC").unwrap(), Some(0.5));
    query.ranking = GraphRanking::GreatestQueryCoverage;
    assert!(query.validate().is_err());
    query.predicate = GraphPredicate::Superstructure;
    assert_eq!(query.matcher().unwrap().score("C").unwrap(), Some(0.5));
}

#[test]
fn preserve_tautomer_fragment_parent_initializes_fingerprint_ring_cache() {
    let mut spec = fingerprint_spec();
    spec.preparation_id = PRESERVE_TAUTOMER_PREPARATION_ID.into();
    for smiles in [
        "CC(=O)[O-].[Na+]",
        "c1ccccc1.[Na+]",
        "C1CCCCC1",
        "[Cl-].C[NH3+]",
    ] {
        let prepared = PreparedMolecule::from_smiles(smiles, &spec).unwrap();
        let reparsed = PreparedMolecule::from_smiles(&prepared.smiles, &spec).unwrap();
        assert_eq!(prepared.fingerprint, reparsed.fingerprint);
    }
}

#[test]
fn graph_queries_reject_no_heavy_atoms_and_wrong_preparation() {
    assert!(
        verifier("[H][H]", GraphPredicate::Identity, false)
            .validate()
            .is_err()
    );
    let mut query = verifier("CC", GraphPredicate::Identity, false);
    query.spec.preparation_id = CHEMINEE_PREPARATION_ID.into();
    query.prepared_smiles = "C[NH3+]".into();
    assert!(query.validate().is_err());
}
