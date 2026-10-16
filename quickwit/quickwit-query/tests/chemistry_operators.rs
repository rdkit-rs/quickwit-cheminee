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

use quickwit_query::ElasticQueryDsl;
use quickwit_query::query_ast::{BuildTantivyAstContext, QueryAst, query_ast_from_user_text};
use serde_json::{Value, json};
use tantivy::collector::{Count, TopDocs};
use tantivy::schema::{FAST, Schema};
use tantivy::{Index, TantivyDocument, doc};
use tantivy_rdkit::{FingerprintFormat, FingerprintSpec};

fn spec() -> FingerprintSpec {
    FingerprintSpec {
        format: FingerprintFormat::MorganR3Bits2048Lsb0V1,
        rdkit_version: "2026.09.1".into(),
        preparation_id: "sanitize-only-v1".into(),
    }
}
fn operand() -> Value {
    json!({"spec":spec(), "fingerprint_hex":format!("03{}", "00".repeat(255)), "minimum":0.5})
}
fn text_ast(text: &str) -> QueryAst {
    query_ast_from_user_text(text, None)
        .parse_user_query(&[])
        .unwrap()
}
fn json_ast(value: Value) -> QueryAst {
    let dsl: ElasticQueryDsl = serde_json::from_value(value).unwrap();
    QueryAst::try_from(dsl)
        .unwrap()
        .parse_user_query(&[])
        .unwrap()
}
#[test]
fn text_json_equivalent_ast_and_scores_with_nested_descriptor_ranges() -> tantivy::Result<()> {
    let arg = operand();
    assert_eq!(
        text_ast(&format!("_tanimoto:'{arg}'")),
        json_ast(json!({"tanimoto":arg}))
    );
    let text = text_ast(&format!("_tanimoto:'{arg}' AND descriptors.amw:[0 TO 50]"));
    assert_eq!(
        text,
        json_ast(json!({"bool":{"must":[{"tanimoto":arg},
        {"range":{"descriptors.amw":{"gte":"0","lte":"50"}}}]}}))
    );
    let json = json_ast(json!({"bool":{"must":[{"tanimoto":arg},
        {"range":{"descriptors.amw":{"gte":0,"lte":50}}}]}}));
    let mut builder = Schema::builder();
    let fp = builder.add_bytes_field(&spec().field_name(), FAST);
    let descriptors = builder.add_json_field("descriptors", FAST);
    let schema = builder.build();
    let index = Index::create_in_ram(schema.clone());
    let mut writer = index.writer_with_num_threads::<TantivyDocument>(1, 15_000_000)?;
    for (bits, weight) in [(1, 10), (3, 20), (7, 30), (3, 100), (128, 10)] {
        let mut bytes = vec![0u8; 256];
        bytes[0] = bits;
        writer.add_document(doc!(fp=>bytes, descriptors=>json!({"amw":weight})))?;
    }
    writer.commit()?;
    let reader = index.reader()?;
    let searcher = reader.searcher();
    let run = |ast: QueryAst| {
        let query = ast
            .build_tantivy_query(&BuildTantivyAstContext::for_test(&schema))
            .unwrap();
        searcher
            .search(&*query, &(TopDocs::with_limit(10).order_by_score(), Count))
            .unwrap()
    };
    let (hits, count) = run(text);
    assert_eq!(count, 3);
    assert_eq!(
        hits.iter().map(|(score, _)| *score).collect::<Vec<_>>(),
        vec![2.0, 1.0 + 2.0 / 3.0, 1.5]
    );
    assert_eq!((hits, count), run(json));
    for (text_query, json_query, expected_count) in [
        (
            format!("_tanimoto:'{arg}' OR descriptors.amw:[0 TO 50]"),
            json!({"bool":{"should":[{"tanimoto":arg},{"range":{"descriptors.amw":{"gte":"0","lte":"50"}}}]}}),
            5,
        ),
        (
            format!("_tanimoto:'{arg}' AND NOT descriptors.amw:[0 TO 50]"),
            json!({"bool":{"must":[{"tanimoto":arg},{"bool":{"must_not":[{"range":{"descriptors.amw":{"gte":"0","lte":"50"}}}]}}]}}),
            1,
        ),
    ] {
        let text = text_ast(&text_query);
        let json = json_ast(json_query);
        assert_eq!(text, json);
        let actual = run(text);
        assert_eq!(actual.1, expected_count);
        assert_eq!(actual, run(json));
    }
    let mut candidate_arg = arg.clone();
    candidate_arg["candidates"] = json!({"type":"range","field":"descriptors.amw",
        "lower_bound":{"Included":0},"upper_bound":{"Included":50}});
    let candidate_text = text_ast(&format!("_tanimoto:'{candidate_arg}'"));
    let candidate_json = json_ast(json!({"tanimoto":candidate_arg}));
    assert_eq!(candidate_text, candidate_json);
    let actual = run(candidate_text);
    assert_eq!(actual.1, 3);
    assert_eq!(actual, run(candidate_json));
    let mut user_candidates = arg.clone();
    user_candidates["candidates"] =
        serde_json::to_value(query_ast_from_user_text("descriptors.amw:[0 TO 50]", None)).unwrap();
    let candidate_text = text_ast(&format!("_tanimoto:'{user_candidates}'"));
    let candidate_json = json_ast(json!({"tanimoto":user_candidates}));
    assert_eq!(candidate_text, candidate_json);
    let actual = run(candidate_text);
    assert_eq!(actual.1, 3);
    assert_eq!(actual, run(candidate_json));
    let (filtered, count) = run(json_ast(json!({"bool":{"filter":[{"tanimoto":arg}]}})));
    assert_eq!(count, 4);
    assert!(filtered.iter().all(|(score, _)| *score == 0.0));
    Ok(())
}
#[test]
fn all_operator_encodings_and_rejections() {
    let mut containment = operand();
    containment.as_object_mut().unwrap().remove("minimum");
    containment["direction"] = json!("document_contains_query");
    let graph = json!({"spec":spec(),"prepared_field":"prepared_smiles","prepared_smiles":"CC",
        "predicate":"substructure","ranking":"best_match","use_chirality":false,"include_identity":true});
    for (name, arg) in [
        ("tanimoto", operand()),
        ("fingerprint_contains", containment),
        ("molecular_graph", graph),
    ] {
        let ast = text_ast(&format!("_{name}:'{arg}'"));
        assert_eq!(ast, json_ast(json!({name:arg})));
        assert_eq!(
            ast,
            serde_json::from_str::<QueryAst>(&serde_json::to_string(&ast).unwrap()).unwrap()
        );
        assert!(
            query_ast_from_user_text(&format!("_{name}:'{arg}'~2"), None)
                .parse_user_query(&[])
                .is_err()
        );
        let mut invalid = arg.clone();
        invalid["ann"] = json!(true);
        assert!(serde_json::from_value::<ElasticQueryDsl>(json!({name:invalid})).is_err());
        assert!(
            query_ast_from_user_text(&format!("_{name}:'{invalid}'"), None)
                .parse_user_query(&[])
                .is_err()
        );
    }
    let schema = Schema::builder().build();
    for minimum in [-1.0, 1.1] {
        let mut arg = operand();
        arg["minimum"] = json!(minimum);
        let ast = json_ast(json!({"tanimoto":arg}));
        assert!(
            ast.build_tantivy_query(
                &BuildTantivyAstContext::for_test(&schema).without_validation()
            )
            .is_err()
        );
    }
    for malformed in ["_tanimoto:abc", "_tanimoto:'{}'", "_molecular_graph:'{}'"] {
        assert!(
            query_ast_from_user_text(malformed, None)
                .parse_user_query(&[])
                .is_err()
        );
    }
}

#[cfg(feature = "native-chemistry")]
#[test]
fn graph_text_json_execute_both_directions_and_negation() -> tantivy::Result<()> {
    let mut builder = Schema::builder();
    let fields =
        tantivy_rdkit::MoleculeFields::add_to_schema(&mut builder, &spec(), "prepared_smiles")?;
    let schema = builder.build();
    let index = Index::create_in_ram(schema.clone());
    let mut writer = index.writer_with_num_threads::<TantivyDocument>(1, 15_000_000)?;
    for smiles in ["C", "CC", "CCC"] {
        let prepared =
            tantivy_rdkit_mapper::PreparedMolecule::from_smiles(smiles, &spec()).unwrap();
        writer.add_document(
            doc!(fields.fingerprint=>prepared.fingerprint.as_bytes().to_vec(),
            fields.prepared_smiles=>prepared.smiles),
        )?;
    }
    writer.commit()?;
    let reader = index.reader()?;
    let searcher = reader.searcher();
    for (predicate, expected) in [
        ("substructure", vec![1.0, 0.5]),
        ("superstructure", vec![1.0, 0.5]),
        ("identity", vec![1.0]),
    ] {
        let arg = json!({"spec":spec(),"prepared_field":"prepared_smiles","prepared_smiles":"CC",
            "predicate":predicate,"ranking":"best_match","use_chirality":false,"include_identity":true});
        let text = text_ast(&format!("_molecular_graph:'{arg}'"));
        let json = json_ast(json!({"molecular_graph":arg}));
        assert_eq!(text, json);
        let run = |ast: QueryAst| {
            let query = ast
                .build_tantivy_query(&BuildTantivyAstContext::for_test(&schema))
                .unwrap();
            searcher
                .search(&*query, &(TopDocs::with_limit(10).order_by_score(), Count))
                .unwrap()
        };
        let (hits, count) = run(text);
        assert_eq!(count, expected.len());
        assert_eq!(
            hits.iter().map(|(score, _)| *score).collect::<Vec<_>>(),
            expected
        );
        assert_eq!((hits, count), run(json));
        let (text, json) = (
            text_ast(&format!("NOT _molecular_graph:'{arg}'")),
            json_ast(json!({"bool":{"must_not":[{"molecular_graph":arg}]}})),
        );
        assert_eq!(text, json);
        let actual = run(text);
        assert_eq!(actual.1, 3 - count);
        assert_eq!(actual, run(json));
    }
    Ok(())
}

#[test]
fn quoted_chemistry_preserves_json_escaping_and_rejects_oversize_operands() {
    let mut arg = json!({"spec":spec(),"prepared_field":"prepared_smiles",
        "prepared_smiles":r"F/C=C\F","predicate":"substructure","ranking":"best_match",
        "use_chirality":true,"include_identity":true});
    let escaped = arg.to_string().replace('\\', "\\\\").replace('\'', "\\'");
    assert_eq!(
        text_ast(&format!("_molecular_graph:'{escaped}'")),
        json_ast(json!({"molecular_graph":arg}))
    );
    arg["prepared_smiles"] = json!("C".repeat(65_536));
    assert!(
        query_ast_from_user_text(&format!("_molecular_graph:'{arg}'"), None)
            .parse_user_query(&[])
            .is_err()
    );
}
