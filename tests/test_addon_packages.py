import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from metin2_studio.addons.hubcore.packages import PackageError, discover_packages, load_package, logical_path, validate_manifest


def manifest(content=b"VALUE = 1\n"):
    return {"schema_version": 1, "id": "demo.markers", "name": "Markers", "version": "1.0.0",
            "description": "Test markers", "author": "Tests", "category": "Maps", "kind": "client-python",
            "entry": "m2hub_addons.markers", "requires": [], "conflicts": [], "capabilities": ["map.markers"],
            "files": [{"source": "markers.py", "target": "m2hub_addons/markers.py",
                       "sha256": hashlib.sha256(content).hexdigest()}]}


class PackageTests(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).resolve().parents[1] / ".test-tmp"
        temporary_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temporary_root)
        self.root = Path(self.temp.name)
        self.package = self.root / "markers"
        (self.package / "payload").mkdir(parents=True)
        (self.package / "payload" / "markers.py").write_bytes(b"VALUE = 1\n")
        self.write_manifest(manifest())

    def tearDown(self):
        self.temp.cleanup()

    def write_manifest(self, value):
        (self.package / "addon.json").write_text(json.dumps(value), encoding="utf-8")

    def test_valid_package_loads_and_hash_is_stable(self):
        first = load_package(self.package)
        second = load_package(self.package)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.files, {"m2hub_addons/markers.py": b"VALUE = 1\n"})

    def test_path_traversal_and_windows_special_paths_rejected(self):
        for path in ("../outside", "/outside", "C:/outside", "a\\b", "a//b", "a/./b", "NUL.txt",
                     "a/COM1", "a/trailing.", "a/trailing ", "x:stream", "a/*"):
            with self.subTest(path=path), self.assertRaises(PackageError):
                logical_path(path)

    def test_source_traversal_rejected_before_read(self):
        value = manifest()
        value["files"][0]["source"] = "../../outside.py"
        self.write_manifest(value)
        with self.assertRaisesRegex(PackageError, "Unsafe"):
            load_package(self.package)

    def test_game_and_framework_paths_rejected(self):
        for target in ("ui.py", "m2hub_config.py", "m2hub_runtime.py", "m2hub_addons_other/thing.py"):
            value = manifest()
            value["files"][0]["target"] = target
            with self.subTest(target=target), self.assertRaises(PackageError):
                validate_manifest(value)

    def test_checksum_is_verified(self):
        (self.package / "payload" / "markers.py").write_bytes(b"changed")
        with self.assertRaisesRegex(PackageError, "SHA-256 mismatch"):
            load_package(self.package)

    def test_case_collisions_rejected(self):
        value = manifest()
        value["files"].append(dict(value["files"][0], target="m2hub_addons/Markers.py"))
        with self.assertRaisesRegex(PackageError, "case collisions"):
            validate_manifest(value)

    def test_entry_must_exist(self):
        value = manifest()
        value["entry"] = "m2hub_addons.missing"
        with self.assertRaisesRegex(PackageError, "entry module"):
            validate_manifest(value)

    def test_dependency_identity_validation(self):
        for requires in (["demo.markers"], ["invalid"], ["demo.base", "demo.base"]):
            value = manifest()
            value["requires"] = requires
            with self.subTest(requires=requires), self.assertRaises(PackageError):
                validate_manifest(value)

    def test_common_namespace_rejects_executable_content(self):
        content = b"import os\n"
        (self.package / "payload" / "__init__.py").write_bytes(content)
        value = manifest()
        value["files"].append({"source": "__init__.py", "target": "m2hub_addons/__init__.py",
                               "sha256": hashlib.sha256(content).hexdigest()})
        self.write_manifest(value)
        with self.assertRaisesRegex(PackageError, "documentation only"):
            load_package(self.package)

    def test_discovery_exposes_invalid_item_without_hiding_good_package(self):
        broken = self.root / "broken"
        broken.mkdir()
        (broken / "addon.json").write_text("invalid", encoding="utf-8")
        packages, errors = discover_packages(self.root)
        self.assertIn("demo.markers", packages)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["status"], "invalid")

    def test_symlink_payload_escape_rejected_where_supported(self):
        outside = self.root / "outside.py"
        outside.write_bytes(b"VALUE = 1\n")
        link = self.package / "payload" / "linked.py"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Host does not permit unprivileged symbolic links")
        value = manifest()
        value["files"][0]["source"] = "linked.py"
        self.write_manifest(value)
        with self.assertRaises(PackageError):
            load_package(self.package)


if __name__ == "__main__":
    unittest.main()
