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
use std::sync::atomic::{AtomicUsize, Ordering};

use tantivy::collector::{Count, TopDocs};
use tantivy::merge_policy::NoMergePolicy;
use tantivy::query::{AllQuery, BooleanQuery, EmptyQuery, Occur, Query, TermQuery};
use tantivy::schema::{FAST, INDEXED, IndexRecordOption, STORED, Schema};
use tantivy::{DocSet, Index, TERMINATED, TantivyDocument, Term, doc};
use tantivy_rdkit::{
    ContainmentDirection, FingerprintFormat, FingerprintSpec, GraphQuery, GraphVerifier,
    MoleculeMatcher, PackedFingerprint, TanimotoQuery,
};
fn spec() -> FingerprintSpec {
    FingerprintSpec {
        format: FingerprintFormat::MorganR3Bits2048Lsb0V1,
        rdkit_version: "2026.09.1".into(),
        preparation_id: "sanitize-only-v1".into(),
    }
}
fn bytes(bits: u8) -> Vec<u8> {
    let mut bytes = vec![0; 256];
    bytes[0] = bits;
    bytes
}

#[test]
fn containment_directions_thresholds_candidates_and_seek() -> tantivy::Result<()> {
    let mut builder = Schema::builder();
    let fp = builder.add_bytes_field(&spec().field_name(), FAST);
    let group = builder.add_u64_field("group", INDEXED);
    let schema = builder.build();
    let index = Index::create_in_ram(schema.clone());
    let mut writer = index.writer_with_num_threads::<TantivyDocument>(1, 15_000_000)?;
    for bits in [1, 3, 7, 128] {
        writer.add_document(doc!(fp=>bytes(bits),group=>1u64))?;
    }
    // Invalid but outside the explicit candidate domain.
    writer.add_document(doc!(fp=>vec![1u8],group=>2u64))?;
    writer.commit()?;
    let reader = index.reader()?;
    let searcher = reader.searcher();
    for (direction, expected) in [
        (ContainmentDirection::DocumentContainsQuery, vec![1, 2]),
        (ContainmentDirection::QueryContainsDocument, vec![0, 1]),
    ] {
        let query = TanimotoQuery::containment(
            Box::new(TermQuery::new(
                Term::from_field_u64(group, 1),
                IndexRecordOption::Basic,
            )),
            &schema,
            &spec(),
            PackedFingerprint::from_bytes(&bytes(3))?,
            direction,
        )?;
        assert_eq!(searcher.search(&query, &Count)?, 2);
        let weight = query.weight(tantivy::query::EnableScoring::enabled_from_searcher(
            &searcher,
        ))?;
        let mut scorer = weight.scorer(searcher.segment_reader(0), 2.0)?;
        assert_eq!(scorer.doc(), expected[0]);
        assert_eq!(scorer.score(), 2.0);
        assert_eq!(scorer.seek(expected[1]), expected[1]);
        assert_eq!(scorer.advance(), TERMINATED);
        assert_eq!(scorer.seek(TERMINATED), TERMINATED);
        assert_eq!(scorer.advance(), TERMINATED);
    }
    let query = TanimotoQuery::new(
        Box::new(AllQuery),
        &schema,
        &spec(),
        PackedFingerprint::from_bytes(&bytes(3))?,
        0.0,
    )?;
    assert!(searcher.search(&query, &Count).is_err());
    Ok(())
}

#[derive(Debug)]
struct Verifier(Arc<AtomicUsize>);
struct Matcher(Arc<AtomicUsize>);
impl GraphVerifier for Verifier {
    fn matcher(&self) -> tantivy::Result<Box<dyn MoleculeMatcher>> {
        Ok(Box::new(Matcher(self.0.clone())))
    }
}
impl MoleculeMatcher for Matcher {
    fn score(&mut self, smiles: &str) -> tantivy::Result<Option<f32>> {
        if smiles == "excluded" {
            return Err(tantivy::TantivyError::InvalidArgument(
                "excluded molecule was verified".into(),
            ));
        }
        self.0.fetch_add(1, Ordering::SeqCst);
        Ok((smiles == "accepted").then_some(0.5))
    }
}
#[test]
fn graph_checks_only_distinct_live_candidates_and_never_truncates_before_verification()
-> tantivy::Result<()> {
    let mut builder = Schema::builder();
    builder.add_bytes_field(&spec().field_name(), FAST);
    let mol = builder.add_text_field("prepared_smiles", FAST | STORED);
    let group = builder.add_u64_field("group", INDEXED);
    let deleted = builder.add_u64_field("deleted", INDEXED);
    let schema = builder.build();
    let index = Index::create_in_ram(schema.clone());
    let mut writer = index.writer_with_num_threads::<TantivyDocument>(1, 15_000_000)?;
    writer.add_document(doc!(mol=>"excluded",group=>2u64))?;
    for _ in 0..100 {
        writer.add_document(doc!(mol=>"rejected",group=>1u64))?;
    }
    for _ in 0..2 {
        writer.add_document(doc!(mol=>"accepted",group=>1u64))?;
    }
    writer.add_document(doc!(mol=>"excluded",group=>1u64,deleted=>1u64))?;
    writer.commit()?;
    writer.delete_term(Term::from_field_u64(deleted, 1));
    writer.commit()?;
    let calls = Arc::new(AtomicUsize::new(0));
    let query = GraphQuery::new(
        Box::new(TermQuery::new(
            Term::from_field_u64(group, 1),
            IndexRecordOption::Basic,
        )),
        &schema,
        &spec(),
        "prepared_smiles".into(),
        Arc::new(Verifier(calls.clone())),
    )?;
    let reader = index.reader()?;
    let searcher = reader.searcher();
    let (hits, count) =
        searcher.search(&query, &(TopDocs::with_limit(1).order_by_score(), Count))?;
    assert_eq!(count, 2);
    assert_eq!(hits.len(), 1);
    assert_eq!(hits[0].0, 0.5);
    assert_eq!(calls.load(Ordering::SeqCst), 2);
    // A sibling filter does not become an embedded candidate constraint. Its exclusion
    // therefore cannot mask a verifier error in the broader chemistry domain.
    let broad = GraphQuery::new(
        Box::new(AllQuery),
        &schema,
        &spec(),
        "prepared_smiles".into(),
        Arc::new(Verifier(calls)),
    )?;
    let adjacent = BooleanQuery::new(vec![
        (Occur::Must, Box::new(broad)),
        (
            Occur::Must,
            Box::new(TermQuery::new(
                Term::from_field_u64(group, 1),
                IndexRecordOption::Basic,
            )),
        ),
    ]);
    assert!(searcher.search(&adjacent, &Count).is_err());
    Ok(())
}

#[test]
fn explicit_score_and_id_order_survives_per_split_top_k() -> tantivy::Result<()> {
    use std::cmp::Reverse;
    let collect = |rows: &[(u8, u64)]| -> tantivy::Result<_> {
        let mut builder = Schema::builder();
        let fp = builder.add_bytes_field(&spec().field_name(), FAST);
        let id = builder.add_u64_field("record_id", FAST);
        let schema = builder.build();
        let index = Index::create_in_ram(schema.clone());
        let mut writer = index.writer_with_num_threads::<TantivyDocument>(1, 15_000_000)?;
        for &(bits, record_id) in rows {
            writer.add_document(doc!(fp=>bytes(bits), id=>record_id))?;
        }
        writer.commit()?;
        let reader = index.reader()?;
        let query = TanimotoQuery::new(
            Box::new(AllQuery),
            &schema,
            &spec(),
            PackedFingerprint::from_bytes(&bytes(3))?,
            0.0,
        )?;
        let collector = TopDocs::with_limit(2).tweak_score(|segment: &tantivy::SegmentReader| {
            let ids = segment.fast_fields().u64("record_id").unwrap();
            move |doc: tantivy::DocId, score: f32| (score, Reverse(ids.first(doc).unwrap()))
        });
        let (hits, count) = reader.searcher().search(&query, &(collector, Count))?;
        Ok((
            hits.into_iter().map(|(key, _)| key).collect::<Vec<_>>(),
            count,
        ))
    };
    let left = [(3, 9), (1, 5), (3, 1)];
    let right = [(7, 4), (3, 2), (3, 7)];
    let (mut left_hits, left_count) = collect(&left)?;
    let (right_hits, right_count) = collect(&right)?;
    left_hits.extend(right_hits);
    left_hits.sort_by(|a, b| b.partial_cmp(a).unwrap());
    left_hits.truncate(2);
    let (global_hits, global_count) = collect(&[left, right].concat())?;
    assert_eq!(left_count + right_count, global_count);
    assert_eq!(global_count, 6);
    assert_eq!(left_hits, global_hits);
    assert_eq!(global_hits, vec![(1.0, Reverse(1)), (1.0, Reverse(2))]);
    Ok(())
}

#[derive(Clone, Copy, Debug)]
enum Operator {
    Graph,
    Tanimoto,
    Containment,
}
const OPERATORS: [Operator; 3] = [Operator::Graph, Operator::Tanimoto, Operator::Containment];
impl Operator {
    fn query(self, schema: &Schema, candidates: Box<dyn Query>) -> tantivy::Result<Box<dyn Query>> {
        Ok(match self {
            Self::Graph => Box::new(GraphQuery::new(
                candidates,
                schema,
                &spec(),
                "prepared_smiles".into(),
                Arc::new(Verifier(Arc::new(AtomicUsize::new(0)))),
            )?),
            Self::Tanimoto => Box::new(TanimotoQuery::new(
                candidates,
                schema,
                &spec(),
                PackedFingerprint::from_bytes(&bytes(1))?,
                0.0,
            )?),
            Self::Containment => Box::new(TanimotoQuery::containment(
                candidates,
                schema,
                &spec(),
                PackedFingerprint::from_bytes(&bytes(1))?,
                ContainmentDirection::DocumentContainsQuery,
            )?),
        })
    }
}

// Keep invalid values in the same segment as a healthy candidate. Disabling merges
// and asserting max_doc after deletion prevents a vacuous deleted-value test.
fn error_domain_index(kind: &str, delete_invalid: bool) -> tantivy::Result<Index> {
    let mut builder = Schema::builder();
    let fp = builder.add_bytes_field(&spec().field_name(), FAST);
    let mol = builder.add_text_field("prepared_smiles", FAST | STORED);
    let group = builder.add_u64_field("group", INDEXED);
    let index = Index::create_in_ram(builder.build());
    let mut writer = index.writer_with_num_threads::<TantivyDocument>(1, 15_000_000)?;
    writer.set_merge_policy(Box::new(NoMergePolicy));
    writer.add_document(doc!(fp=>bytes(1), mol=>"accepted", group=>1u64))?;
    let invalid = match kind {
        "missing" => doc!(group=>2u64),
        "multivalued" => {
            doc!(fp=>bytes(1), fp=>bytes(3), mol=>"accepted", mol=>"rejected", group=>2u64)
        }
        "malformed" => doc!(fp=>vec![1u8], mol=>"excluded", group=>2u64),
        _ => panic!("unknown fixture"),
    };
    writer.add_document(invalid)?;
    writer.commit()?;
    if delete_invalid {
        writer.delete_term(Term::from_field_u64(group, 2));
        writer.commit()?;
    }
    Ok(index)
}

#[test]
fn graph_and_fingerprint_errors_are_scoped_to_explicit_candidates() -> tantivy::Result<()> {
    for kind in ["missing", "multivalued", "malformed"] {
        let index = error_domain_index(kind, false)?;
        let schema = index.schema();
        let group = schema.get_field("group")?;
        let reader = index.reader()?;
        let searcher = reader.searcher();
        assert_eq!(searcher.segment_readers().len(), 1);
        for operator in OPERATORS {
            let candidates = Box::new(TermQuery::new(
                Term::from_field_u64(group, 1),
                IndexRecordOption::Basic,
            ));
            let selective = operator.query(&schema, candidates)?;
            assert_eq!(
                searcher.search(&*selective, &Count)?,
                1,
                "{operator:?} {kind}"
            );
            let broad = operator.query(&schema, Box::new(AllQuery))?;
            let error = searcher
                .search(&*broad, &Count)
                .expect_err("live invalid value must fail");
            let expected = if kind == "malformed" {
                match operator {
                    Operator::Graph => "excluded molecule was verified",
                    _ => "256 bytes",
                }
            } else {
                "exactly one"
            };
            assert!(
                error.to_string().contains(expected),
                "{operator:?} {kind}: {error}"
            );
        }
    }
    Ok(())
}

#[test]
fn graph_and_fingerprint_ignore_deleted_invalid_values() -> tantivy::Result<()> {
    for kind in ["missing", "multivalued", "malformed"] {
        let index = error_domain_index(kind, true)?;
        let reader = index.reader()?;
        let searcher = reader.searcher();
        assert_eq!(searcher.segment_readers().len(), 1);
        assert_eq!(searcher.segment_reader(0).max_doc(), 2);
        assert_eq!(searcher.segment_reader(0).num_docs(), 1);
        for operator in OPERATORS {
            let query = operator.query(&index.schema(), Box::new(AllQuery))?;
            assert_eq!(searcher.search(&*query, &Count)?, 1, "{operator:?} {kind}");
        }
    }
    Ok(())
}

#[test]
fn graph_and_fingerprint_require_columns_only_for_live_candidates() -> tantivy::Result<()> {
    let mut builder = Schema::builder();
    builder.add_bytes_field(&spec().field_name(), FAST);
    builder.add_text_field("prepared_smiles", FAST | STORED);
    let query_schema = builder.build();
    // A schema-declared but unpopulated fast field has an empty column. Use an
    // older segment schema to exercise an actually absent column, as can happen
    // when a field is introduced after a split was written.
    let mut builder = Schema::builder();
    let group = builder.add_u64_field("group", INDEXED);
    let index = Index::create_in_ram(builder.build());
    let mut writer = index.writer_with_num_threads::<TantivyDocument>(1, 15_000_000)?;
    writer.set_merge_policy(Box::new(NoMergePolicy));
    writer.add_document(doc!(group=>1u64))?;
    writer.add_document(doc!(group=>2u64))?;
    writer.commit()?;
    let reader = index.reader()?;
    let searcher = reader.searcher();
    assert!(
        searcher
            .segment_reader(0)
            .fast_fields()
            .bytes(&spec().field_name())?
            .is_none()
    );
    assert!(
        searcher
            .segment_reader(0)
            .fast_fields()
            .str("prepared_smiles")?
            .is_none()
    );
    for operator in OPERATORS {
        let query = operator.query(&query_schema, Box::new(EmptyQuery))?;
        assert_eq!(searcher.search(&*query, &Count)?, 0, "{operator:?}");
        let query = operator.query(&query_schema, Box::new(AllQuery))?;
        let error = searcher
            .search(&*query, &Count)
            .expect_err("missing segment column with live candidates must fail");
        let expected = match operator {
            Operator::Graph => "missing prepared SMILES fast field",
            _ => "missing fingerprint fast field",
        };
        assert!(
            error.to_string().contains(expected),
            "{operator:?}: {error}"
        );
    }
    writer.delete_term(Term::from_field_u64(group, 2));
    writer.commit()?;
    reader.reload()?;
    let searcher = reader.searcher();
    assert_eq!(searcher.segment_reader(0).max_doc(), 2);
    assert_eq!(searcher.segment_reader(0).num_docs(), 1);
    for operator in OPERATORS {
        let deleted_only = Box::new(TermQuery::new(
            Term::from_field_u64(group, 2),
            IndexRecordOption::Basic,
        ));
        let query = operator.query(&query_schema, deleted_only)?;
        assert_eq!(searcher.search(&*query, &Count)?, 0, "{operator:?}");
        let failing_candidates = operator.query(&query_schema, Box::new(AllQuery))?;
        let query = operator.query(&query_schema, failing_candidates)?;
        assert!(
            searcher.search(&*query, &Count).is_err(),
            "candidate errors must survive"
        );
    }
    Ok(())
}

#[derive(Debug)]
struct FailingVerifier;
impl GraphVerifier for FailingVerifier {
    fn matcher(&self) -> tantivy::Result<Box<dyn MoleculeMatcher>> {
        Err(tantivy::TantivyError::InvalidArgument(
            "invalid matcher setup".into(),
        ))
    }
}

#[test]
fn empty_candidates_preserve_graph_matcher_setup_errors() -> tantivy::Result<()> {
    let index = error_domain_index("missing", false)?;
    let query = GraphQuery::new(
        Box::new(EmptyQuery),
        &index.schema(),
        &spec(),
        "prepared_smiles".into(),
        Arc::new(FailingVerifier),
    )?;
    let error = index
        .reader()?
        .searcher()
        .search(&query, &Count)
        .unwrap_err();
    assert!(error.to_string().contains("invalid matcher setup"));
    Ok(())
}
