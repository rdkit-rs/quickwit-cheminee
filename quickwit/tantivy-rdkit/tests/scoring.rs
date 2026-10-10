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

use tantivy::collector::{Count, TopDocs};
use tantivy::query::{AllQuery, Query, TermQuery};
use tantivy::schema::{FAST, INDEXED, IndexRecordOption, Schema};
use tantivy::{Index, TERMINATED, TantivyDocument, Term, doc};
use tantivy_rdkit::{FingerprintFormat, FingerprintSpec, PackedFingerprint, TanimotoQuery};

fn spec() -> FingerprintSpec {
    FingerprintSpec {
        format: FingerprintFormat::MorganR3Bits2048Lsb0V1,
        rdkit_version: "2025.03.1".into(),
        preparation_id: "identity-v1".into(),
    }
}

fn fingerprint(first: u8) -> Vec<u8> {
    let mut bytes = vec![0; 256];
    bytes[0] = first;
    bytes
}

#[test]
fn threshold_filters_scores_seek_and_count() -> tantivy::Result<()> {
    let mut builder = Schema::builder();
    let field = builder.add_bytes_field(&spec().field_name(), FAST);
    let group = builder.add_u64_field("group", INDEXED);
    let schema = builder.build();
    let index = Index::create_in_ram(schema.clone());
    let mut writer = index.writer_with_num_threads::<TantivyDocument>(1, 15_000_000)?;
    for (value, group_id) in [(0, 1u64), (1, 1), (3, 1), (7, 1), (3, 2), (128, 1)] {
        writer.add_document(doc!(field => fingerprint(value), group => group_id))?;
    }
    writer.commit()?;
    let reader = index.reader()?;
    let searcher = reader.searcher();
    let query = TanimotoQuery::new(
        Box::new(TermQuery::new(
            Term::from_field_u64(group, 1),
            IndexRecordOption::Basic,
        )),
        &schema,
        &spec(),
        PackedFingerprint::from_hex(&hex::encode(fingerprint(3)))?,
        0.5,
    )?;
    let (hits, count) =
        searcher.search(&query, &(TopDocs::with_limit(10).order_by_score(), Count))?;
    assert_eq!(count, 3);
    assert_eq!(
        hits.iter().map(|(score, _)| *score).collect::<Vec<_>>(),
        vec![1.0, 2.0 / 3.0, 0.5]
    );
    let weight = query.weight(tantivy::query::EnableScoring::enabled_from_searcher(
        &searcher,
    ))?;
    let mut scorer = weight.scorer(searcher.segment_reader(0), 1.0)?;
    assert_eq!(scorer.doc(), 1);
    assert_eq!(scorer.seek(2), 2);
    assert_eq!(scorer.score(), 1.0);
    assert_eq!(scorer.advance(), 3);
    assert_eq!(scorer.advance(), TERMINATED);
    Ok(())
}

#[test]
fn malformed_missing_and_multivalued_data_fail_closed() -> tantivy::Result<()> {
    for values in [
        vec![],
        vec![vec![1; 255]],
        vec![fingerprint(1), fingerprint(2)],
    ] {
        let mut builder = Schema::builder();
        let field = builder.add_bytes_field(&spec().field_name(), FAST);
        let schema = builder.build();
        let index = Index::create_in_ram(schema.clone());
        let mut writer = index.writer_with_num_threads::<TantivyDocument>(1, 15_000_000)?;
        let mut document = TantivyDocument::new();
        for value in values {
            document.add_bytes(field, &value);
        }
        writer.add_document(document)?;
        writer.commit()?;
        let reader = index.reader()?;
        let query = TanimotoQuery::new(
            Box::new(AllQuery),
            &schema,
            &spec(),
            PackedFingerprint::from_hex(&hex::encode(fingerprint(1)))?,
            0.0,
        )?;
        assert!(reader.searcher().search(&query, &Count).is_err());
    }
    Ok(())
}

#[test]
fn rejects_invalid_specs_queries_and_schema() {
    for value in [
        "".to_string(),
        "0".repeat(512),
        "g".repeat(512),
        "1".repeat(510),
    ] {
        assert!(PackedFingerprint::from_hex(&value).is_err());
    }
    let mut version = spec();
    version.preparation_id = "a\0b".into();
    assert!(version.validate().is_err());
    version = spec();
    version.rdkit_version = "2026.09.1".into();
    assert_ne!(version.field_name(), spec().field_name());
    let mut builder = Schema::builder();
    builder.add_bytes_field(&spec().field_name(), INDEXED);
    let schema = builder.build();
    for minimum in [f32::NAN, f32::INFINITY, -0.1, 1.1, 0.5] {
        let query = TanimotoQuery::new(
            Box::new(AllQuery),
            &schema,
            &spec(),
            PackedFingerprint::from_hex(&hex::encode(fingerprint(3))).unwrap(),
            minimum,
        );
        assert!(query.is_err());
    }
}

#[test]
fn packed_bytes_are_fixed_width_and_lsb0() {
    let mut bytes = [0; 256];
    bytes[0] = 0x81;
    bytes[255] = 0x80;
    let fingerprint = PackedFingerprint::from_bytes(&bytes).unwrap();
    assert_eq!(fingerprint.as_bytes(), &bytes);
    assert_eq!(
        PackedFingerprint::from_hex(&fingerprint.to_hex()).unwrap(),
        fingerprint
    );
    for wrong in [vec![], vec![1; 255], vec![1; 257], vec![0; 256]] {
        assert!(PackedFingerprint::from_bytes(&wrong).is_err());
    }
}
