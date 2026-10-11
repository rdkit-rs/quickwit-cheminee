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

//! Offline correctness oracle output. Never used to prepare benchmark ingestion input.
use std::io::{self, BufRead, Write};

use base64::Engine;
use tantivy_rdkit_mapper::descriptor::PreparedDocument;
use tantivy_rdkit_mapper::{CHEMINEE_PREPARATION_ID, fingerprint_spec};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut spec = fingerprint_spec();
    spec.preparation_id = CHEMINEE_PREPARATION_ID.into();
    let mut output = io::BufWriter::new(io::stdout().lock());
    for line in io::stdin().lock().lines() {
        let input: serde_json::Value = serde_json::from_str(&line?)?;
        let smiles = input["smiles"].as_str().ok_or("missing SMILES")?;
        let prepared = PreparedDocument::from_smiles(smiles, &spec)?;
        let result = serde_json::json!({
            "smiles": prepared.smiles,
            "morgan_fingerprint": base64::engine::general_purpose::STANDARD.encode(prepared.fingerprint.as_bytes()),
            "pattern_fingerprint": base64::engine::general_purpose::STANDARD.encode(&prepared.pattern),
            "descriptors": prepared.descriptors,
            "other_descriptors": {"scaffolds": prepared.scaffolds, "similarity_cluster": prepared.cluster},
            "extra_data": input.get("extra_data")
        });
        writeln!(output, "{result}")?;
    }
    output.flush()?;
    Ok(())
}
