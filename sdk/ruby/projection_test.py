"""Regression checks for the generated client's schema transformations."""
import copy
import json
from pathlib import Path
import sys
import unittest

from generate import OPERATIONS, distribute_union_parents, project, references, reject_composition_cycles

COMBINED = json.loads(Path(sys.argv.pop(1)).read_text())


class ProjectionTest(unittest.TestCase):
    def test_public_surface_and_all_references(self):
        sdk = project(COMBINED)
        methods = {(p, method) for p, item in sdk["paths"].items()
                   for method in item if method in {"post", "get", "delete", "put"}}
        self.assertEqual(set(OPERATIONS), methods)
        for ref in references(sdk):
            _, _, category, name = ref.split("/")
            self.assertIn(name, sdk["components"][category])

    def test_determinism_and_no_mutation(self):
        before = copy.deepcopy(COMBINED)
        self.assertEqual(project(COMBINED), project(COMBINED))
        self.assertEqual(before, COMBINED)

    def test_missing_contract_or_security_is_fatal(self):
        changed = copy.deepcopy(COMBINED)
        del changed["paths"]["/api/v1/{index_id}/ingest"]
        with self.assertRaises(KeyError):
            project(changed)
        changed = copy.deepcopy(COMBINED)
        changed["security"] = [{"bearer": []}]
        with self.assertRaises(ValueError):
            project(changed)

    def test_recursive_composition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Recursive composition"):
            reject_composition_cycles({"components": {"schemas": {
                "Loop": {"allOf": [{"$ref": "#/components/schemas/Loop"}]}}}})

    def test_alias_mapping_and_constraints_survive_distribution(self):
        base = {"type": "object", "additionalProperties": False,
                "properties": {"params": {"type": "string"}}}
        common = {"type": "object", "properties": {"enabled": {"type": "boolean"}}}
        schema = {"components": {"schemas": {
            "Concrete": base,
            "Union": {"oneOf": [{"$ref": "#/components/schemas/Concrete"}],
                      "discriminator": {"propertyName": "kind", "mapping": {
                          "a": "#/components/schemas/Concrete", "alias": "#/components/schemas/Concrete"}}},
            "Child": {"allOf": [{"$ref": "#/components/schemas/Union"}, common], "description": "retain"}
        }}}
        distribute_union_parents(schema)
        result = schema["components"]["schemas"]
        self.assertEqual(base, result["Concrete"])
        self.assertEqual(common, result["ChildMember0"]["allOf"][1])
        self.assertEqual("retain", result["Child"]["description"])
        mapping = result["Child"]["discriminator"]["mapping"]
        self.assertEqual(mapping["a"], mapping["alias"])

    def test_parent_union_constraints_are_not_silently_discarded(self):
        schema = {"components": {"schemas": {
            "V": {"type": "object"},
            "U": {"oneOf": [{"$ref": "#/components/schemas/V"}],
                  "required": ["mandatory"],
                  "discriminator": {"propertyName": "kind", "mapping": {"v": "#/components/schemas/V"}}},
            "C": {"allOf": [{"$ref": "#/components/schemas/U"}, {"type": "object"}]}}}}
        with self.assertRaisesRegex(ValueError, "Union parent has unsupported siblings"):
            distribute_union_parents(schema)

    def test_source_union_members_retain_tag_and_common_intersections(self):
        sdk = project(COMBINED)["components"]["schemas"]
        for version in ("0.7", "0.9"):
            parent_ref = sdk["VersionedSourceConfig"]["discriminator"]["mapping"][version]
            parent = sdk[parent_ref.split("/")[-1]]
            self.assertEqual("source_type", parent["discriminator"]["propertyName"])
            self.assertEqual(11, len(parent["oneOf"]))
        self.assertEqual("type", sdk["TokenizerEntry"]["discriminator"]["propertyName"])


if __name__ == "__main__":
    unittest.main()
