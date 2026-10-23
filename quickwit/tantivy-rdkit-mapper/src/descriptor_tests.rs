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

use crate::descriptor::PreparedDocument;
use crate::{CHEMINEE_PREPARATION_ID, fingerprint_spec};

#[test]
fn full_preparation_rejects_incompatible_contract_before_loading_model() {
    assert!(PreparedDocument::from_smiles("CCO", &fingerprint_spec()).is_err());
}

#[test]
fn full_preparation_rejects_invalid_smiles() {
    let mut spec = fingerprint_spec();
    spec.preparation_id = CHEMINEE_PREPARATION_ID.into();
    assert!(PreparedDocument::from_smiles("invalid", &spec).is_err());
}

#[test]
fn full_preparation_has_complete_descriptor_contract() {
    let mut spec = fingerprint_spec();
    spec.preparation_id = CHEMINEE_PREPARATION_ID.into();
    let prepared = PreparedDocument::from_smiles("CCO", &spec).unwrap();
    assert_eq!(prepared.smiles, "CCO");
    assert_eq!(prepared.descriptors.len(), 43);
    assert_eq!(prepared.descriptors["NumHeavyAtoms"], 3.0);
    assert_eq!(prepared.pattern.len(), 256);
    assert_eq!(prepared.scaffolds, vec![-1]);
    assert!(prepared.cluster >= 0 && prepared.cluster < 10000);
}

#[test]
fn successful_preparation_is_reused_without_a_client_prepared_marker() {
    let mut spec = fingerprint_spec();
    spec.preparation_id = CHEMINEE_PREPARATION_ID.into();
    let first = crate::descriptor::prepare_cached("CCO", &spec).unwrap();
    let second = crate::descriptor::prepare_cached("CCO", &spec).unwrap();
    assert!(std::sync::Arc::ptr_eq(&first, &second));
}
