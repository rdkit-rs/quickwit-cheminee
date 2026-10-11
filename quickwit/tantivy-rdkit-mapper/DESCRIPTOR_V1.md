# In-process descriptor_v1 preparation

Build Quickwit with `--features descriptor-v1`. This includes `native-chemistry`;
the existing fingerprint-only and graph builds remain available without TensorFlow.
Enable `chemistry.descriptor_v1: true` in the index mapping and supply only raw
SMILES, `record_id`, and metadata. Both ingester validation and actor mapping use
the same preparation implementation. Full-chemistry batch validation uses the existing
CPU pool in parallel and preserves input order in its rejection report. No preparation
service or exporter is used.

The mapping requires the existing Cheminee canonical preparation contract, the
43 numeric descriptors with their original integer/f64 types (nested or flat),
`pattern_fingerprint` (base64 bytes), `other_descriptors` (JSON), and the existing
prepared SMILES and contract-hashed Morgan fields. Caller-supplied derived fields
are rejected. Missing, nonfinite, invalid, or incompatible chemistry fails the
document; model failure never produces a fallback cluster.

Descriptors, pattern fingerprints, scaffolds, and Morgan fingerprints are computed
from the neutralized molecule, as in Cheminee. A sanitized SMILES round trip is
validated; its Morgan bytes must agree with the graph-query preparation contract.
This check rejects any incompatible structure instead of silently storing a
fingerprint that queries cannot reproduce. Existing graph/query normalization and
all previous input restrictions remain in force.

The scaffold list is the unchanged Cheminee asset at
`f8d31a604203392f4dfba7d9a84120100b8426b5`. Matching preserves pattern screening,
RDKit's default substructure parameters, scaffold IDs/order and the `[-1]` sentinel.
The TensorFlow graph follows `cheminee-similarity-model` 0.1.6: the encoder's first
128 outputs, broadcast centroid distances, squared difference, mean, square root,
negation and full TopKV2 ranking. Inference is performed in process. Encoder and
ranking sessions are reused, with serialized access; model files are read once.
The first ingestion initializes the model, and initialization cost belongs to the
full ingestion path.

Set `QW_CHEMINEE_MODEL_ASSETS` to the directory containing `vae_encoder/` and
`lf_kmeans_10k_centroids_20241111.csv`. The optional
`ci/install-descriptor-model.sh` fetches the checksum-pinned archive during setup.
The mapper verifies SHA-256 for all four model/centroid files before loading and
performs no network access. TensorFlow's C API must be dynamically available.
The comparison uses publisher-verified TensorFlow CPU 2.15.1 and the same homemade
Ubuntu 26.04 RDKit package as the earlier study. See the benchmark evidence for
exact build inputs and hashes.

A process-local cache retains only successful native chemistry outputs. Its
conservatively estimated owned-capacity budget is 64 MiB. Metadata never enters
the cache, and every document retains ordinary schema/ID validation. Crossing the
budget clears cached entries. Cache misses, eviction, restarts and remote workers
recompute chemistry. The WAL continues to contain original raw inputs; no client
marker can bypass validation. This is an optimization, not a durability or
exactly-once mechanism. The existing timeout/replay correction is unchanged.

`descriptor_audit` is an offline correctness tool, not an ingestion exporter.
Its outputs are never used as benchmark ingestion inputs. Test the deployed REST
path as well as the chemistry/mapper units before claiming the feature works.

## Nested numeric descriptors

For new indexes, set `chemistry.descriptor_layout: nested` and map one top-level
`descriptors` field as `type: json`, `indexed: true`, `stored: true`, `fast: true`.
Do not also declare the 43 top-level numeric descriptor fields. The example in
`tests/fixtures/descriptor_v1.index.json` uses this layout. Integers remain integers,
continuous properties remain f64, and every molecule still receives all 43 values.
Fingerprint, scaffold, learned-cluster and preparation behavior is unchanged.
Caller-supplied `descriptors` or legacy numeric descriptor fields are rejected,
including in dynamic mappings.

Use property paths in Quickwit queries and in chemistry endpoints' `extra_query`:

```text
descriptors.NumAtoms:10
descriptors.NumAtoms:>10 AND descriptors.NumAtoms:<20
descriptors.NumAtoms:>=10 AND descriptors.NumAtoms:<=20
descriptors.NumAtoms:[10 TO 20]
descriptors.NumAtoms:{10 TO 20}
descriptors.exactmw:[136.2 TO 10000]
descriptors.NumAtoms:[* TO 13] AND NOT descriptors.NumAmideBonds:0
```

The colon before a comparison operator is required. Square bounds are inclusive;
curly bounds are exclusive. `*` makes a bound unbounded. Numeric JSON properties
must be fast fields for range queries. Sorting accepts the same property paths,
for example `sort_field: "descriptors.exactmw"` on the Cheminee basic endpoint.
Numeric equality is numeric: an integer-valued float literal can match an integer
property. These queries use Quickwit's query AST, not Tantivy's bare QueryParser.

For compatibility, an omitted `descriptor_layout` retains the existing `flat`
layout and existing query paths. Its fixture is `descriptor_v1.flat.index.json`.
Changing layout requires a new index and reingestion from raw inputs; old index
segments are not rewritten. Clients querying the new index must add the
`descriptors.` prefix to numeric property names. No query aliases silently change
existing behavior. The historical 100k measurements used the flat layout and do
not establish nested-layout performance; the nested layout also enables fast
columns for all 43 descriptors, unlike the historical schema.
