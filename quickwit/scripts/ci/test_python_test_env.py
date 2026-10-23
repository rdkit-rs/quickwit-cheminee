import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


spec = importlib.util.spec_from_file_location("python_test_env", Path(__file__).with_name("python_test_env.py"))
environment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(environment)


class LockedEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "Pipfile.lock"
        version = f"{sys.version_info.major}.{sys.version_info.minor}"
        source = {"name": "pypi", "url": "https://pypi.org/simple", "verify_ssl": True}
        self.pipfile = f'[[source]]\nname = "pypi"\nurl = "https://pypi.org/simple"\nverify_ssl = true\n[packages]\nrequests = "*"\n[dev-packages]\n[requires]\npython_version = "{version}"\n'
        (self.root / "Pipfile").write_text(self.pipfile)
        hashed = {"_meta": {"sources": [source], "requires": {"python_version": version}},
                  "default": {"requests": "*"}, "develop": {}}
        digest = hashlib.sha256(json.dumps(hashed, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.lock = {"_meta": {**hashed["_meta"], "hash": {"sha256": digest}},
                     "default": {"requests": {"version": "==2.33.0", "hashes": ["sha256:" + "a" * 64]}}, "develop": {}}
        self.write_lock()

    def write_lock(self):
        self.path.write_text(json.dumps(self.lock))

    def test_matching_manifest_is_accepted(self):
        lock, pipfile = environment.read_lock(self.path)
        self.assertEqual(lock["default"]["requests"]["version"], "==2.33.0")
        self.assertEqual(pipfile["packages"], {"requests": "*"})

    def test_stale_manifest_fails_before_environment_creation(self):
        (self.root / "Pipfile").write_text(self.pipfile.replace('requests = "*"', 'requests = ">=2.34"'))
        destination = self.root / "venv"
        with self.assertRaisesRegex(ValueError, "stale"):
            environment.install(self.path, destination)
        self.assertFalse(destination.exists())

    def test_unpinned_or_unhashed_packages_are_rejected(self):
        for replacement in [{"version": ">=2.33.0", "hashes": ["sha256:" + "a" * 64]},
                            {"version": "==2.33.0", "hashes": []}]:
            with self.subTest(replacement=replacement):
                self.lock["default"]["requests"] = replacement
                self.write_lock()
                with self.assertRaises(ValueError):
                    environment.read_lock(self.path)

    def test_different_interpreter_is_rejected(self):
        self.lock["_meta"]["requires"]["python_version"] = "3.1"
        self.write_lock()
        with self.assertRaisesRegex(ValueError, "Python version"):
            environment.read_lock(self.path)

    def test_changed_source_is_rejected(self):
        self.lock["_meta"]["sources"][0]["url"] = "http://example.invalid/simple"
        self.write_lock()
        with self.assertRaisesRegex(ValueError, "verified PyPI"):
            environment.read_lock(self.path)

    def test_direct_urls_and_extras_cannot_enter_through_lock(self):
        self.lock["default"]["requests"]["file"] = "https://example.invalid/package.whl"
        self.write_lock()
        with self.assertRaisesRegex(ValueError, "unsupported lock entry"):
            environment.read_lock(self.path)

    def test_download_hash_mismatch_is_not_written(self):
        with patch.object(environment.urllib.request, "urlopen", return_value=io.BytesIO(b"wrong content")):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                environment.download("https://files.pythonhosted.org/package.whl", "a" * 64, self.root)
        self.assertFalse((self.root / "package.whl").exists())

    def test_ambiguous_wheel_metadata_is_rejected(self):
        wheel = self.root / "package.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("one.dist-info/METADATA", "Name: one\nVersion: 1\n")
            archive.writestr("two.dist-info/METADATA", "Name: two\nVersion: 1\n")
        with self.assertRaisesRegex(ValueError, "one wheel METADATA"):
            environment.wheel_metadata(wheel)


class WheelValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="quickwit-packaging-tests-")
        cls.addClassCleanup(cls.temporary.cleanup)
        url, digest = environment.BOOTSTRAP["packaging"]
        wheel = environment.download(url, digest, Path(cls.temporary.name))
        sys.path.insert(0, str(wheel))
        cls.addClassCleanup(sys.path.remove, str(wheel))
        import packaging

        if not packaging.__file__.startswith(str(wheel) + "/"):
            raise RuntimeError("wheel tests must use checksum-verified pinned packaging")

    def metadata(self, name="sample", version="1.0", requirement=None):
        raw = f"Name: {name}\nVersion: {version}\n"
        if requirement:
            raw += f"Requires-Dist: {requirement}\n"
        return environment.BytesParser().parsebytes(raw.encode())

    def test_missing_transitive_dependency_is_rejected(self):
        selected = {"sample": {"version": "==1.0"}}
        metadata = {"sample": self.metadata(requirement="dependency>=2")}
        with self.assertRaisesRegex(ValueError, "incomplete or incompatible lock"):
            environment.verify_closure(selected, metadata, {"sample": "*"})

    def test_incompatible_transitive_version_is_rejected(self):
        selected = {"sample": {"version": "==1.0"}, "dependency": {"version": "==1.5"}}
        metadata = {"sample": self.metadata(requirement="dependency>=2"),
                    "dependency": self.metadata(name="dependency", version="1.5")}
        with self.assertRaisesRegex(ValueError, "incomplete or incompatible lock"):
            environment.verify_closure(selected, metadata, {"sample": "*"})

    def test_metadata_identity_mismatch_is_rejected(self):
        selected = {"sample": {"version": "==1.0"}}
        for metadata in [self.metadata(name="different"), self.metadata(version="1.1")]:
            with self.subTest(metadata=metadata):
                with self.assertRaisesRegex(ValueError, "identity mismatch"):
                    environment.verify_closure(selected, {"sample": metadata}, {"sample": "*"})

    def test_inactive_dependency_marker_does_not_add_a_package(self):
        selected = {"sample": {"version": "==1.0"}}
        metadata = {"sample": self.metadata(requirement='optional>=2; extra == "optional"')}
        environment.verify_closure(selected, metadata, {"sample": "*"})

    def test_incompatible_wheel_tag_version_or_hash_is_rejected(self):
        from packaging.tags import Tag

        spec = {"version": "==1.0", "hashes": ["sha256:" + "a" * 64]}
        supported = {Tag("py3", "none", "any"): 0}
        for filename, digest in [("sample-1.0-cp311-cp311-win_amd64.whl", "a" * 64),
                                 ("sample-1.1-py3-none-any.whl", "a" * 64),
                                 ("sample-1.0-py3-none-any.whl", "b" * 64)]:
            with self.subTest(filename=filename, digest=digest):
                release = {"urls": [{"filename": filename, "packagetype": "bdist_wheel",
                                     "digests": {"sha256": digest}, "yanked": False}]}
                with self.assertRaisesRegex(ValueError, "no compatible hash-locked wheel"):
                    environment.select_wheel("sample", spec, release, supported)

    def test_compatible_hash_locked_wheel_is_selected(self):
        from packaging.tags import Tag

        spec = {"version": "==1.0", "hashes": ["sha256:" + "a" * 64]}
        item = {"filename": "sample-1.0-py3-none-any.whl", "packagetype": "bdist_wheel",
                "digests": {"sha256": "a" * 64}, "yanked": False}
        self.assertEqual(environment.select_wheel("sample", spec, {"urls": [item]},
                                                 {Tag("py3", "none", "any"): 0}), item)


if __name__ == "__main__":
    unittest.main()
