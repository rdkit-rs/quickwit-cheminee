# Native SMILES mapping

`tantivy-rdkit` owns the fingerprint contract, fixed-width packed bytes, schema helpers and the Tantivy Query/Weight/Scorer. It has no RDKit or CXX dependency. `tantivy-rdkit-mapper` depends on that core and the pinned rdkit-rs binding revision `0ae060c9cfc14626172070989fee890b16454373` from the open ownership-modernization PR [rdkit-rs/rdkit#57](https://github.com/rdkit-rs/rdkit/pull/57). Updating that revision requires revalidation; this does not imply the binding PR has merged.

Quickwit configuration, JSON field handling, validation and error routing live in `quickwit-doc-mapper::chemistry`. `DocProcessor::process_json_doc` invokes `doc_from_json_obj` on Quickwit's blocking runtime; the adapter computes the fingerprint before ordinary mapping can return an indexable document. There is no custom column format. Existing bytes fast fields are used.

## Contract and preparation

The supported native contract is `morgan-r3-2048-lsb0-v1`, RDKit `2026.09.1`, preparation `sanitize-only-v1`. This is RDKit's default `SmilesToMol` preparation: sanitization and default hydrogen handling, with salts/fragments, charges, isotopes and stereochemistry retained. There is no neutralization, fragment selection, tautomer canonicalization or feature invariant substitution. Morgan radius is 3, width 2048 bits (256 bytes), packing LSB0, chirality and feature invariants disabled. The binding calls `getFingerprintAsBitVect(mol, 3, 2048)` and converts every bit to its corresponding little-endian byte position.

The existing field hash includes the format, RDKit version and preparation identifier. A different version has a different `morgan_<sha256>` field. Native preparation rejects any other contract and also checks the linked RDKit runtime version. Packed queries can still score existing contracts without native RDKit.

Invalid parsing/sanitization and empty/zero-bit molecules return explicit errors. The adapter rejects absent, null or multivalued SMILES, missing/non-u64 IDs and caller-supplied derived fields. It never returns an indexable document without its fingerprint. Ingest validation uses the same adapter and reports per-document schema failures; indexing independently repeats preparation and routes failures through the existing document-mapper counters/logs. This currently computes twice when ingestion validation is enabled. Disabling upstream validation does not disable indexing-time validation.

Canonical **isomeric** SMILES from the prepared molecule are stored for future graph verification, separately from the original input SMILES. They retain the supported molecular graph, isotope and stereo information; they are not an RDKit binary pickle or a preservation format for arbitrary CXSMILES properties/conformers. Native molecule handles are local owned values and never cross asynchronous tasks or enter a shared mapper. Query and indexing use exactly `PreparedMolecule::from_smiles`.

## Native package and linkage

The supported native deployment target is Ubuntu **26.04**, using the project's published APT packages at **2026.09.1+ds1-1~ubuntu26.04**: `librdkit-rs-dev`, `librdkit-rs202609`, and `rdkit-rs-data`. The installer checks OS/architecture, pins all three downloads and verifies their SHA-256 checksums before installation. It uses the existing [rdkit-rs S3 APT repository](https://rdkit-rs-debian.s3.eu-central-1.amazonaws.com/dists/resolute/Release), whose published trust model is HTTPS and unsigned Release metadata (`trusted=yes`); the script adds pinned payload verification. It does not modify repository publication or account settings. The installer currently pins amd64; other architectures need their own verified package hashes.

From the Quickwit workspace on Ubuntu 26.04:

```sh
sudo bash tantivy-rdkit-mapper/ci/install-rdkit.sh
cargo build --locked -p quickwit-cli --features native-chemistry --bin quickwit
ldd target/debug/quickwit
readelf -d target/debug/quickwit
```

The CXX bridge is compiled into a static archive. **Actual RDKit linkage is dynamic**, as explicitly requested by rdkit-sys's `rustc-link-lib=dylib=RDKit...` directives. Native executables need the matching `.so.2026.09` runtime libraries and package dependencies; a static bridge does not make them standalone static binaries. The build requires pkg-config's exact RDKit 2026.09.1 metadata. There is no source-build or older-distro fallback. Custom prefix overrides in rdkit-sys must refer to the same matched installation; mixing headers/libraries is unsupported.

A scoring-only Quickwit build omits `native-chemistry`:

```sh
cargo tree --locked -p quickwit-search -e normal
cargo build --locked -p quickwit-cli --bin quickwit
```

That dependency tree must not contain `rdkit`, `rdkit-sys`, CXX or `tantivy-rdkit-mapper`, and the binary must not contain RDKit dynamic dependencies. It can load chemistry schemas and score packed queries. Native SMILES ingestion and the SMILES endpoint explicitly error when the feature is absent. Features are additive across a Cargo invocation: do not enable a native adapter elsewhere in a build intended to prove pure scoring isolation.

## Quickwit configuration

Add a `chemistry` object to `doc_mapping`, alongside ordinary field mappings. The input and prepared fields are distinct, top-level, single-valued text fields. The prepared field is stored; `record_id` is a stored u64 fast field. The fingerprint field is a single-valued bytes fast field with hexadecimal input. The executable harness writes a complete example to its `index.json`:

```json
{
  "chemistry": {
    "spec": {
      "format": "morgan-r3-2048-lsb0-v1",
      "rdkit_version": "2026.09.1",
      "preparation_id": "sanitize-only-v1"
    },
    "smiles_field": "smiles",
    "prepared_smiles_field": "prepared_smiles"
  }
}
```

An input document supplies `{"record_id": 42, "smiles": "CC(=O)[O-].[Na+]"}` plus declared application fields. Do not supply the fingerprint or `prepared_smiles`; the adapter owns those outputs. `store_source`, when enabled, retains the original document before derivation. Changing the native contract requires a new field and reindexing; existing splits are never relabeled.

`POST /api/v1/{index}/cheminee/search/similarity/smiles` accepts `spec`, `smiles`, and the existing `tanimoto_minimum`, `result_limit`, `extra_query` options. Preparation runs once on the root's CPU pool, then the existing packed query AST is distributed. Leaves receive no SMILES. The packed endpoint remains unchanged. Both endpoints have typed OpenAPI responses and distinct stable operation IDs (`chemineeSearchSimilarity` and `chemineeSearchSimilaritySmiles`).

## Validation and limits

```sh
cargo test --locked -p tantivy-rdkit -p tantivy-rdkit-mapper
cargo test --locked -p quickwit-doc-mapper --features native-chemistry chemistry --lib
cargo test --locked -p quickwit-serve --features native-chemistry cheminee_api --lib
python3 -m venv /tmp/cheminee-python
/tmp/cheminee-python/bin/pip install -r tantivy-rdkit/poc/requirements.txt
/tmp/cheminee-python/bin/python tantivy-rdkit/poc/run.py --binary /path/to/native-quickwit --leaf-binary /path/to/scoring-quickwit --raw-smiles --work-dir /tmp/native-results
```

The raw mode ingests no external fingerprints; Python RDKit 2026.09.1 is solely an independent test oracle and fixture source. That Python wheel is distinct from the C++ APT package used by the application. Both the original packed mode and raw mode retain 168 exhaustive score/count/ID comparisons and the 10,051-match top-1 no-cap check. Raw mode additionally compares the native SMILES query path, tests invalid ingestion, verifies retained prepared molecules, and generates a client for typed success/error responses on both endpoints.

This remains the bounded prototype from PR #1. No exact graph sub/superstructure search, new physical column, broader chemical type system, large-scale benchmark, deployment or release is implemented. The dictionary scan and per-document cardinality checks remain unchanged. Canonicalization can change across RDKit releases, which is why native version and preparation are part of the contract. Historical PR #1 measurements describe its original Python/precomputed path, not proof of this native path; current run results must be inspected separately.
