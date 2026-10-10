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
