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

//! The TensorFlow encoder and distance/TopKV2 operations from
//! cheminee-similarity-model 0.1.6 (MIT), with explicit pinned assets and reusable sessions.
use std::path::Path;
use std::sync::{Mutex, OnceLock};

use sha2::{Digest, Sha256};
use tantivy_rdkit::PackedFingerprint;
use tensorflow::{
    DataType, Graph, Operation, SavedModelBundle, Scope, Session, SessionOptions, SessionRunArgs,
    Tensor, ops,
};

use crate::MappingError;

type ModelResult<T> = Result<T, Box<dyn std::error::Error + Send + Sync>>;

struct ClusterModel {
    encoder: SavedModelBundle,
    input: Operation,
    output: Operation,
    centroids: Tensor<f32>,
    rank_session: Session,
    rank_input: Operation,
    rank_centroids: Operation,
    rank_output: Operation,
    // Keep both graphs alive for every session operation.
    _encoder_graph: Graph,
}

static MODEL: OnceLock<Result<Mutex<ClusterModel>, String>> = OnceLock::new();

pub(crate) fn assign(fingerprint: &PackedFingerprint) -> Result<i32, MappingError> {
    let model = MODEL.get_or_init(|| {
        ClusterModel::load()
            .map(Mutex::new)
            .map_err(|e| e.to_string())
    });
    let runtime = model
        .as_ref()
        .map_err(|e| MappingError::Preparation(e.clone()))?
        .lock()
        .map_err(|e| MappingError::Preparation(e.to_string()))?;
    runtime
        .assign(fingerprint)
        .map_err(|e| MappingError::Preparation(e.to_string()))
}

fn verify_assets(directory: &Path) -> ModelResult<()> {
    for (file, expected) in [
        (
            "lf_kmeans_10k_centroids_20241111.csv",
            "5cf1ede6d2193dccd6b552dcce51b49c12cf69b28589e9f98c18311230edec65",
        ),
        (
            "vae_encoder/saved_model.pb",
            "658f9912c06760343341b98ac8659527159a20aec51656574bde6328cc9b294b",
        ),
        (
            "vae_encoder/variables/variables.data-00000-of-00001",
            "9d60970837b9398e6920eb96f61444919426b2f1d3d04f8377c0fc712f6e734f",
        ),
        (
            "vae_encoder/variables/variables.index",
            "886d87f6ec11c70ffc7af7e76bf96699ebc9fa2c4e59f69d74bdbb2a29f33307",
        ),
    ] {
        let bytes = std::fs::read(directory.join(file))?;
        let actual = Sha256::digest(&bytes)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        if actual != expected {
            return Err(format!("Cheminee model checksum mismatch: {file}").into());
        }
    }
    Ok(())
}

impl ClusterModel {
    fn load() -> ModelResult<Self> {
        let directory = std::env::var("QW_CHEMINEE_MODEL_ASSETS").map_err(|_| {
            "descriptor_v1 requires QW_CHEMINEE_MODEL_ASSETS pointing to pinned model assets"
        })?;
        let path = Path::new(&directory);
        verify_assets(path)?;
        let csv = std::fs::read_to_string(path.join("lf_kmeans_10k_centroids_20241111.csv"))?;
        let mut values = Vec::new();
        let mut rows = 0;
        for line in csv.lines() {
            let row = line
                .split(',')
                .map(|v| v.trim().parse::<f32>())
                .collect::<Result<Vec<_>, _>>()?;
            if row.len() != 128 || row.iter().any(|v| !v.is_finite()) {
                return Err("invalid cluster centroid shape or value".into());
            }
            values.extend(row);
            rows += 1;
        }
        let centroids = Tensor::<f32>::new(&[rows, 128]).with_values(&values)?;
        let mut graph = Graph::new();
        let encoder = SavedModelBundle::load(
            &SessionOptions::new(),
            ["serve"],
            &mut graph,
            path.join("vae_encoder"),
        )?;
        let input = graph.operation_by_name_required("serving_default_dense_input")?;
        let output = graph.operation_by_name_required("StatefulPartitionedCall")?;
        let mut scope = Scope::new_root_scope();
        let rank_centroids = ops::Placeholder::new()
            .dtype(DataType::Float)
            .shape(centroids.dims())
            .build(&mut scope)?;
        let rank_input = ops::Placeholder::new()
            .dtype(DataType::Float)
            .build(&mut scope)?;
        let begin = ops::Const::new()
            .dtype(DataType::Int32)
            .value(Tensor::new(&[2]).with_values(&[0i32, 0])?)
            .build(&mut scope)?;
        let size = ops::Const::new()
            .dtype(DataType::Int32)
            .value(Tensor::new(&[2]).with_values(&[1i32, 128])?)
            .build(&mut scope)?;
        let slice = ops::Slice::new().build(rank_input.clone(), begin, size, &mut scope)?;
        // Retain the 0.1.6 batched distance graph, including broadcast and reduction axis.
        let expanded_size = ops::Const::new()
            .dtype(DataType::Int32)
            .value(Tensor::new(&[3]).with_values(&[1i32, rows as i32, 128])?)
            .build(&mut scope)?;
        let centroid_axis = ops::Const::new()
            .dtype(DataType::Int32)
            .value(Tensor::new(&[1]).with_values(&[0i32])?)
            .build(&mut scope)?;
        let centroid_dims =
            ops::ExpandDims::new().build(rank_centroids.clone(), centroid_axis, &mut scope)?;
        let centroid_broadcast =
            ops::BroadcastTo::new().build(centroid_dims, expanded_size.clone(), &mut scope)?;
        let latent_axis = ops::Const::new()
            .dtype(DataType::Int32)
            .value(Tensor::new(&[1]).with_values(&[1i32])?)
            .build(&mut scope)?;
        let latent_dims = ops::ExpandDims::new().build(slice, latent_axis, &mut scope)?;
        let latent_broadcast =
            ops::BroadcastTo::new().build(latent_dims, expanded_size, &mut scope)?;
        let diff = ops::Sub::new().build(centroid_broadcast, latent_broadcast, &mut scope)?;
        let squared = ops::Square::new().build(diff, &mut scope)?;
        let axis = ops::Const::new()
            .dtype(DataType::Int32)
            .value(Tensor::new(&[1]).with_values(&[2i32])?)
            .build(&mut scope)?;
        let mean = ops::Mean::new().build(squared, axis, &mut scope)?;
        let distance = ops::Sqrt::new().build(mean, &mut scope)?;
        let negated = ops::Neg::new().build(distance, &mut scope)?;
        let k = ops::Const::new()
            .dtype(DataType::Int64)
            .value(rows as i64)
            .build(&mut scope)?;
        let rank_output = ops::TopKV2::new().build(negated, k, &mut scope)?;
        let rank_graph = scope.graph();
        let rank_session = Session::new(&SessionOptions::new(), &rank_graph)?;
        Ok(Self {
            encoder,
            input,
            output,
            centroids,
            rank_session,
            rank_input,
            rank_centroids,
            rank_output,
            _encoder_graph: graph,
        })
    }

    fn assign(&self, fingerprint: &PackedFingerprint) -> ModelResult<i32> {
        let bits: Vec<i64> = fingerprint
            .as_bytes()
            .iter()
            .flat_map(|byte| (0..8).map(move |bit| i64::from((byte >> bit) & 1)))
            .collect();
        let input = Tensor::new(&[1, 2048]).with_values(&bits)?;
        let mut encode_args = SessionRunArgs::new();
        encode_args.add_feed(&self.input, 0, &input);
        let encoded_token = encode_args.request_fetch(&self.output, 0);
        self.encoder.session.run(&mut encode_args)?;
        let encoded: Tensor<f32> = encode_args.fetch(encoded_token)?;
        if encoded.dims().len() != 2 || encoded.dims()[0] != 1 || encoded.dims()[1] < 128 {
            return Err(format!("unexpected encoder shape: {:?}", encoded.dims()).into());
        }
        let mut rank_args = SessionRunArgs::new();
        rank_args.add_feed(&self.rank_centroids, 0, &self.centroids);
        rank_args.add_feed(&self.rank_input, 0, &encoded);
        let rank_token = rank_args.request_fetch(&self.rank_output, 1);
        self.rank_session.run(&mut rank_args)?;
        let ranked: Tensor<i32> = rank_args.fetch(rank_token)?;
        ranked
            .first()
            .copied()
            .ok_or_else(|| "empty cluster assignment".into())
    }
}
