#!/usr/bin/env python3
# Copyright 2021-Present Datadog, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Freeze a new 100k raw-SMILES fixture; standard library only, no package import.

The downloaded wheel is a checksum-verified data archive. No wheel code
is installed, imported or executed. This does not reconstruct historical metadata.
"""

import argparse
import csv
import gzip
import hashlib
import heapq
import io
import json
import os
from pathlib import Path
import urllib.request
import zipfile


WHEEL_NAME = "molsets-0.3.1-py3-none-any.whl"
WHEEL_URL = (
    "https://files.pythonhosted.org/packages/ca/04/"
    "335f23e9ae95ca381ac7c3f335303dbbeb0f8a604d167891cf60c9360178/"
    + WHEEL_NAME
)
WHEEL_BYTES = 51_584_291
WHEEL_SHA256 = "7f4450e3ebecebe79c3a2a55950c93daddee071120daf64a163d03481e811d34"
LICENSE_MEMBER = "molsets-0.3.1.dist-info/LICENSE"
LICENSE_SHA256 = "9a40669143195de51e7d0ccee88f0d6b4f3d1da91c5a091293e26d128a02d042"
METADATA_MEMBER = "molsets-0.3.1.dist-info/METADATA"
METADATA_SHA256 = "8afffff60ea09a50fdd4bcd7cc187acae9ee4ae2fa416be8005b3e5dc2bcdbbc"
SOURCES = {
    "test": "f896fbf3764f88d94670b9959e5872c600c12152a18233823e820761b7a791b2",
    "test_scaffolds": "adffb2192c1bfe31ab0e13154d4af19a37dc18bdbf3cd7b4491e04405128adde",
    "train": "786f0313aa6b9ba5514df685f885742a70ea8d86f1a4fa48115f7f80a634265c",
}
COUNT = 100_000
SEED = b"tantivy-rdkit-compression-v1\0"
FIXTURE = "cheminee-pilot-moses-100k-v1"
OBSERVED_AT = "2026-10-23T00:00:00.000000000Z"
MAX_CSV_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 16 * 1024 * 1024
EXPECTED_SPLITS = {"train": 81_777, "test": 9_165, "test_scaffolds": 9_058}
OLD_SHA256 = "9a63bf25bc02ba3c965bb050cd74ba1a059bc362b8fb210b8febb6a326ce2e5e"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_info(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"filename": path.name, "bytes": size, "sha256": digest.hexdigest()}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("unexpected download redirect; stop, do not change source")


def download_wheel(path):
    # Exact public publisher URL, with a hard byte cap below the 250 MiB budget.
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(WHEEL_URL, headers={"User-Agent": FIXTURE})
    size = 0
    with opener.open(request, timeout=30) as response, path.open("xb") as output:
        require(response.status == 200, "download HTTP status is not 200")
        length = response.headers.get("Content-Length")
        require(length is None or int(length) == WHEEL_BYTES, "unexpected Content-Length")
        while True:
            chunk = response.read(min(1024 * 1024, WHEEL_BYTES - size + 1))
            if not chunk:
                break
            size += len(chunk)
            require(size <= WHEEL_BYTES, "wheel download exceeds pinned byte size")
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    require(size == WHEEL_BYTES, "truncated wheel download")


def read_member(archive, name, expected_hash):
    # Read explicit members in memory; never extract an archive pathname.
    info = archive.getinfo(name)
    require(info.file_size <= MAX_ARCHIVE_MEMBER_BYTES, "archive member too large")
    require(not info.is_dir(), "unexpected directory member")
    contents = archive.read(name)
    require(sha256(contents) == expected_hash, "archive member checksum mismatch: " + name)
    return contents


def write_bytes(path, contents):
    with path.open("xb") as output:
        output.write(contents)
        output.flush()
        os.fsync(output.fileno())
    path.chmod(0o444)


def prepare(args):
    output = args.output.resolve()
    # Current executor only admits temporary data. This also makes accidental
    # placement of ~100 MB beside the small repository recipe fail closed.
    require(output.is_relative_to(Path("/tmp")), "output must be a fresh directory under /tmp")
    require(not output.exists(), "output already exists; never overwrite a frozen fixture")
    output.mkdir(mode=0o700)
    if args.wheel:
        wheel = args.wheel.resolve()
        require(wheel.is_relative_to(Path("/tmp")), "cached wheel must be under /tmp")
    else:
        wheel = output / WHEEL_NAME
        download_wheel(wheel)
    info = file_info(wheel)
    require(info["bytes"] == WHEEL_BYTES and info["sha256"] == WHEEL_SHA256,
            "wheel differs from publisher pin; do not inspect or execute it")

    source_info = {}
    all_smiles = set()
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "duplicate ZIP member names")
        license_bytes = read_member(archive, LICENSE_MEMBER, LICENSE_SHA256)
        metadata_bytes = read_member(archive, METADATA_MEMBER, METADATA_SHA256)

        def rows():
            for source, digest in sorted(SOURCES.items()):
                member = "moses/dataset/data/" + source + ".csv.gz"
                compressed = read_member(archive, member, digest)
                with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                    contents = stream.read(MAX_CSV_BYTES + 1)
                    require(len(contents) <= MAX_CSV_BYTES, "CSV exceeds decompression cap")
                stats = {"member": member, "gzip_bytes": len(compressed),
                         "gzip_sha256": digest, "csv_bytes": len(contents),
                         "csv_sha256": sha256(contents), "rows": 0,
                         "raw_smiles_duplicates_against_earlier_rows": 0}
                source_info[source] = stats
                with io.TextIOWrapper(io.BytesIO(contents), encoding="utf-8", newline="") as text:
                    reader = csv.reader(text, strict=True)
                    require(next(reader) == ["SMILES"], "unexpected CSV header")
                    for row, record in enumerate(reader, 1):
                        require(len(record) == 1, "unexpected CSV column count")
                        smiles = record[0]
                        require(bool(smiles) and len(smiles) <= 4096 and smiles.strip() == smiles,
                                "empty, padded or oversized raw SMILES")
                        require(not any(character.isspace() for character in smiles),
                                "whitespace inside raw SMILES")
                        stats["rows"] += 1
                        stats["raw_smiles_duplicates_against_earlier_rows"] += smiles in all_smiles
                        all_smiles.add(smiles)
                        yield (sha256(SEED + smiles.encode("utf-8")), source, row, smiles)

        # ASCII SHA256 hex ordering equals digest-byte ordering. Every source row
        # participates. Do not deduplicate, normalize or change a source SMILES.
        selected = heapq.nsmallest(COUNT, rows())

    require(len(selected) == COUNT, "not enough source rows")
    unique = len({row[3] for row in selected})
    require(unique == COUNT, "selection has duplicate raw SMILES; do not silently replace rows")
    split_counts = {source: sum(row[1] == source for row in selected) for source in SOURCES}
    require(split_counts == EXPECTED_SPLITS, "selection differs from retained split-count recipe")
    raw_path = output / "catalog-offers-100k.ndjson"
    smiles_path = output / "raw-smiles-100k.smi"
    selection_path = output / "selection-100k.tsv"
    with raw_path.open("xb") as raw, smiles_path.open("xb") as smiles_out, selection_path.open("xb") as selection:
        selection.write(b"record_id\tsplit\trow_1based\tselection_sha256\n")
        for record_id, (digest, source, row, smiles) in enumerate(selected, 1):
            record = {
                "record_id": record_id,
                "offer_id": "molsets-0.3.1:" + source + ":" + str(row),
                "supplier": "fixture-moses-" + source,
                "observed_at": OBSERVED_AT,
                "smiles": smiles,
                "provenance": {"fixture": FIXTURE, "dataset": "MOSES", "version": "0.3.1",
                               "split": source, "row_1based": row,
                               "metadata_kind": "synthetic-acceptance"},
            }
            raw.write((json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
            smiles_out.write(smiles.encode("utf-8") + b"\n")
            selection.write(f"{record_id}\t{source}\t{row}\t{digest}\n".encode("ascii"))
        for stream in (raw, smiles_out, selection):
            stream.flush()
            os.fsync(stream.fileno())
    write_bytes(output / "MOSES-LICENSE.txt", license_bytes)
    write_bytes(output / "molsets-0.3.1-METADATA.txt", metadata_bytes)
    outputs = [file_info(path) for path in (raw_path, smiles_path, selection_path)]
    require(outputs[0]["sha256"] != OLD_SHA256, "unexpected equality to historical corpus hash")
    manifest = {
        "fixture": FIXTURE,
        "status": "new immutable raw input; no import, engine run or chemistry audit",
        "old_corpus_recovered": False,
        "historical_reference": {"sha256": OLD_SHA256, "bytes": 20_032_857,
            "relationship": "same documented selection rule and observed split counts; historical metadata/bytes unavailable"},
        "publisher": {"project": "MOSES / molsets", "version": "0.3.1",
            "release_page": "https://pypi.org/project/molsets/0.3.1/",
            "release_json": "https://pypi.org/pypi/molsets/0.3.1/json",
            "wheel_url": WHEEL_URL, "wheel_bytes": WHEEL_BYTES, "wheel_sha256": WHEEL_SHA256,
            "upload_time_utc": "2020-03-26T12:25:09.828842Z",
            "attestation": "PyPI release has no Trusted Publishing provenance attestation"},
        "license": {"declared": "MIT", "copyright": "2018 Insilico Medicine, Inc",
            "notice_member": LICENSE_MEMBER, "notice_sha256": LICENSE_SHA256,
            "retained_notice": "MOSES-LICENSE.txt", "metadata_sha256": METADATA_SHA256,
            "basis": "publisher MIT declaration and bundled notice retained for local acceptance fixture",
            "limitations": "no separate data-specific license found in the wheel; upstream ZINC rights not independently re-audited"},
        "selection": {"count": COUNT, "key": "SHA256(seed_bytes + raw_SMILES_UTF8), split_ASCII, row_1based",
            "seed_hex": SEED.hex(), "seed_display": "tantivy-rdkit-compression-v1\\0",
            "row_numbering": "1-based data rows, excluding CSV header",
            "ordering": "ascending key; first 100000; no normalization or deduplication",
            "split_counts": split_counts,
            "selected_unique_raw_smiles": unique,
            "source_total_rows": sum(item["rows"] for item in source_info.values()),
            "source_unique_raw_smiles": len(all_smiles), "sources": source_info},
        "serialization": {"format": "UTF-8 NDJSON; sorted JSON keys; compact separators; final LF",
            "record_ids": "1..100000 in selection order",
            "metadata": "new synthetic fixture metadata; not historical study metadata or vendor availability",
            "synthetic_observed_at": OBSERVED_AT,
            "supplier_groups": ["fixture-moses-" + split for split in SOURCES]},
        "validation": {"selected_rows": COUNT, "unique_raw_smiles": unique,
            "unique_record_ids": COUNT, "unique_offer_ids": COUNT,
            "chemical_validity": "unverified; independent RDKit required",
            "canonical_structure_uniqueness": "unverified; raw-string uniqueness is not chemical uniqueness",
            "chemical_diversity": "unverified; source split coverage is not a measured diversity result",
            "representativeness": "not established; MOSES is filtered ZINC Clean Leads, not a supplier catalog",
            "engine_ingestion": "not run", "independent_oracle": "not run"},
        "files": outputs,
        "preparer_sha256": file_info(Path(__file__))["sha256"],
        "immutability": "verify SHA256 before use; generated files set read-only; /tmp is ephemeral, not durable evidence",
    }
    write_bytes(output / "corpus-manifest.json", (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    for path in (raw_path, smiles_path, selection_path):
        path.chmod(0o444)
    if not args.wheel:
        wheel.chmod(0o444)
    print(json.dumps({"output_directory": str(output), "manifest": file_info(output / "corpus-manifest.json"),
                      "files": outputs, "split_counts": split_counts, "unique_raw_smiles": unique}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="fresh output directory under /tmp")
    parser.add_argument("--wheel", type=Path, help="reuse a checksum-verified wheel under /tmp; otherwise download official pin")
    prepare(parser.parse_args())
