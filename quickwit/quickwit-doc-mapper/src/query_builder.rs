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

use std::collections::{HashMap, HashSet};
use std::convert::Infallible;
use std::ops::Bound;
use std::sync::Arc;

use quickwit_query::query_ast::{
    BuildTantivyAstContext, FieldPresenceQuery, FullTextQuery, PhrasePrefixQuery, QueryAst,
    QueryAstTransformer, QueryAstVisitor, RangeQuery, RegexQuery, TermSetQuery, WildcardQuery,
};
use quickwit_query::tokenizers::TokenizerManager;
use quickwit_query::{InvalidQuery, find_field_or_hit_dynamic};
use tantivy::Term;
use tantivy::query::Query;
use tantivy::schema::{Field, Schema};
use tracing::error;

use crate::doc_mapper::FastFieldWarmupInfo;
use crate::{Automaton, QueryParserError, TermRange, WarmupInfo};

#[derive(Default)]
struct QueryFastFields {
    range_query_field_names: HashSet<String>,
    fingerprint_field_names: HashSet<String>,
    graph_fields: Vec<(tantivy_rdkit::FingerprintSpec, String)>,
}

impl<'a> QueryAstVisitor<'a> for QueryFastFields {
    type Err = Infallible;

    fn visit_fingerprint_contains(
        &mut self,
        query: &'a quickwit_query::query_ast::FingerprintContainsQueryAst,
    ) -> Result<(), Infallible> {
        self.fingerprint_field_names.insert(query.spec.field_name());
        self.visit(&query.candidates)
    }

    fn visit_graph(
        &mut self,
        query: &'a quickwit_query::query_ast::GraphQueryAst,
    ) -> Result<(), Infallible> {
        self.graph_fields
            .push((query.spec.clone(), query.prepared_field.clone()));
        self.visit(&query.candidates)
    }

    fn visit_tanimoto(
        &mut self,
        query: &'a quickwit_query::query_ast::TanimotoQueryAst,
    ) -> Result<(), Infallible> {
        self.fingerprint_field_names.insert(query.spec.field_name());
        self.visit(&query.candidates)
    }

    fn visit_range(&mut self, range_query: &'a RangeQuery) -> Result<(), Infallible> {
        self.range_query_field_names
            .insert(range_query.field.to_string());
        Ok(())
    }
}

/// Term Queries on fields which are fast but not indexed.
struct TermSearchOnColumnar<'f> {
    fields: &'f mut HashSet<FastFieldWarmupInfo>,
    schema: Schema,
}
impl<'a, 'f> QueryAstVisitor<'a> for TermSearchOnColumnar<'f> {
    type Err = Infallible;

    fn visit_term_set(&mut self, term_set_query: &'a TermSetQuery) -> Result<(), Infallible> {
        for field in term_set_query.terms_per_field.keys() {
            if let Some((_field, field_entry, path)) =
                find_field_or_hit_dynamic(field, &self.schema)
                && field_entry.is_fast()
                && !field_entry.is_indexed()
            {
                self.fields.insert(FastFieldWarmupInfo {
                    name: if path.is_empty() {
                        field_entry.name().to_string()
                    } else {
                        format!("{}.{}", field_entry.name(), path)
                    },
                    with_subfields: false,
                });
            }
        }
        Ok(())
    }

    fn visit_term(
        &mut self,
        term_query: &'a quickwit_query::query_ast::TermQuery,
    ) -> Result<(), Infallible> {
        if let Some((_field, field_entry, path)) =
            find_field_or_hit_dynamic(&term_query.field, &self.schema)
            && field_entry.is_fast()
            && !field_entry.is_indexed()
        {
            self.fields.insert(FastFieldWarmupInfo {
                name: if path.is_empty() {
                    field_entry.name().to_string()
                } else {
                    format!("{}.{}", field_entry.name(), path)
                },
                with_subfields: false,
            });
        }
        Ok(())
    }
    /// We also need to visit full text queries because they can be converted to term queries
    /// on fast fields. We only care about the field being fast and not indexed AND the tokenizer
    /// being `raw` or None.
    fn visit_full_text(&mut self, full_text_query: &'a FullTextQuery) -> Result<(), Infallible> {
        if let Some((_field, field_entry, path)) =
            find_field_or_hit_dynamic(&full_text_query.field, &self.schema)
            && field_entry.is_fast()
            && !field_entry.is_indexed()
            && (full_text_query.params.tokenizer.is_none()
                || full_text_query.params.tokenizer.as_deref() == Some("raw"))
        {
            self.fields.insert(FastFieldWarmupInfo {
                name: if path.is_empty() {
                    field_entry.name().to_string()
                } else {
                    format!("{}.{}", field_entry.name(), path)
                },
                with_subfields: false,
            });
        }
        Ok(())
    }
}

struct ExistsQueryFastFields<'f> {
    fields: &'f mut HashSet<FastFieldWarmupInfo>,
    schema: Schema,
}

impl<'a, 'f> QueryAstVisitor<'a> for ExistsQueryFastFields<'f> {
    type Err = Infallible;

    fn visit_exists(&mut self, exists_query: &'a FieldPresenceQuery) -> Result<(), Infallible> {
        let fields = exists_query.find_field_and_subfields(&self.schema);
        for (_, field_entry, path) in fields {
            if field_entry.is_fast() {
                if field_entry.field_type().is_json() {
                    let full_path = format!("{}.{}", field_entry.name(), path);
                    self.fields.insert(FastFieldWarmupInfo {
                        name: full_path,
                        with_subfields: true,
                    });
                } else if path.is_empty() {
                    self.fields.insert(FastFieldWarmupInfo {
                        name: field_entry.name().to_string(),
                        with_subfields: false,
                    });
                } else {
                    error!(
                        field_entry = field_entry.name(),
                        path, "only JSON type supports subfields"
                    );
                }
            }
        }
        Ok(())
    }
}

/// Build a `Query` with field resolution & forbidding range clauses.
pub(crate) fn build_query(
    query_ast: QueryAst,
    context: &BuildTantivyAstContext,
    cache_context: Option<(Arc<dyn quickwit_query::query_ast::PredicateCache>, String)>,
) -> Result<(Box<dyn Query>, WarmupInfo), QueryParserError> {
    let mut fast_fields: HashSet<FastFieldWarmupInfo> = HashSet::new();

    let query_ast = if let Some((cache, split_id)) = cache_context {
        let Ok(query_ast) = quickwit_query::query_ast::PredicateCacheInjector { cache, split_id }
            .transform(query_ast);
        // this transformer isn't supposed to ever remove a node
        query_ast.unwrap_or(QueryAst::MatchAll)
    } else {
        query_ast
    };

    let mut range_query_fields = QueryFastFields::default();
    // This cannot fail. The error type is Infallible.
    let Ok(_) = range_query_fields.visit(&query_ast);
    // Old physical splits may lack the current chemistry contract. Defer that
    // error to a live candidate, while preserving all ordinary query warmups.
    for name in &range_query_fields.fingerprint_field_names {
        if tantivy_rdkit::validate_fingerprint_field(context.schema, name).is_ok() {
            fast_fields.insert(FastFieldWarmupInfo {
                name: name.clone(),
                with_subfields: false,
            });
        }
    }
    for (spec, name) in &range_query_fields.graph_fields {
        if tantivy_rdkit::GraphQuery::validate_schema(context.schema, spec, name).is_ok() {
            fast_fields.insert(FastFieldWarmupInfo {
                name: name.clone(),
                with_subfields: false,
            });
        }
    }
    let range_query_fast_fields = range_query_fields
        .range_query_field_names
        .into_iter()
        .filter(|name| {
            context.with_validation
                || matches!(find_field_or_hit_dynamic(name, context.schema),
                    Some((_, entry, _)) if entry.is_fast())
        })
        .map(|name| FastFieldWarmupInfo {
            name,
            with_subfields: false,
        });
    fast_fields.extend(range_query_fast_fields);

    let Ok(_) = TermSearchOnColumnar {
        fields: &mut fast_fields,
        schema: context.schema.clone(),
    }
    .visit(&query_ast);

    let Ok(_) = ExistsQueryFastFields {
        fields: &mut fast_fields,
        schema: context.schema.clone(),
    }
    .visit(&query_ast);

    let (query, required_terms) = query_ast.build_tantivy_query_and_required_terms(context)?;

    let term_set_query_fields =
        extract_term_set_query_fields(&query_ast, context.schema, context.with_validation)?;
    let (term_ranges_grouped_by_field, automatons_grouped_by_field) =
        extract_prefix_term_ranges_and_automaton(
            &query_ast,
            context.schema,
            context.tokenizer_manager,
        )?;

    let mut terms_grouped_by_field: HashMap<Field, HashMap<_, bool>> = Default::default();
    query.query_terms(&mut |term, need_position| {
        let field = term.field();
        if !context.schema.get_field_entry(field).is_indexed() {
            return;
        }
        *terms_grouped_by_field
            .entry(field)
            .or_default()
            .entry(term.clone())
            .or_default() |= need_position;
    });

    let warmup_info = WarmupInfo {
        term_dict_fields: term_set_query_fields,
        terms_grouped_by_field,
        term_ranges_grouped_by_field,
        fast_fields,
        automatons_grouped_by_field,
        required_terms,
        ..WarmupInfo::default()
    };

    Ok((query, warmup_info))
}

struct ExtractTermSetFields<'a> {
    term_dict_fields_to_warm_up: HashSet<Field>,
    schema: &'a Schema,
    with_validation: bool,
}

impl<'a> ExtractTermSetFields<'a> {
    fn new(schema: &'a Schema, with_validation: bool) -> Self {
        ExtractTermSetFields {
            term_dict_fields_to_warm_up: HashSet::new(),
            schema,
            with_validation,
        }
    }
}

impl<'a> QueryAstVisitor<'a> for ExtractTermSetFields<'_> {
    type Err = anyhow::Error;

    fn visit_term_set(&mut self, term_set_query: &'a TermSetQuery) -> anyhow::Result<()> {
        for field in term_set_query.terms_per_field.keys() {
            if let Some((field, entry, _path)) = find_field_or_hit_dynamic(field, self.schema) {
                if entry.is_indexed() {
                    self.term_dict_fields_to_warm_up.insert(field);
                }
            } else if self.with_validation {
                anyhow::bail!("field does not exist: {}", field);
            }
        }
        Ok(())
    }
}

fn extract_term_set_query_fields(
    query_ast: &QueryAst,
    schema: &Schema,
    with_validation: bool,
) -> anyhow::Result<HashSet<Field>> {
    let mut visitor = ExtractTermSetFields::new(schema, with_validation);
    visitor.visit(query_ast)?;
    Ok(visitor.term_dict_fields_to_warm_up)
}

/// Converts a `prefix` term into the equivalent term range.
///
/// The resulting range is `[prefix, next_prefix)`, that is:
/// - start bound: `Included(prefix)`
/// - end bound: `Excluded(next lexicographic term after the prefix)`
///
/// "abc"    -> start: "abc", end: "abd" (excluded)
/// "ab\xFF" -> start: "ab\xFF", end: "ac" (excluded)
/// "\xFF\xFF" -> start: "\xFF\xFF", end: Unbounded
fn prefix_term_to_range(prefix: Term) -> (Bound<Term>, Bound<Term>) {
    // Start from the given prefix and try to find the successor
    let mut end_bound = prefix.clone();
    let mut end_bound_value_bytes = prefix.serialized_value_bytes().to_vec();
    while !end_bound_value_bytes.is_empty() {
        let last_byte = end_bound_value_bytes.last_mut().unwrap();
        if *last_byte != u8::MAX {
            *last_byte += 1;
            // The last non-`u8::MAX` byte incremented
            // gives us the exclusive upper bound.
            end_bound.set_bytes(&end_bound_value_bytes);
            return (Bound::Included(prefix), Bound::Excluded(end_bound));
        }
        // pop u8::MAX byte and try next
        end_bound_value_bytes.pop();
    }
    // All bytes were `u8::MAX`: there is no successor, so the upper bound is unbounded.
    (Bound::Included(prefix), Bound::Unbounded)
}

type PositionNeeded = bool;

struct ExtractPrefixTermRanges<'a> {
    schema: &'a Schema,
    tokenizer_manager: &'a TokenizerManager,
    term_ranges_to_warm_up: HashMap<Field, HashMap<TermRange, PositionNeeded>>,
    automatons_to_warm_up: HashMap<Field, HashSet<Automaton>>,
}

impl<'a> ExtractPrefixTermRanges<'a> {
    fn with_schema(schema: &'a Schema, tokenizer_manager: &'a TokenizerManager) -> Self {
        ExtractPrefixTermRanges {
            schema,
            tokenizer_manager,
            term_ranges_to_warm_up: HashMap::new(),
            automatons_to_warm_up: HashMap::new(),
        }
    }

    fn add_prefix_term(
        &mut self,
        term: Term,
        max_expansions: u32,
        position_needed: PositionNeeded,
    ) {
        let field = term.field();
        let (start, end) = prefix_term_to_range(term);
        let term_range = TermRange {
            start,
            end,
            limit: Some(max_expansions as u64),
        };
        *self
            .term_ranges_to_warm_up
            .entry(field)
            .or_default()
            .entry(term_range)
            .or_default() |= position_needed;
    }

    fn add_automaton(&mut self, field: Field, automaton: Automaton) {
        self.automatons_to_warm_up
            .entry(field)
            .or_default()
            .insert(automaton);
    }
}

impl<'a, 'b: 'a> QueryAstVisitor<'a> for ExtractPrefixTermRanges<'b> {
    type Err = InvalidQuery;

    fn visit_full_text(&mut self, full_text_query: &'a FullTextQuery) -> Result<(), Self::Err> {
        if let Some(prefix_term) =
            full_text_query.get_prefix_term(self.schema, self.tokenizer_manager)
        {
            // the max_expansion expansion of a bool prefix query is used for the fuzzy part of the
            // query, not for the expension to a range request.
            // see https://github.com/elastic/elasticsearch/blob/6ad48306d029e6e527c0481e2e9880bd2f06b239/docs/reference/query-dsl/match-bool-prefix-query.asciidoc#parameters
            self.add_prefix_term(prefix_term, u32::MAX, false);
        }
        Ok(())
    }

    fn visit_phrase_prefix(
        &mut self,
        phrase_prefix: &'a PhrasePrefixQuery,
    ) -> Result<(), Self::Err> {
        let phrase_prefix_terms = match phrase_prefix.get_terms(self.schema, self.tokenizer_manager)
        {
            Ok(terms) => terms,
            Err(InvalidQuery::SchemaError(_)) | Err(InvalidQuery::FieldDoesNotExist { .. }) => {
                return Ok(());
            } /* the query will be nullified when casting to a tantivy ast */
            Err(e) => return Err(e),
        };
        if let Some((_, term)) = phrase_prefix_terms.term_positions.last() {
            self.add_prefix_term(
                term.clone(),
                phrase_prefix_terms.max_expansions,
                phrase_prefix_terms.term_positions.len() > 1,
            );
        }
        Ok(())
    }

    fn visit_wildcard(&mut self, wildcard_query: &'a WildcardQuery) -> Result<(), Self::Err> {
        let (field, path, regex) =
            match wildcard_query.to_regex(self.schema, self.tokenizer_manager) {
                Ok(res) => res,
                /* the query will be nullified when casting to a tantivy ast */
                Err(InvalidQuery::FieldDoesNotExist { .. }) => return Ok(()),
                Err(e) => return Err(e),
            };

        self.add_automaton(field, Automaton::Regex(path, regex));
        Ok(())
    }

    fn visit_regex(&mut self, regex_query: &'a RegexQuery) -> Result<(), Self::Err> {
        let resolved = match regex_query.to_resolved(self.schema, Some(self.tokenizer_manager)) {
            Ok(res) => res,
            /* the query will be nullified when casting to a tantivy ast */
            Err(InvalidQuery::FieldDoesNotExist { .. }) => return Ok(()),
            Err(e) => return Err(e),
        };
        self.add_automaton(
            resolved.field,
            Automaton::Regex(resolved.json_path, resolved.regex),
        );
        Ok(())
    }
}

type TermRangeWarmupInfo = HashMap<Field, HashMap<TermRange, PositionNeeded>>;
type AutomatonWarmupInfo = HashMap<Field, HashSet<Automaton>>;

fn extract_prefix_term_ranges_and_automaton(
    query_ast: &QueryAst,
    schema: &Schema,
    tokenizer_manager: &TokenizerManager,
) -> anyhow::Result<(TermRangeWarmupInfo, AutomatonWarmupInfo)> {
    let mut visitor = ExtractPrefixTermRanges::with_schema(schema, tokenizer_manager);
    visitor.visit(query_ast)?;
    Ok((
        visitor.term_ranges_to_warm_up,
        visitor.automatons_to_warm_up,
    ))
}

#[cfg(test)]
mod test {
    use std::ops::Bound;

    use quickwit_common::shared_consts::FIELD_PRESENCE_FIELD_NAME;
    use quickwit_query::query_ast::{
        BuildTantivyAstContext, FullTextMode, FullTextParams, PhrasePrefixQuery, QueryAstVisitor,
        UserInputQuery, query_ast_from_user_text,
    };
    use quickwit_query::{
        BooleanOperand, MatchAllOrNone, create_default_quickwit_tokenizer_manager,
    };
    use tantivy::Term;
    use tantivy::schema::{DateOptions, DateTimePrecision, FAST, INDEXED, STORED, Schema, TEXT};

    use super::{ExtractPrefixTermRanges, build_query};
    use crate::{DYNAMIC_FIELD_NAME, SOURCE_FIELD_NAME, TermRange};

    enum TestExpectation<'a> {
        Err(&'a str),
        Ok(&'a str),
    }

    fn make_schema(dynamic_mode: bool) -> Schema {
        let mut schema_builder = Schema::builder();
        schema_builder.add_i64_field(FIELD_PRESENCE_FIELD_NAME, INDEXED);
        schema_builder.add_text_field("title", TEXT);
        schema_builder.add_text_field("desc", TEXT | STORED);
        schema_builder.add_text_field("server.name", TEXT | STORED);
        schema_builder.add_text_field("server.mem", TEXT);
        schema_builder.add_bool_field("server.running", FAST | STORED | INDEXED);
        schema_builder.add_text_field(SOURCE_FIELD_NAME, TEXT);
        schema_builder.add_ip_addr_field("ip", FAST | STORED);
        schema_builder.add_ip_addr_field("ips", FAST);
        schema_builder.add_ip_addr_field("ip_notff", STORED);
        let date_options = DateOptions::default()
            .set_fast()
            .set_precision(DateTimePrecision::Milliseconds);
        schema_builder.add_date_field("dt", date_options);
        schema_builder.add_u64_field("u64_fast", FAST | STORED);
        schema_builder.add_i64_field("i64_fast", FAST | STORED);
        schema_builder.add_f64_field("f64_fast", FAST | STORED);
        schema_builder.add_json_field("json_fast", FAST);
        schema_builder.add_json_field("json_text", TEXT);
        if dynamic_mode {
            schema_builder.add_json_field(DYNAMIC_FIELD_NAME, TEXT);
        }
        schema_builder.build()
    }

    #[track_caller]
    fn check_build_query_dynamic_mode(
        user_query: &str,
        search_fields: Vec<String>,
        expected: TestExpectation,
    ) {
        check_build_query(user_query, search_fields, expected, true, false);
    }

    #[track_caller]
    fn check_build_query_static_mode(
        user_query: &str,
        search_fields: Vec<String>,
        expected: TestExpectation,
    ) {
        check_build_query(user_query, search_fields, expected, false, false);
    }

    #[track_caller]
    fn check_build_query_static_lenient_mode(
        user_query: &str,
        search_fields: Vec<String>,
        expected: TestExpectation,
    ) {
        check_build_query(user_query, search_fields, expected, false, true);
    }

    fn test_build_query(
        user_query: &str,
        search_fields: Vec<String>,
        dynamic_mode: bool,
        lenient: bool,
    ) -> Result<String, String> {
        let user_input_query = UserInputQuery {
            user_text: user_query.to_string(),
            default_fields: Some(search_fields),
            default_operator: BooleanOperand::And,
            lenient,
        };
        let query_ast = user_input_query
            .parse_user_query(&[])
            .map_err(|err| err.to_string())?;
        let schema = make_schema(dynamic_mode);
        let query_result = build_query(query_ast, &BuildTantivyAstContext::for_test(&schema), None);
        query_result
            .map(|query| format!("{query:?}"))
            .map_err(|err| err.to_string())
    }

    #[track_caller]
    fn check_build_query(
        user_query: &str,
        search_fields: Vec<String>,
        expected: TestExpectation,
        dynamic_mode: bool,
        lenient: bool,
    ) {
        let query_result = test_build_query(user_query, search_fields, dynamic_mode, lenient);
        match (query_result, expected) {
            (Err(query_err_msg), TestExpectation::Err(sub_str)) => {
                assert!(
                    query_err_msg.contains(sub_str),
                    "query error received is {query_err_msg}. it should contain {sub_str}"
                );
            }
            (Ok(query_str), TestExpectation::Ok(sub_str)) => {
                assert!(
                    query_str.contains(sub_str),
                    "error query parsing {query_str} should contain {sub_str}"
                );
            }
            (Err(error_msg), TestExpectation::Ok(expectation)) => {
                panic!("Expected `{expectation}` but got an error `{error_msg}`.");
            }
            (Ok(query_str), TestExpectation::Err(expected_error)) => {
                panic!("Expected the error `{expected_error}`, but got a success `{query_str}`");
            }
        }
    }

    #[test]
    fn test_build_query_dynamic_field() {
        check_build_query_dynamic_mode("*", Vec::new(), TestExpectation::Ok("All"));
        check_build_query_dynamic_mode(
            "foo:bar",
            Vec::new(),
            TestExpectation::Ok(
                r#"TermQuery(Term(field=16, type=Json, path=foo, type=Str, "bar"))"#,
            ),
        );
        check_build_query_dynamic_mode(
            "server.type:hpc server.mem:4GB",
            Vec::new(),
            TestExpectation::Ok("server.type"),
        );
        check_build_query_dynamic_mode(
            "title:[a TO b]",
            Vec::new(),
            TestExpectation::Err(
                "range queries are only supported for fast fields. (`title` is not a fast field)",
            ),
        );
        check_build_query_dynamic_mode(
            "title:{a TO b} desc:foo",
            Vec::new(),
            TestExpectation::Err(
                "range queries are only supported for fast fields. (`title` is not a fast field)",
            ),
        );
    }

    #[test]
    fn test_build_query_not_dynamic_mode() {
        check_build_query_static_mode("*", Vec::new(), TestExpectation::Ok("All"));
        check_build_query_static_mode(
            "foo:bar",
            Vec::new(),
            TestExpectation::Err("invalid query: field does not exist: `foo`"),
        );
        check_build_query_static_lenient_mode(
            "foo:bar",
            Vec::new(),
            TestExpectation::Ok("EmptyQuery"),
        );
        check_build_query_static_mode(
            "title:bar",
            Vec::new(),
            TestExpectation::Ok(r#"TermQuery(Term(field=1, type=Str, "bar"))"#),
        );
        check_build_query_static_mode(
            "bar",
            vec!["fieldnotinschema".to_string()],
            TestExpectation::Err("invalid query: field does not exist: `fieldnotinschema`"),
        );
        check_build_query_static_lenient_mode(
            "bar",
            vec!["fieldnotinschema".to_string()],
            TestExpectation::Ok("EmptyQuery"),
        );
        check_build_query_static_mode(
            "title:[a TO b]",
            Vec::new(),
            TestExpectation::Err(
                "range queries are only supported for fast fields. (`title` is not a fast field)",
            ),
        );
        check_build_query_static_mode(
            "title:{a TO b} desc:foo",
            Vec::new(),
            TestExpectation::Err(
                "range queries are only supported for fast fields. (`title` is not a fast field)",
            ),
        );
        check_build_query_static_mode(
            "title:>foo",
            Vec::new(),
            TestExpectation::Err(
                "range queries are only supported for fast fields. (`title` is not a fast field)",
            ),
        );
        check_build_query_static_mode(
            "title:foo desc:bar _source:baz",
            Vec::new(),
            TestExpectation::Ok("TermQuery"),
        );
        check_build_query_static_mode(
            "server.name:\".bar:\" server.mem:4GB",
            vec!["server.name".to_string()],
            TestExpectation::Ok("TermQuery"),
        );
        check_build_query_static_mode(
            "server.name:\"for.bar:b\" server.mem:4GB",
            Vec::new(),
            TestExpectation::Ok("TermQuery"),
        );
        check_build_query_static_mode(
            "foo",
            Vec::new(),
            TestExpectation::Err("query requires a default search field and none was supplied"),
        );
        check_build_query_static_mode(
            "bar",
            Vec::new(),
            TestExpectation::Err("query requires a default search field and none was supplied"),
        );
        check_build_query_static_mode(
            "title:hello AND (Jane OR desc:world)",
            Vec::new(),
            TestExpectation::Err("query requires a default search field and none was supplied"),
        );
        check_build_query_static_mode(
            "server.running:true",
            Vec::new(),
            TestExpectation::Ok("TermQuery"),
        );
        check_build_query_static_mode(
            "title: IN [hello]",
            Vec::new(),
            TestExpectation::Ok("TermSetQuery"),
        );
        check_build_query_static_mode(
            "IN [hello]",
            Vec::new(),
            TestExpectation::Err("set query need to target a specific field"),
        );
    }

    #[test]
    fn test_wildcard_query() {
        check_build_query_static_mode("title:hello*", Vec::new(), TestExpectation::Ok("Regex"));
        check_build_query_static_mode(
            "title:\"hello world\"*",
            Vec::new(),
            TestExpectation::Ok("PhrasePrefixQuery"),
        );
        // the tokenizer removes '*' chars, making it a simple PhraseQuery (not RegexPhraseQuery)
        check_build_query_static_mode(
            "title:\"hello* world*\"",
            Vec::new(),
            TestExpectation::Ok("PhraseQuery"),
        );
        check_build_query_static_mode(
            "foo:bar*",
            Vec::new(),
            TestExpectation::Err("invalid query: field does not exist: `foo`"),
        );
        check_build_query_static_mode("title:hello*yo", Vec::new(), TestExpectation::Ok("Regex"));
    }

    #[test]
    fn test_existence_query() {
        check_build_query_static_mode(
            "title:*",
            Vec::new(),
            TestExpectation::Ok("TermQuery(Term(field=0, type=U64"),
        );

        check_build_query_static_mode(
            "ip:*",
            Vec::new(),
            TestExpectation::Ok("ExistsQuery { field_name: \"ip\", json_subpaths: true }"),
        );
        check_build_query_static_mode(
            "json_text:*",
            Vec::new(),
            TestExpectation::Ok("TermSetQuery"),
        );
        check_build_query_static_mode(
            "json_fast:*",
            Vec::new(),
            TestExpectation::Ok("ExistsQuery { field_name: \"json_fast\", json_subpaths: true }"),
        );
        check_build_query_static_mode(
            "foo:*",
            Vec::new(),
            TestExpectation::Err("invalid query: field does not exist: `foo`"),
        );
        check_build_query_static_mode(
            "server:*",
            Vec::new(),
            TestExpectation::Ok("BooleanQuery { subqueries: [(Should, TermQuery(Term"),
        );
    }

    #[test]
    fn test_datetime_range_query() {
        {
            // Check range on datetime in millisecond, precision has no impact as it is in
            // milliseconds.
            let start_date_time_str = "2023-01-10T08:38:51.150Z";
            let end_date_time_str = "2023-01-10T08:38:51.160Z";
            check_build_query_static_mode(
                &format!("dt:[{start_date_time_str} TO {end_date_time_str}]"),
                Vec::new(),
                TestExpectation::Ok("2023-01-10T08:38:51.15Z"),
            );
            check_build_query_static_mode(
                &format!("dt:[{start_date_time_str} TO {end_date_time_str}]"),
                Vec::new(),
                TestExpectation::Ok("RangeQuery"),
            );
            check_build_query_static_mode(
                &format!("dt:<{end_date_time_str}"),
                Vec::new(),
                TestExpectation::Ok("lower_bound: Unbounded"),
            );
            check_build_query_static_mode(
                &format!("dt:<{end_date_time_str}"),
                Vec::new(),
                TestExpectation::Ok("upper_bound: Excluded"),
            );
            check_build_query_static_mode(
                &format!("dt:<{end_date_time_str}"),
                Vec::new(),
                TestExpectation::Ok("2023-01-10T08:38:51.16Z"),
            );
        }

        // Check range on datetime in microseconds and truncation to milliseconds.
        {
            let start_date_time_str = "2023-01-10T08:38:51.000150Z";
            let end_date_time_str = "2023-01-10T08:38:51.000151Z";
            check_build_query_static_mode(
                &format!("dt:[{start_date_time_str} TO {end_date_time_str}]"),
                Vec::new(),
                TestExpectation::Ok("2023-01-10T08:38:51Z"),
            );
        }
    }

    #[test]
    fn test_ip_range_query() {
        check_build_query_static_mode(
            "ip:[127.0.0.1 TO 127.1.1.1]",
            Vec::new(),
            TestExpectation::Ok(
                "RangeQuery { bounds: BoundsRange { lower_bound: Included(Term(field=7, \
                 type=IpAddr, ::ffff:127.0.0.1)), upper_bound: Included(Term(field=7, \
                 type=IpAddr, ::ffff:127.1.1.1)) } }",
            ),
        );
        check_build_query_static_mode(
            "ip:>127.0.0.1",
            Vec::new(),
            TestExpectation::Ok(
                "RangeQuery { bounds: BoundsRange { lower_bound: Excluded(Term(field=7, \
                 type=IpAddr, ::ffff:127.0.0.1)), upper_bound: Unbounded } }",
            ),
        );
    }

    #[test]
    fn test_f64_range_query() {
        check_build_query_static_mode(
            "f64_fast:[7.7 TO 77.7]",
            Vec::new(),
            TestExpectation::Ok(
                r#"RangeQuery { bounds: BoundsRange { lower_bound: Included(Term(field=13, type=F64, 7.7)), upper_bound: Included(Term(field=13, type=F64, 77.7)) } }"#,
            ),
        );
        check_build_query_static_mode(
            "f64_fast:>7",
            Vec::new(),
            TestExpectation::Ok(
                r#"RangeQuery { bounds: BoundsRange { lower_bound: Excluded(Term(field=13, type=F64, 7.0)), upper_bound: Unbounded } }"#,
            ),
        );
    }

    #[test]
    fn test_i64_range_query() {
        check_build_query_static_mode(
            "i64_fast:[-7 TO 77]",
            Vec::new(),
            TestExpectation::Ok(r#"field=12"#),
        );
        check_build_query_static_mode(
            "i64_fast:>7",
            Vec::new(),
            TestExpectation::Ok(r#"field=12"#),
        );
    }

    #[test]
    fn test_u64_range_query() {
        check_build_query_static_mode(
            "u64_fast:[7 TO 77]",
            Vec::new(),
            TestExpectation::Ok(r#"field=11,"#),
        );
        check_build_query_static_mode(
            "u64_fast:>7",
            Vec::new(),
            TestExpectation::Ok(r#"field=11,"#),
        );
    }

    #[test]
    fn test_range_query_ip_fields_multivalued() {
        check_build_query_static_mode(
            "ips:[127.0.0.1 TO 127.1.1.1]",
            Vec::new(),
            TestExpectation::Ok(
                "RangeQuery { bounds: BoundsRange { lower_bound: Included(Term(field=8, \
                 type=IpAddr, ::ffff:127.0.0.1)), upper_bound: Included(Term(field=8, \
                 type=IpAddr, ::ffff:127.1.1.1)) } }",
            ),
        );
    }

    #[test]
    fn test_range_query_no_fast_field() {
        check_build_query_static_mode(
            "ip_notff:[127.0.0.1 TO 127.1.1.1]",
            Vec::new(),
            TestExpectation::Err("`ip_notff` is not a fast field"),
        );
    }

    #[test]
    fn test_build_query_not_bool_should_fail() {
        check_build_query_static_mode(
            "server.running:notabool",
            Vec::new(),
            TestExpectation::Err("expected a `bool` search value for field `server.running`"),
        );
    }

    #[test]
    fn test_build_query_warmup_info() {
        let query_with_set = query_ast_from_user_text("desc: IN [hello]", None)
            .parse_user_query(&[])
            .unwrap();
        let query_without_set = query_ast_from_user_text("desc:hello", None)
            .parse_user_query(&[])
            .unwrap();

        let schema = make_schema(true);
        let context = BuildTantivyAstContext::for_test(&schema);

        let (_, warmup_info) = build_query(query_with_set, &context, None).unwrap();
        assert_eq!(warmup_info.term_dict_fields.len(), 1);
        assert!(
            warmup_info
                .term_dict_fields
                .contains(&tantivy::schema::Field::from_field_id(2))
        );

        let (_, warmup_info) = build_query(query_without_set, &context, None).unwrap();
        assert!(warmup_info.term_dict_fields.is_empty());
    }

    #[test]
    fn test_extract_phrase_prefix_position_required() {
        let schema = make_schema(false);
        let tokenizer_manager = create_default_quickwit_tokenizer_manager();

        let params = FullTextParams {
            tokenizer: None,
            mode: FullTextMode::Phrase { slop: 0 },
            zero_terms_query: MatchAllOrNone::MatchNone,
        };
        let short = PhrasePrefixQuery {
            field: "title".to_string(),
            phrase: "short".to_string(),
            max_expansions: 50,
            params: params.clone(),
            lenient: false,
        };
        let long = PhrasePrefixQuery {
            field: "title".to_string(),
            phrase: "not so short".to_string(),
            max_expansions: 50,
            params: params.clone(),
            lenient: false,
        };
        let mut extractor1 = ExtractPrefixTermRanges::with_schema(&schema, &tokenizer_manager);
        extractor1.visit_phrase_prefix(&short).unwrap();
        extractor1.visit_phrase_prefix(&long).unwrap();

        let mut extractor2 = ExtractPrefixTermRanges::with_schema(&schema, &tokenizer_manager);
        extractor2.visit_phrase_prefix(&long).unwrap();
        extractor2.visit_phrase_prefix(&short).unwrap();

        assert_eq!(
            extractor1.term_ranges_to_warm_up,
            extractor2.term_ranges_to_warm_up
        );

        let field = tantivy::schema::Field::from_field_id(1);
        let mut expected_inner = std::collections::HashMap::new();
        // The single-token phrase prefix ("short") is executed as an uncapped prefix
        // range query, so its whole term range must be warmed up (limit u32::MAX) and it
        // needs no positions.
        expected_inner.insert(
            TermRange {
                start: Bound::Included(Term::from_field_text(field, "short")),
                end: Bound::Excluded(Term::from_field_text(field, "shoru")),
                limit: Some(u32::MAX as u64),
            },
            false,
        );
        // The multi-token phrase prefix ("not so short") still runs as a capped phrase
        // prefix query on its last token, so it warms up at most `max_expansions` terms
        // and needs positions.
        expected_inner.insert(
            TermRange {
                start: Bound::Included(Term::from_field_text(field, "short")),
                end: Bound::Excluded(Term::from_field_text(field, "shoru")),
                limit: Some(50),
            },
            true,
        );
        let mut expected = std::collections::HashMap::new();
        expected.insert(field, expected_inner);
        assert_eq!(extractor1.term_ranges_to_warm_up, expected);
    }
}

#[cfg(test)]
mod chemistry_tests {
    use tantivy::schema::{FAST, STRING};

    use super::*;

    #[cfg(feature = "native-chemistry")]
    #[test]
    fn old_physical_chemistry_contract_is_checked_only_for_live_candidates() {
        use tantivy::collector::Count;
        use tantivy::schema::{BytesOptions, STORED, TextOptions};
        use tantivy::{Index, TantivyDocument, doc};
        use tantivy_rdkit::FingerprintSpec;

        let spec_json = serde_json::json!({"format":"morgan-r3-2048-lsb0-v1",
            "rdkit_version":"2026.09.1", "preparation_id":"sanitize-only-v1"});
        let spec: FingerprintSpec = serde_json::from_value(spec_json.clone()).unwrap();
        let fp = spec.field_name();
        let mapper = serde_json::from_value::<crate::DocMapperBuilder>(serde_json::json!({
            "mode":"strict", "chemistry":{"spec":spec_json, "smiles_field":"smiles",
                "prepared_smiles_field":"prepared"},
            "field_mappings":[
                {"name":"record_id","type":"u64","fast":true},
                {"name":fp,"type":"bytes","fast":true,"indexed":false,"input_format":"hex","output_format":"hex"},
                {"name":"prepared","type":"text","fast":true,"indexed":false},
                {"name":"smiles","type":"text","tokenizer":"raw"},
                {"name":"family","type":"text","tokenizer":"raw"}]
        }))
        .unwrap()
        .try_build()
        .unwrap();
        for contract in [
            "missing",
            "wrong_fp",
            "nonfast_fp",
            "missing_prepared",
            "nonfast_prepared",
            "nonraw_prepared",
            "wrong_prepared",
            "unstored_prepared",
            "dynamic_only",
            "dynamic_prepared",
            "valid",
        ] {
            let mut builder = Schema::builder();
            let family = builder.add_text_field("family", STRING);
            let dynamic = if matches!(contract, "dynamic_only" | "dynamic_prepared") {
                Some(builder.add_json_field(
                    "_dynamic",
                    tantivy::schema::JsonObjectOptions::default().set_fast(None),
                ))
            } else {
                None
            };
            let fingerprint = match contract {
                "missing" | "dynamic_only" => None,
                "wrong_fp" => {
                    builder.add_u64_field(&fp, FAST);
                    None
                }
                "nonfast_fp" => Some(builder.add_bytes_field(&fp, BytesOptions::default())),
                _ => Some(builder.add_bytes_field(&fp, FAST)),
            };
            let prepared = match contract {
                "missing" | "missing_prepared" | "dynamic_only" | "dynamic_prepared" => None,
                "wrong_prepared" => {
                    builder.add_u64_field("prepared", FAST);
                    None
                }
                "unstored_prepared" => {
                    Some(builder.add_text_field("prepared", TextOptions::default().set_fast(None)))
                }
                "nonfast_prepared" => Some(builder.add_text_field("prepared", STORED)),
                "nonraw_prepared" => Some(
                    builder.add_text_field(
                        "prepared",
                        TextOptions::default()
                            .set_stored()
                            .set_fast(Some("default")),
                    ),
                ),
                _ => Some(builder.add_text_field("prepared", STORED | FAST)),
            };
            let schema = builder.build();
            assert_ne!(family, mapper.schema().get_field("family").unwrap());
            let index = Index::create_in_ram(schema.clone());
            let mut writer = index
                .writer_with_num_threads::<TantivyDocument>(1, 15_000_000)
                .unwrap();
            let mut document = doc!(family => "legacy");
            if let Some(field) = fingerprint {
                document.add_bytes(field, &[1u8; 256]);
            }
            if let Some(field) = prepared {
                document.add_text(field, "CCO");
            }
            if let Some(field) = dynamic {
                document.add_object(
                    field,
                    std::collections::BTreeMap::from([(
                        "prepared".to_string(),
                        tantivy::schema::OwnedValue::Str("CCO".to_string()),
                    )]),
                );
            }
            writer.add_document(document).unwrap();
            writer.commit().unwrap();
            let reader = index.reader().unwrap();
            let searcher = reader.searcher();
            for operator in ["tanimoto", "fingerprint_contains", "graph"] {
                for candidate in ["absent", "legacy"] {
                    let mut value = serde_json::json!({"type":operator,"spec":spec_json,
                        "candidates":{"type":"term","field":"family","value":candidate}});
                    match operator {
                        "tanimoto" => {
                            value["fingerprint_hex"] = "01".repeat(256).into();
                            value["minimum"] = 0.0.into();
                        }
                        "fingerprint_contains" => {
                            value["fingerprint_hex"] = "01".repeat(256).into();
                            value["direction"] = "document_contains_query".into();
                        }
                        _ => {
                            value["prepared_field"] = "prepared".into();
                            value["prepared_smiles"] = "CCO".into();
                            value["predicate"] = "identity".into();
                            value["ranking"] = "stable_id".into();
                            value["use_chirality"] = true.into();
                            value["include_identity"] = true.into();
                        }
                    }
                    let ast: QueryAst = serde_json::from_value(value.clone()).unwrap();
                    let (query, warmup) = mapper.query(schema.clone(), ast, false, None).unwrap();
                    assert!(warmup.terms_grouped_by_field.contains_key(&family));
                    let result = searcher.search(query.as_ref(), &Count);
                    let invalid_physical = if operator == "graph" {
                        contract != "valid"
                    } else {
                        matches!(
                            contract,
                            "missing" | "wrong_fp" | "nonfast_fp" | "dynamic_only"
                        )
                    };
                    let expected_warmup = if invalid_physical {
                        None
                    } else if operator == "graph" {
                        Some("prepared")
                    } else {
                        Some(fp.as_str())
                    };
                    let names: Vec<_> = warmup
                        .fast_fields
                        .iter()
                        .map(|field| field.name.as_str())
                        .collect();
                    assert_eq!(
                        names,
                        expected_warmup.into_iter().collect::<Vec<_>>(),
                        "{contract}/{operator}"
                    );
                    if candidate == "legacy" && invalid_physical {
                        assert!(
                            result.is_err(),
                            "{contract}/{operator} must fail for live candidates"
                        );
                    } else {
                        assert_eq!(
                            result.unwrap(),
                            usize::from(candidate == "legacy"),
                            "{contract}/{operator}/{candidate}"
                        );
                    }
                    // Invalid inputs stay eager, even on a physically old split with no candidates.
                    value["candidates"]["value"] = "absent".into();
                    if operator == "graph" {
                        value["prepared_smiles"] = "not-smiles".into();
                    } else {
                        value["fingerprint_hex"] = "invalid".into();
                    }
                    assert!(
                        mapper
                            .query(
                                schema.clone(),
                                serde_json::from_value(value).unwrap(),
                                false,
                                None
                            )
                            .is_err()
                    );
                }
            }
        }
    }

    #[test]
    fn old_candidate_term_set_and_nonfast_range_keep_empty_domain() {
        use tantivy::collector::Count;
        use tantivy::schema::NumericOptions;
        use tantivy::{Index, TantivyDocument, doc};
        let QueryAst::Tanimoto(chemistry) = ast() else {
            panic!()
        };
        let mut current = Schema::builder();
        current.add_bytes_field(&chemistry.spec.field_name(), FAST);
        current.add_text_field("new_field", STRING);
        current.add_u64_field("range_field", FAST);
        let current = current.build();
        let mut old = Schema::builder();
        let range = old.add_u64_field("range_field", NumericOptions::default().set_indexed());
        let old = old.build();
        let index = Index::create_in_ram(old.clone());
        let mut writer = index
            .writer_with_num_threads::<TantivyDocument>(1, 15_000_000)
            .unwrap();
        writer.add_document(doc!(range => 1u64)).unwrap();
        writer.commit().unwrap();
        let reader = index.reader().unwrap();
        for candidate in [
            serde_json::json!({"type":"term_set","terms_per_field":{"new_field":["value"]}}),
            serde_json::json!({"type":"range","field":"range_field","lower_bound":{"Included":0},"upper_bound":{"Included":2}}),
        ] {
            let mut query = chemistry.clone();
            query.candidates = Box::new(serde_json::from_value(candidate).unwrap());
            let mut context = BuildTantivyAstContext::for_test(&old).without_validation();
            context.chemistry_schema = &current;
            let (query, warmup) = build_query(QueryAst::Tanimoto(query), &context, None).unwrap();
            assert!(warmup.fast_fields.is_empty());
            assert!(warmup.term_dict_fields.is_empty());
            assert_eq!(reader.searcher().search(query.as_ref(), &Count).unwrap(), 0);
        }
        // The same invalid ordinary range is still rejected during eager validation.
        let invalid: QueryAst =
            serde_json::from_value(serde_json::json!({"type":"range","field":"range_field",
            "lower_bound":{"Included":0},"upper_bound":{"Included":2}}))
            .unwrap();
        assert!(build_query(invalid, &BuildTantivyAstContext::for_test(&old), None).is_err());
    }

    fn ast() -> QueryAst {
        serde_json::from_value(serde_json::json!({
            "type":"tanimoto",
            "candidates":{"type":"term","field":"family","value":"public"},
            "spec":{"format":"morgan-r3-2048-lsb0-v1","rdkit_version":"2025.03.1","preparation_id":"sanitize-only-v1"},
            "fingerprint_hex":format!("01{}", "00".repeat(255)),
            "minimum":0.4
        })).unwrap()
    }

    #[test]
    fn chemistry_warms_fingerprints_and_candidate_postings() {
        let query = ast().parse_user_query(&[]).unwrap();
        let QueryAst::Tanimoto(chemistry) = &query else {
            panic!()
        };
        let field_name = chemistry.spec.field_name();
        let mut builder = Schema::builder();
        builder.add_bytes_field(&field_name, FAST);
        let family = builder.add_text_field("family", STRING);
        let schema = builder.build();
        let (_, warmup) =
            build_query(query, &BuildTantivyAstContext::for_test(&schema), None).unwrap();
        assert!(
            warmup
                .fast_fields
                .iter()
                .any(|field| field.name == field_name)
        );
        assert!(warmup.terms_grouped_by_field.contains_key(&family));
    }

    #[test]
    fn containment_warms_fingerprints_and_preserves_candidate_postings() {
        let QueryAst::Tanimoto(original) = ast() else {
            panic!()
        };
        let field_name = original.spec.field_name();
        let query =
            QueryAst::FingerprintContains(quickwit_query::query_ast::FingerprintContainsQueryAst {
                candidates: original.candidates,
                spec: original.spec,
                fingerprint_hex: original.fingerprint_hex,
                direction: tantivy_rdkit::ContainmentDirection::DocumentContainsQuery,
            });
        let mut builder = Schema::builder();
        builder.add_bytes_field(&field_name, FAST);
        let family = builder.add_text_field("family", STRING);
        let schema = builder.build();
        let (_, warmup) = build_query(
            query.clone(),
            &BuildTantivyAstContext::for_test(&schema),
            None,
        )
        .unwrap();
        assert!(
            warmup
                .fast_fields
                .iter()
                .any(|field| field.name == field_name)
        );
        assert!(warmup.terms_grouped_by_field.contains_key(&family));
        let empty_schema = Schema::builder().build();
        assert!(
            build_query(
                query,
                &BuildTantivyAstContext::for_test(&empty_schema).without_validation(),
                None
            )
            .is_err()
        );
    }

    #[test]
    fn incompatible_split_does_not_become_match_none() {
        let mut builder = Schema::builder();
        builder.add_text_field("family", STRING);
        let schema = builder.build();
        let context = BuildTantivyAstContext::for_test(&schema).without_validation();
        assert!(build_query(ast().parse_user_query(&[]).unwrap(), &context, None).is_err());
    }
}
