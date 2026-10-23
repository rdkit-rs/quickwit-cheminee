# New MOSES 100k acceptance fixture

`cheminee-pilot-moses-100k-v1` is a new, checksum-frozen input for the proposed
local kind/object-store acceptance. Preparation completed on 2026-10-23. No
engine import, benchmark, container, native build or RDKit evaluation ran here.
The old corpus was **not recovered**. Its documented 20,032,857-byte file and
SHA-256 `9a63bf25bc02ba3c965bb050cd74ba1a059bc362b8fb210b8febb6a326ce2e5e`
remain historical references; no old metadata or byte identity is claimed.

The new file contains 100,000 different raw SMILES, selected from all 1,936,962
different raw strings in the three pinned source splits. Selection is the first
100,000 rows ordered by `SHA256(b'tantivy-rdkit-compression-v1\0' + smiles_utf8)`,
then split name and one-based data row. CSV headers are excluded from row numbers.
SMILES are preserved exactly, without deduplication or normalization. The observed
81,777 train / 9,165 test / 9,058 scaffold-test counts agree with the retained
recipe. This agreement does not verify the absent historical file's bytes.

## Reproduce in an admitted execution environment

Use Python 3.9+ with its standard library only:

```sh
python3 docs/cheminee-campaign/corpus-preparation/prepare_corpus.py \
  --output /tmp/cheminee-pilot-moses-100k-v1
```

The output directory must not exist. The script downloads only the exact official
PyPI wheel URL pinned in the manifest, at most 51,584,291 bytes (49.2 MiB), and
requires its published SHA-256 before reading it. It refuses redirects, changed
bytes and existing output directories. HTTP denial is a blocker: do not substitute
a proxy, mirror, credential or altered network setting. To reuse a wheel already
under `/tmp`, add `--wheel /tmp/path/molsets-0.3.1-py3-none-any.whl`; the same size
and hash verification still applies.

The wheel is read as ZIP/GZIP/CSV data using explicit member names and decompression
caps. Nothing is extracted by archive pathname, installed, imported or executed.
The output contains raw offers, raw SMILES, a row-to-source selection table,
manifest, publisher metadata and the complete MIT license notice. Files are set
read-only after writing; verify their SHA-256 again before every use. `/tmp` is
ephemeral RAM-backed storage in the preparation executor, not durable evidence.
Regenerate these inputs in the new environment and preserve the verified bytes
and notices on admitted durable storage before relying on recovery evidence.

The retained manifest must match the regenerated manifest byte-for-byte when
this exact script is used. A mismatch is a stop condition, not permission to
replace the expected hashes. Generated native preparation and independent oracle
outputs belong in separately versioned artifacts and must never replace the raw
input.

| Output | Bytes | SHA-256 |
| --- | ---: | --- |
| `catalog-offers-100k.ndjson` | 35,720,502 | `7bbf24a94d4d2ffb2080561205236cdce844e8b420fe24107ab72a25e5f59632` |
| `raw-smiles-100k.smi` | 3,688,674 | `9b1bdd383de20d4bbf4b64ba56422a184e29981f20660ae77f092c6d6a7698b0` |
| `selection-100k.tsv` | 8,474,227 | `a9a413ce50a4faf78cbc3ba7775dc5738861dba6de23dbdcffe5ec74e17b0a76` |

## Catalog importer shape

Every offer has `record_id` (integer 1..100000, within u64), stable `offer_id`
(`molsets-0.3.1:<split>:<source-row>`), exact source `smiles`, `supplier`,
`observed_at` and source `provenance`. Supplier labels are synthetic groups:
`fixture-moses-test`, `fixture-moses-test_scaffolds`, `fixture-moses-train`.
The timestamp `2026-10-23T00:00:00.000000000Z` is a fixed fixture value, not a
supplier observation or availability claim. All non-SMILES catalog metadata is
new synthetic acceptance metadata.

To construct a `CatalogGeneration` input, first verify the manifest and every
file hash, parse all 100,000 offers, and group by the exact `supplier` value. Use
the same three sorted names as `expected_suppliers` and manifest `suppliers`.
Wrap each group in one snapshot with `supplier`, `sequence: 1`, `complete: true`,
the fixed `observed_at`, and `offers`. Mark it complete only after validating the
entire frozen fixture and expected per-group counts. Here completeness means
the full selected synthetic group; it makes no assertion about the complete
upstream MOSES dataset, a vendor catalog, or current stock. Preserve original
source row identities across separately documented refresh/withdrawal fixtures.
Do not run this wrapping/import workflow until the parent admission gates pass.

## Provenance, permission and limits

The [official MOSES repository](https://github.com/molecularsets/moses) identifies
`molsets` as its PyPI package. The
[official 0.3.1 release](https://pypi.org/project/molsets/0.3.1/) supplies the pinned
wheel and SHA-256 and declares MIT. Its bundled metadata also declares MIT, and
its bundled notice is retained verbatim in [MOSES-LICENSE.txt](MOSES-LICENSE.txt).
This publisher declaration and retained notice are the permission basis for this
local acceptance fixture. No separate dataset-specific license was found among
the wheel's license/metadata files. Upstream ZINC rights have not been independently
re-audited; its official website returned HTTP 403 to the read-only browser check.
Do not represent that missing check as completed redistribution clearance.
PyPI reports no publishing provenance attestation for this 2020 release; the
publisher's version, byte size and SHA-256 are recorded rather than an attestation.

The MOSES authors describe a filtered ZINC Clean Leads dataset, with constrained
molecular weight and rotatable bonds, charge/element/ring exclusions, and
medicinal-chemistry filters. It therefore covers a limited chemistry domain.
Its separate scaffold-test split motivates including all three sources, but no
scaffold count, chemical diversity statistic or catalog representativeness has
been measured for this selection. These source descriptions are from the
[publisher README](https://github.com/molecularsets/moses#dataset), not results of
a local chemistry audit.

Raw JSON readback independently confirmed 100,000 records, unique record IDs,
offer IDs and raw SMILES, along with all split counts. Chemical validity,
canonical structure uniqueness, stereochemical identity, fingerprint truth and
structural diversity remain **unverified until independent RDKit evaluation**.
The earlier study's reported 99,989 normalized structures is not evidence for
the current preparation path. MOSES alone does not qualify salt, charge or other
chemistry excluded by its source filters; keep separately identified edge fixtures.

See [corpus-manifest.json](corpus-manifest.json) for member/output hashes and
[source-evidence.json](source-evidence.json) for the retained evidence references.
