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

use serde_json::json;
#[cfg(feature = "native-chemistry")]
use tantivy::schema::Value;
use tantivy_rdkit::{FingerprintFormat, FingerprintSpec};

use crate::{DocMapper, DocMapperBuilder};

fn spec() -> FingerprintSpec {
    FingerprintSpec {
        format: FingerprintFormat::MorganR3Bits2048Lsb0V1,
        rdkit_version: "2026.09.1".into(),
        preparation_id: "sanitize-only-v1".into(),
    }
}

fn config() -> serde_json::Value {
    json!({"mode": "strict", "chemistry": {"spec": spec(), "smiles_field": "smiles", "prepared_smiles_field": "prepared_smiles"}, "field_mappings": [
        {"name":"record_id", "type":"u64", "fast": true},
        {"name":"smiles", "type":"text"},
        {"name":"prepared_smiles", "type":"text", "indexed":false},
        {"name":spec().field_name(), "type":"bytes", "fast":true, "indexed":false, "input_format":"hex", "output_format":"hex"}
    ]})
}

fn mapper() -> DocMapper {
    serde_json::from_value::<DocMapperBuilder>(config())
        .unwrap()
        .try_build()
        .unwrap()
}

#[test]
fn chemistry_mapping_schema_validation_and_roundtrip() {
    let mapper = mapper();
    let serialized = serde_json::to_value(&mapper).unwrap();
    assert_eq!(serialized["chemistry"], config()["chemistry"]);
    let _: DocMapper = serde_json::from_value(serialized).unwrap();
    for index in [0, 2, 3] {
        let mut bad = config();
        bad["field_mappings"].as_array_mut().unwrap().remove(index);
        assert!(
            serde_json::from_value::<DocMapperBuilder>(bad)
                .unwrap()
                .try_build()
                .is_err()
        );
    }
}

#[test]
fn chemistry_mapping_rejects_missing_null_multivalued_and_supplied_outputs() {
    let mapper = mapper();
    for value in [
        json!({"record_id":0}),
        json!({"record_id":0,"smiles":null}),
        json!({"record_id":0,"smiles":["CCO"]}),
        json!({"record_id":0,"smiles":"CCO","prepared_smiles":"CC"}),
        json!({"smiles":"CCO"}),
        json!({"record_id":0,"smiles":"bad-smiles"}),
    ] {
        assert!(
            mapper
                .doc_from_json_obj(value.as_object().unwrap().clone(), 0)
                .is_err()
        );
        let bytes = serde_json::to_vec(&value).unwrap();
        let borrowed: serde_json_borrow::Value = serde_json::from_slice(&bytes).unwrap();
        assert!(
            mapper
                .validate_json_obj(borrowed.as_object().unwrap())
                .is_err()
        );
    }
}

#[cfg(feature = "native-chemistry")]
#[test]
fn chemistry_mapping_raw_smiles_generates_native_fields() {
    let mapper = mapper();
    for smiles in ["CCO", "CC(=O)[O-].[Na+]", "c1ccccc1", "C[C@H](O)C(=O)O"] {
        let value = json!({"record_id":0,"smiles":smiles});
        let (partition, doc) = mapper
            .doc_from_json_obj(value.as_object().unwrap().clone(), 0)
            .unwrap();
        let expected =
            tantivy_rdkit_mapper::PreparedMolecule::from_smiles(smiles, &spec()).unwrap();
        let schema = mapper.schema();
        assert_eq!(
            doc.get_first(schema.get_field(&spec().field_name()).unwrap())
                .unwrap()
                .as_bytes()
                .unwrap(),
            expected.fingerprint.as_bytes()
        );
        assert_eq!(
            doc.get_first(schema.get_field("prepared_smiles").unwrap())
                .unwrap()
                .as_str()
                .unwrap(),
            expected.smiles
        );
        assert_eq!(partition, 0);
    }
}

#[cfg(not(feature = "native-chemistry"))]
#[test]
fn chemistry_mapping_requires_native_feature_for_ingestion() {
    let error = mapper()
        .doc_from_json_str(r#"{"record_id":0,"smiles":"CCO"}"#)
        .unwrap_err();
    assert!(error.to_string().contains("native-chemistry"));
}

#[test]
fn graph_contract_checks_mapping_and_field_inside_boolean_filters() {
    use quickwit_query::query_ast::{BoolQuery, GraphQueryAst, QueryAst};
    use tantivy_rdkit::{GraphPredicate, GraphRanking};
    let mapping: crate::ChemistryMapping =
        serde_json::from_value(config()["chemistry"].clone()).unwrap();
    let graph = GraphQueryAst {
        candidates: Box::new(QueryAst::MatchAll),
        spec: spec(),
        prepared_field: "prepared_smiles".into(),
        prepared_smiles: "CC".into(),
        predicate: GraphPredicate::Identity,
        ranking: GraphRanking::BestMatch,
        use_chirality: false,
        include_identity: true,
    };
    let valid = QueryAst::Graph(graph.clone());
    assert!(super::validate_graph_contract(&valid, Some(&mapping)).is_ok());
    assert!(super::validate_graph_contract(&valid, None).is_err());
    let mut wrong = graph;
    wrong.prepared_field = "smiles".into();
    let nested = QueryAst::Bool(BoolQuery {
        filter: vec![QueryAst::Graph(wrong)],
        ..Default::default()
    });
    assert!(super::validate_graph_contract(&nested, Some(&mapping)).is_err());
    let mut other_mapping = mapping;
    other_mapping.spec.preparation_id = "other".into();
    assert!(super::validate_graph_contract(&valid, Some(&other_mapping)).is_err());
}

#[cfg(feature = "descriptor-v1")]
fn descriptor_config() -> serde_json::Value {
    let mut value = config();
    value["chemistry"]["descriptor_v1"] = true.into();
    value["chemistry"]["spec"]["preparation_id"] =
        tantivy_rdkit_mapper::CHEMINEE_PREPARATION_ID.into();
    let full_spec: FingerprintSpec =
        serde_json::from_value(value["chemistry"]["spec"].clone()).unwrap();
    value["field_mappings"][3]["name"] = full_spec.field_name().into();
    let mappings = value["field_mappings"].as_array_mut().unwrap();
    for name in tantivy_rdkit_mapper::descriptor::KNOWN_DESCRIPTORS {
        mappings.push(json!({"name":name,"type":if name.starts_with("Num") || name.starts_with("lipinski") {"i64"} else {"f64"}}));
    }
    mappings.push(json!({"name":"pattern_fingerprint","type":"bytes","input_format":"base64"}));
    mappings.push(json!({"name":"other_descriptors","type":"json"}));
    value
}

#[cfg(feature = "descriptor-v1")]
#[test]
fn descriptor_mapping_prepares_validates_and_rejects_forged_outputs() {
    let mapper = serde_json::from_value::<DocMapperBuilder>(descriptor_config())
        .unwrap()
        .try_build()
        .unwrap();
    let input = json!({"record_id":1,"smiles":"CCO"});
    let (_, doc) = mapper
        .doc_from_json_obj(input.as_object().unwrap().clone(), 0)
        .unwrap();
    let schema = mapper.schema();
    assert_eq!(
        doc.get_first(schema.get_field("NumHeavyAtoms").unwrap())
            .unwrap()
            .as_i64(),
        Some(3)
    );
    assert!(
        doc.get_first(schema.get_field("other_descriptors").unwrap())
            .is_some()
    );
    for name in ["NumHeavyAtoms", "other_descriptors", "pattern_fingerprint"] {
        let mut forged = input.clone();
        forged[name] = json!(0);
        assert!(
            mapper
                .doc_from_json_obj(forged.as_object().unwrap().clone(), 0)
                .is_err()
        );
        let bytes = serde_json::to_vec(&forged).unwrap();
        let borrowed: serde_json_borrow::Value = serde_json::from_slice(&bytes).unwrap();
        assert!(
            mapper
                .validate_json_obj(borrowed.as_object().unwrap())
                .is_err()
        );
    }
    let mut missing = descriptor_config();
    missing["field_mappings"].as_array_mut().unwrap().pop();
    assert!(
        serde_json::from_value::<DocMapperBuilder>(missing)
            .unwrap()
            .try_build()
            .is_err()
    );
}

#[cfg(feature = "descriptor-v1")]
fn nested_descriptor_config() -> serde_json::Value {
    let mut config = descriptor_config();
    config["chemistry"]["descriptor_layout"] = json!("nested");
    let mappings = config["field_mappings"].as_array_mut().unwrap();
    mappings.retain(|field| {
        !tantivy_rdkit::descriptor_v1::KNOWN_DESCRIPTORS.contains(&field["name"].as_str().unwrap())
    });
    mappings.push(json!({"name":"descriptors","type":"json","fast":true}));
    config
}

#[cfg(feature = "descriptor-v1")]
#[test]
fn nested_descriptor_mapping_requires_searchable_stored_fast_json() {
    let config = nested_descriptor_config();
    let mapper = serde_json::from_value::<DocMapperBuilder>(config.clone())
        .unwrap()
        .try_build()
        .unwrap();
    let serialized = serde_json::to_value(&mapper).unwrap();
    assert_eq!(serialized["chemistry"]["descriptor_layout"], "nested");
    assert!(mapper.schema().get_field("descriptors").is_ok());
    assert!(mapper.schema().get_field("NumAtoms").is_err());
    for option in ["fast", "indexed", "stored"] {
        let mut bad = config.clone();
        bad["field_mappings"]
            .as_array_mut()
            .unwrap()
            .last_mut()
            .unwrap()[option] = json!(false);
        assert!(
            serde_json::from_value::<DocMapperBuilder>(bad)
                .unwrap()
                .try_build()
                .is_err()
        );
    }
    let mut duplicate = config.clone();
    duplicate["field_mappings"]
        .as_array_mut()
        .unwrap()
        .push(json!({"name":"NumAtoms","type":"i64"}));
    assert!(
        serde_json::from_value::<DocMapperBuilder>(duplicate)
            .unwrap()
            .try_build()
            .is_err()
    );
    let mut disabled = config;
    disabled["chemistry"]["descriptor_v1"] = json!(false);
    assert!(
        serde_json::from_value::<DocMapperBuilder>(disabled)
            .unwrap()
            .try_build()
            .is_err()
    );
}

#[cfg(feature = "descriptor-v1")]
#[test]
fn nested_descriptor_outputs_match_flat_and_reject_forgery_in_dynamic_mode() {
    let mut config = nested_descriptor_config();
    config["mode"] = json!("dynamic");
    let nested: crate::ChemistryMapping =
        serde_json::from_value(config["chemistry"].clone()).unwrap();
    let flat: crate::ChemistryMapping =
        serde_json::from_value(descriptor_config()["chemistry"].clone()).unwrap();
    let input = json!({"record_id":1,"smiles":"CCO"});
    let actual = nested.prepare(input.as_object().unwrap().clone()).unwrap();
    let expected = flat.prepare(input.as_object().unwrap().clone()).unwrap();
    assert_eq!(actual["descriptors"].as_object().unwrap().len(), 43);
    for name in tantivy_rdkit::descriptor_v1::KNOWN_DESCRIPTORS {
        assert_eq!(actual["descriptors"][name], expected[name]);
        assert!(!actual.contains_key(name));
    }
    assert!(actual["descriptors"]["NumHeavyAtoms"].is_i64());
    assert!(actual["descriptors"]["exactmw"].is_f64());
    let mapper = serde_json::from_value::<DocMapperBuilder>(config)
        .unwrap()
        .try_build()
        .unwrap();
    for (field, value) in [
        ("descriptors", json!({"NumAtoms":99})),
        ("descriptors", json!(null)),
        ("descriptors", json!([])),
        ("NumAtoms", json!(99)),
        ("exactmw", json!(0.0)),
    ] {
        let mut forged = input.clone();
        forged[field] = value;
        assert!(
            mapper
                .doc_from_json_obj(forged.as_object().unwrap().clone(), 0)
                .is_err()
        );
        let bytes = serde_json::to_vec(&forged).unwrap();
        let borrowed: serde_json_borrow::Value = serde_json::from_slice(&bytes).unwrap();
        assert!(
            mapper
                .validate_json_obj(borrowed.as_object().unwrap())
                .is_err()
        );
    }
}
