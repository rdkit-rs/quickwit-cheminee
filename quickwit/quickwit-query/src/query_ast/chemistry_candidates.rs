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

//! Narrow verification only with locally necessary, validated predicates.
use anyhow::Context;

use super::cache_node::CacheState;
use super::{BoolQuery, QueryAst};

struct Guard {
    query: QueryAst,
    bytes: usize,
}

#[derive(Default)]
struct Budget {
    bytes: usize,
    copies: usize,
}

/// Call after validating the original resolved query against every target schema.
/// Original matching/scoring clauses remain intact. The limits bound planning
/// expansion; they are safety limits, not measured workload recommendations.
pub fn narrow_chemistry_candidates(mut query: QueryAst) -> anyhow::Result<QueryAst> {
    let mut budget = Budget::default();
    rewrite(&mut query, &mut Vec::new(), &mut budget)?;
    if budget.copies > 0 {
        // Leaves decode the serialized plan with serde's default recursion limit.
        // Reject expansion at the root rather than dispatching an unreadable plan.
        // Reserve the exact wrappers leaf timestamp and search-after rewrites may add.
        let leaf_shape: QueryAst = super::CacheNode::new(
            BoolQuery {
                must: vec![query.clone()],
                ..Default::default()
            }
            .into(),
        )
        .into();
        let encoded = serde_json::to_vec(&leaf_shape)?;
        serde_json::from_slice::<QueryAst>(&encoded)
            .context("chemistry candidate planning exceeds supported serialization depth")?;
    }
    Ok(query)
}

fn permitted_guard(query: &QueryAst) -> bool {
    matches!(
        query,
        QueryAst::Term(_)
            | QueryAst::TermSet(_)
            | QueryAst::Range(_)
            | QueryAst::FieldPresence(_)
            | QueryAst::MatchNone
    )
}

fn constrain(
    candidates: &mut Box<QueryAst>,
    guards: &mut Vec<Guard>,
    budget: &mut Budget,
) -> anyhow::Result<()> {
    rewrite(candidates, guards, budget)?;
    if guards.is_empty() {
        return Ok(());
    }
    for guard in guards.iter() {
        budget.bytes = budget.bytes.saturating_add(guard.bytes);
        budget.copies = budget.copies.saturating_add(1);
        anyhow::ensure!(
            budget.bytes <= 1_048_576 && budget.copies <= 4096,
            "chemistry candidate planning exceeds bounded expansion limit"
        );
    }
    // A new wrapper preserves implicit should requirements in the old candidates.
    let original = std::mem::replace(candidates, Box::new(QueryAst::MatchAll));
    let mut filter = vec![*original];
    filter.extend(guards.iter().map(|guard| guard.query.clone()));
    **candidates = BoolQuery {
        filter,
        ..Default::default()
    }
    .into();
    Ok(())
}

fn rewrite(
    query: &mut QueryAst,
    guards: &mut Vec<Guard>,
    budget: &mut Budget,
) -> anyhow::Result<()> {
    match query {
        QueryAst::Bool(boolean) => {
            let inherited = guards.len();
            for clause in boolean.must.iter().chain(&boolean.filter) {
                if permitted_guard(clause) && !guards.iter().any(|guard| guard.query == *clause) {
                    guards.push(Guard {
                        bytes: serde_json::to_vec(clause)?.len(),
                        query: clause.clone(),
                    });
                }
            }
            for clause in boolean
                .must
                .iter_mut()
                .chain(&mut boolean.filter)
                .chain(&mut boolean.should)
                .chain(&mut boolean.must_not)
            {
                rewrite(clause, guards, budget)?;
            }
            guards.truncate(inherited);
        }
        QueryAst::Graph(chemistry) => constrain(&mut chemistry.candidates, guards, budget)?,
        QueryAst::Tanimoto(chemistry) => constrain(&mut chemistry.candidates, guards, budget)?,
        QueryAst::FingerprintContains(chemistry) => {
            constrain(&mut chemistry.candidates, guards, budget)?
        }
        QueryAst::Boost { underlying, .. } => rewrite(underlying, guards, budget)?,
        QueryAst::Cache(cache) => {
            rewrite(&mut cache.inner, guards, budget)?;
            cache.state = CacheState::Uninitialized;
        }
        _ => {}
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use tantivy_rdkit::{FingerprintFormat, FingerprintSpec};

    use super::super::{TanimotoQueryAst, TermQuery};
    use super::*;

    fn term(value: &str) -> QueryAst {
        TermQuery::from_field_value("supplier", value).into()
    }
    fn chemistry(candidates: QueryAst) -> QueryAst {
        QueryAst::Tanimoto(TanimotoQueryAst {
            candidates: Box::new(candidates),
            spec: FingerprintSpec {
                format: FingerprintFormat::MorganR3Bits2048Lsb0V1,
                rdkit_version: "2026.09.1".into(),
                preparation_id: "sanitize-only-v1".into(),
            },
            fingerprint_hex: format!("01{}", "00".repeat(255)),
            minimum: 0.5f32.try_into().unwrap(),
        })
    }
    fn candidates(query: &QueryAst) -> &QueryAst {
        let QueryAst::Tanimoto(node) = query else {
            panic!("expected chemistry")
        };
        &node.candidates
    }
    #[test]
    fn optional_and_negative_terms_are_not_global_guards() {
        for boolean in [
            BoolQuery {
                should: vec![term("a"), chemistry(QueryAst::MatchAll)],
                ..Default::default()
            },
            BoolQuery {
                must: vec![chemistry(QueryAst::MatchAll)],
                must_not: vec![term("a")],
                ..Default::default()
            },
        ] {
            let original: QueryAst = boolean.into();
            assert_eq!(
                narrow_chemistry_candidates(original.clone()).unwrap(),
                original
            );
        }
    }
    #[test]
    fn original_should_candidates_and_scoring_clauses_are_preserved() {
        let old: QueryAst = BoolQuery {
            should: vec![term("a"), term("b")],
            ..Default::default()
        }
        .into();
        let query = BoolQuery {
            must: vec![term("a"), chemistry(old.clone())],
            ..Default::default()
        };
        let QueryAst::Bool(rewritten) = narrow_chemistry_candidates(query.clone().into()).unwrap()
        else {
            panic!()
        };
        assert_eq!(rewritten.must[0], query.must[0]);
        let QueryAst::Bool(wrapper) = candidates(&rewritten.must[1]) else {
            panic!()
        };
        assert_eq!(wrapper.filter, vec![old, term("a")]);
        assert!(wrapper.should.is_empty());
    }
    #[test]
    fn nested_guards_do_not_escape_their_boolean_scope() {
        let nested: QueryAst = BoolQuery {
            filter: vec![term("a")],
            must_not: vec![chemistry(QueryAst::MatchAll)],
            ..Default::default()
        }
        .into();
        let query = BoolQuery {
            should: vec![nested, chemistry(QueryAst::MatchAll)],
            ..Default::default()
        };
        let QueryAst::Bool(rewritten) = narrow_chemistry_candidates(query.into()).unwrap() else {
            panic!()
        };
        assert_eq!(candidates(&rewritten.should[1]), &QueryAst::MatchAll);
        let QueryAst::Bool(nested) = &rewritten.should[0] else {
            panic!()
        };
        let QueryAst::Bool(wrapper) = candidates(&nested.must_not[0]) else {
            panic!()
        };
        assert_eq!(wrapper.filter, vec![QueryAst::MatchAll, term("a")]);
    }
    #[test]
    fn excessive_candidate_expansion_is_rejected() {
        let query = BoolQuery {
            filter: vec![term(&"x".repeat(1_048_576))],
            must: vec![chemistry(QueryAst::MatchAll)],
            ..Default::default()
        };
        assert!(
            narrow_chemistry_candidates(query.into())
                .unwrap_err()
                .to_string()
                .contains("bounded expansion")
        );
    }
    #[test]
    fn nested_chemistry_expansion_is_rejected_before_leaf_dispatch() {
        let mut inner = QueryAst::MatchAll;
        let mut observed_boundary = false;
        for _ in 0..100 {
            inner = chemistry(inner);
            let original: QueryAst = BoolQuery {
                filter: vec![term("a")],
                must: vec![inner.clone()],
                ..Default::default()
            }
            .into();
            let encoded = serde_json::to_vec(&original).unwrap();
            if serde_json::from_slice::<QueryAst>(&encoded).is_err() {
                break;
            }
            if let Err(error) = narrow_chemistry_candidates(original) {
                assert!(error.to_string().contains("serialization depth"));
                observed_boundary = true;
                break;
            }
        }
        assert!(
            observed_boundary,
            "exercise a valid input whose expanded plan exceeds leaf depth"
        );
    }
}
