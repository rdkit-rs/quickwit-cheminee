#!/usr/bin/env python3
"""Project the server's exported schema and generate a pinned Ruby/Faraday SDK.

This command builds local artifacts only. It never publishes or writes credentials.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

GENERATOR_VERSION = "7.11.0"
GENERATOR_SHA256 = "113c25df5a781d5a1fc2b883f12fe8f263db285ab12e15854d5b15306e1bf7fc"
OPERATIONS = {
    ("/api/v1/indexes", "post"): "createIndex",
    ("/api/v1/indexes/{index_id}", "delete"): "deleteIndex",
    ("/api/v1/indexes/{index_id}/describe", "get"): "describeIndex",
    ("/api/v1/{index_id}/ingest", "post"): "ingest",
    ("/health/readyz", "get"): "ready",
    **{(f"/v1/indexes/{{index_id}}/search/{kind}", "post"): f"chemineeV1{kind.title()}"
       for kind in ("basic", "identity", "substructure", "superstructure", "similarity")},
}


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def references(value):
    if isinstance(value, dict):
        if "$ref" in value:
            yield value["$ref"]
        # Discriminator mappings are references too, even though not named $ref.
        mapping = value.get("discriminator", {}).get("mapping", {})
        yield from mapping.values()
        for child in value.values():
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def project(combined):
    if combined.get("security"):
        raise ValueError("Top-level authentication requires an explicit SDK contract update")
    selected = {"openapi": combined["openapi"], "info": copy.deepcopy(combined["info"]),
                "paths": {}, "components": {}, "tags": [{"name": "Default"}]}
    selected["info"]["title"] = "Quickwit-Cheminee public Ruby contract"
    for (path, method), name in OPERATIONS.items():
        original = combined["paths"][path]
        op = copy.deepcopy(original[method])  # Missing operations are fatal.
        if op.get("security"):
            raise ValueError("Operation authentication requires an explicit SDK contract update")
        op["operationId"] = name
        op["tags"] = ["Default"]
        target = selected["paths"].setdefault(path, {})
        target[method] = op
        if "parameters" in original:
            target["parameters"] = copy.deepcopy(original["parameters"])
    # Only local component references are accepted. Include their transitive closure.
    pending = list(references(selected))
    seen = set()
    while pending:
        ref = pending.pop()
        if ref in seen:
            continue
        match = re.fullmatch(r"#/components/([^/]+)/([^/]+)", ref)
        if not match:
            raise ValueError(f"Unsupported component reference: {ref}")
        category, name = match.groups()
        value = copy.deepcopy(combined["components"][category][name])
        selected["components"].setdefault(category, {})[name] = value
        seen.add(ref)
        pending.extend(references(value))
    ingest = selected["paths"]["/api/v1/{index_id}/ingest"]["post"]
    if set(ingest["requestBody"]["content"]) != {"application/x-ndjson"}:
        raise ValueError("Ingest must advertise raw application/x-ndjson")
    if not any(p.get("name") == "detailed_response" and p.get("in") == "query"
               for p in ingest["parameters"]):
        raise ValueError("Ingest must expose detailed_response")
    mapping = selected["components"]["schemas"]["FieldMappingEntryForSerialization"]
    if (mapping.get("type") != "object" or set(mapping.get("required", [])) != {"name", "type"}
            or set(mapping.get("properties", {})) != {"name", "type"}
            or any(mapping["properties"][key].get("type") != "string" for key in ("name", "type"))
            or any(key in mapping for key in ("allOf", "oneOf", "anyOf"))
            or mapping.get("additionalProperties") not in ({}, True)):
        raise ValueError("Field mapping options must permit arbitrary JSON values")
    # Ruby 7.11.0 drops additionalProperties on models with named properties.
    # Enable the pinned template correction only for this verified open mapping.
    mapping["x-preserve-mapping-options"] = True
    reject_composition_cycles(selected)
    normalize_discriminators(selected)
    distribute_union_parents(selected)
    return selected


def reject_composition_cycles(schema):
    schemas = schema["components"].get("schemas", {})

    def edges(value):
        if "$ref" in value:
            yield value["$ref"].split("/")[-1]
        for keyword in ("allOf", "oneOf", "anyOf"):
            for member in value.get(keyword, []):
                yield from edges(member)

    complete, visiting = set(), set()

    def visit(name):
        if name in visiting:
            raise ValueError(f"Recursive composition cannot be projected: {name}")
        if name in complete:
            return
        visiting.add(name)
        for target in edges(schemas[name]):
            visit(target)
        visiting.remove(name)
        complete.add(name)

    for name in schemas:
        visit(name)


def normalize_discriminators(schema):
    """Name Utoipa's inline tagged variants and make their mappings explicit.

    Without mappings the Ruby generator treats a wire tag such as "0.9" as a
    Ruby constant name. Variants and their enum constraints are preserved exactly.
    """
    schemas = schema["components"].get("schemas", {})

    def tags(value, property_name):
        if "$ref" in value:
            return tags(schemas[value["$ref"].split("/")[-1]], property_name)
        result = list(value.get("properties", {}).get(property_name, {}).get("enum", []))
        for child in value.get("allOf", []):
            result.extend(tags(child, property_name))
        return result

    for name, value in list(schemas.items()):
        discriminator = value.get("discriminator")
        if not discriminator:
            continue
        if discriminator.get("mapping"):
            continue
        mapping, variants = {}, []
        for i, variant in enumerate(value["oneOf"]):
            labels = tags(variant, discriminator["propertyName"])
            if not labels or any(not isinstance(label, str) for label in labels):
                raise ValueError(f"Cannot resolve discriminator for {name}")
            component = f"{name}Variant{i}"
            if component in schemas:
                raise ValueError(f"Component collision: {component}")
            ref = f"#/components/schemas/{component}"
            schemas[component] = variant
            variants.append({"$ref": ref})
            for label in labels:
                if label in mapping:
                    raise ValueError(f"Ambiguous discriminator for {name}: {label}")
                mapping[label] = ref
        value["oneOf"] = variants
        discriminator["mapping"] = mapping


def distribute_union_parents(schema):
    """Distribute allOf over a tagged oneOf without weakening any member.

    Ruby cannot subclass the Module emitted for a oneOf. Keep version/source-type
    discrimination nested and preserve every original allOf member and constraint.
    """
    schemas = schema["components"]["schemas"]
    changed = True
    while changed:
        changed = False
        for name, value in list(schemas.items()):
            for i, member in enumerate(value.get("allOf", [])):
                ref = member.get("$ref", "")
                parent = schemas.get(ref.split("/")[-1], {}) if ref else {}
                if not parent.get("oneOf"):
                    continue
                if set(value) - {"allOf", "description", "title", "deprecated"}:
                    raise ValueError(f"Union intersection has unsupported siblings: {name}")
                if set(parent) - {"oneOf", "discriminator", "description", "title", "deprecated"}:
                    raise ValueError(f"Union parent has unsupported siblings: {name}")
                if not parent.get("discriminator", {}).get("mapping"):
                    raise ValueError(f"Union parent needs an explicit mapping: {name}")
                if set(parent["discriminator"]["mapping"].values()) != {
                        item.get("$ref") for item in parent["oneOf"]}:
                    raise ValueError(f"Discriminator does not cover union members: {name}")
                translated, variants = {}, []
                for j, variant in enumerate(parent["oneOf"]):
                    if len(schemas) >= 5000:
                        raise ValueError("SDK schema expansion exceeds 5000 components")
                    if set(variant) != {"$ref"}:
                        raise ValueError(f"Union member must be named: {name}")
                    child_name = f"{name}Member{j}"
                    if child_name in schemas:
                        raise ValueError(f"Component collision: {child_name}")
                    child_ref = f"#/components/schemas/{child_name}"
                    members = copy.deepcopy(value["allOf"])
                    members[i] = copy.deepcopy(variant)
                    schemas[child_name] = {"allOf": members}
                    translated[variant["$ref"]] = child_ref
                    variants.append({"$ref": child_ref})
                discriminator = copy.deepcopy(parent["discriminator"])
                discriminator["mapping"] = {
                    label: translated[target] for label, target in discriminator["mapping"].items()}
                schemas[name] = {**{k: v for k, v in value.items() if k != "allOf"},
                                 "oneOf": variants, "discriminator": discriminator}
                changed = True
                break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--combined-schema", type=Path, required=True)
    parser.add_argument("--generator-jar", type=Path, required=True)
    parser.add_argument("--server-revision", required=True)
    parser.add_argument("--gem-version", required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="New/empty output directory; never overwrites an existing SDK")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.server_revision):
        parser.error("server-revision must be a full Git SHA")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:\.[A-Za-z0-9]+)*", args.gem_version):
        parser.error("gem-version must be an explicit Ruby version, e.g. 0.9.1.pre.pr3")
    if sha256(args.generator_jar.read_bytes()) != GENERATOR_SHA256:
        parser.error("generator JAR checksum mismatch")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("output directory must be empty")
    raw = args.combined_schema.read_bytes()
    schema = canonical(project(json.loads(raw)))
    config = Path(__file__).with_name("generator-config.json")
    templates = Path(__file__).with_name("templates")
    args.output.mkdir(parents=True, exist_ok=True)
    spec = args.output / "openapi.json"
    spec.write_bytes(schema)
    subprocess.run(["java", "-jar", str(args.generator_jar), "validate", "-i", str(spec)], check=True)
    subprocess.run(["java", "-jar", str(args.generator_jar), "generate", "-g", "ruby",
                    "--library", "faraday", "-i", str(spec), "-c", str(config),
                    "-t", str(templates),
                    "--additional-properties", f"gemVersion={args.gem_version}",
                    "-o", str(args.output)], check=True)
    # Server revision is supplied by the export job, not inferred from schema version.
    manifest = {"server_revision": args.server_revision,
                "server_version": json.loads(raw)["info"]["version"],
                "gem_version": args.gem_version, "generator_version": GENERATOR_VERSION,
                "generator_sha256": GENERATOR_SHA256,
                "generator_config_sha256": sha256(config.read_bytes()),
                "projection_script_sha256": sha256(Path(__file__).read_bytes()),
                "template_sha256": {p.name: sha256(p.read_bytes()) for p in sorted(templates.glob("*.mustache"))},
                "ruby_dependency_lock_sha256": sha256(Path(__file__).with_name("Gemfile.lock").read_bytes()),
                "combined_schema_sha256": sha256(raw), "sdk_schema_sha256": sha256(schema),
                "publication_authorized": False,
                "operation_count": len(OPERATIONS)}
    (args.output / "provenance.json").write_bytes(canonical(manifest))
    license_file = Path(__file__).resolve().parents[2] / "LICENSE"
    (args.output / "LICENSE").write_bytes(license_file.read_bytes())
    for path in args.output.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)


if __name__ == "__main__":
    main()
