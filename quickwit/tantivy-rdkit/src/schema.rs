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

use tantivy::schema::{FAST, Field, FieldType, STORED, Schema, SchemaBuilder};

use crate::{FingerprintSpec, invalid};

#[derive(Clone, Copy, Debug)]
pub struct MoleculeFields {
    pub fingerprint: Field,
    pub prepared_smiles: Field,
}

impl MoleculeFields {
    pub fn add_to_schema(
        builder: &mut SchemaBuilder,
        spec: &FingerprintSpec,
        prepared_name: &str,
    ) -> tantivy::Result<Self> {
        spec.validate()?;
        Ok(Self {
            fingerprint: builder.add_bytes_field(&spec.field_name(), FAST),
            prepared_smiles: builder.add_text_field(prepared_name, STORED | FAST),
        })
    }

    pub fn from_schema(
        schema: &Schema,
        spec: &FingerprintSpec,
        prepared_name: &str,
    ) -> tantivy::Result<Self> {
        spec.validate()?;
        let fingerprint = schema.get_field(&spec.field_name())?;
        let fingerprint_entry = schema.get_field_entry(fingerprint);
        if !matches!(fingerprint_entry.field_type(), FieldType::Bytes(_))
            || !fingerprint_entry.is_fast()
        {
            return Err(invalid("fingerprint field must be bytes with fast=true"));
        }
        let prepared_smiles = schema.get_field(prepared_name)?;
        let prepared_entry = schema.get_field_entry(prepared_smiles);
        if !matches!(prepared_entry.field_type(), FieldType::Str(_)) || !prepared_entry.is_stored()
        {
            return Err(invalid("prepared molecule field must be stored text"));
        }
        Ok(Self {
            fingerprint,
            prepared_smiles,
        })
    }
}
