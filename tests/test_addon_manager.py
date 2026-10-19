import ast
import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from metin2_studio.addons.hubcore.manager import Manager


def encode(files):
    return json.dumps({name: base64.b64encode(content).decode("ascii") for name, content in sorted(files.items())}, sort_keys=True).encode("ascii")


class FakeBackend:
    """Two-file pack adapter, exercising actual physical file transactions."""
    def __init__(self, path, writable=True):
        self.target_root = Path(path)
        self.writable = writable
        self.prepare_calls = 0

    def profile(self):
        return {"id": "test-profile", "name": "Test sandbox", "client_version": "2.0.112", "server_version": "2.2.108",
                "kind": "sandbox" if self.writable else "installation", "writable": self.writable, "fingerprint": "test"}

    def snapshot(self):
        return {name: base64.b64decode(content) for name, content in json.loads((self.target_root / "root.data").read_bytes()).items()}

    def physical_snapshot(self):
        return {name: (self.target_root / name).read_bytes() for name in ("root.data", "root.index") if (self.target_root / name).exists()}

    def prepare(self, logical_files, staging_dir):
        self.prepare_calls += 1
        data = encode(logical_files)
        return {"root.data": data, "root.index": hashlib.sha256(data).hexdigest().encode("ascii")}

    def check_writable(self):
        if not self.writable:
            raise ValueError("Live installation is read-only")


class ManagerTests(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).resolve().parents[1] / ".test-tmp"
        temporary_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temporary_root)
        self.root = Path(self.temp.name)
        self.target = self.root / "sandbox"
        self.target.mkdir()
        self.catalog = self.root / "catalog"
        self.catalog.mkdir()
        self.backend = FakeBackend(self.target)
        self.original_logical = {"ui.py": b"# game\n", "game.py": b"# original\n"}
        self.set_target(self.original_logical)
        self.original_physical = self.backend.physical_snapshot()
        self.make_package("demo.markers", "markers")
        self.make_package("demo.legend", "legend")
        self.manager = Manager(self.root / "hub-state", self.catalog, lambda path: self.backend)
        self.manager.connect(self.target)

    def tearDown(self):
        self.temp.cleanup()

    def set_target(self, files):
        for name, content in self.backend.prepare(files, self.root / "unused").items():
            (self.target / name).write_bytes(content)

    def make_package(self, addon_id, module, content=None, requires=None, conflicts=None, extra_files=None, version="1.0.0", compatibility=None):
        directory = self.catalog / addon_id
        payload = directory / "payload"
        payload.mkdir(parents=True, exist_ok=True)
        data = {"m2hub_addons/" + module + ".py": content if content is not None else ("NAME = %r\n" % module).encode("ascii"),
                "m2hub_addons/__init__.py": b""}
        data.update(extra_files or {})
        files = []
        for index, (target, content) in enumerate(data.items()):
            source = "%d.bin" % index
            (payload / source).write_bytes(content)
            files.append({"source": source, "target": target, "sha256": hashlib.sha256(content).hexdigest()})
        value = {"schema_version": 1, "id": addon_id, "name": module, "version": version, "description": "Test add-on",
                 "author": "Tests", "category": "Maps", "kind": "client-python", "entry": "m2hub_addons." + module,
                 "requires": requires or [], "conflicts": conflicts or [], "capabilities": ["map.markers"], "files": files,
                 "settings_schema": {"type": "object", "properties": {"show_labels": {"type": "boolean", "default": True}}}}
        if compatibility is not None:
            value["compatibility"] = compatibility
        (directory / "addon.json").write_text(json.dumps(value), encoding="utf-8")
        return directory

    def apply(self, addon_id, action="install"):
        plan = self.manager.plan(addon_id, action)
        self.assertTrue(plan["can_apply"], plan["conflicts"])
        return self.manager.apply(plan["id"])

    def test_inspection_and_plan_do_not_capture_baseline_or_write_target(self):
        self.manager.state()
        self.manager.catalog()
        self.manager.plan("demo.markers")
        self.assertFalse(self.manager._state_path.exists())
        self.assertEqual(self.backend.physical_snapshot(), self.original_physical)

    def updated_game(self):
        self.backend.is_clean_game_baseline = lambda files: not any(name == 'm2hub_config.py' or name.startswith('m2hub_addons/') for name in files)
        fresh = {'ui.py': b'# new game UI\n', 'game.py': b'# new upstream lifecycle\n', 'new.py': b'# upstream addition\n'}
        self.set_target(fresh)
        # Different physical encoding of a valid logical pack must also survive removal.
        (self.target / 'root.data').write_bytes((self.target / 'root.data').read_bytes() + b'\n')
        return fresh, self.backend.physical_snapshot()

    def test_game_update_reapply_preserves_new_baseline_settings_and_exact_removal(self):
        self.apply('demo.markers')
        self.apply('demo.legend')
        self.manager.apply(self.manager.plan('demo.markers', 'configure', {'show_labels': False})['id'])
        fresh, physical = self.updated_game()
        self.assertTrue(self.manager.state()['game_update']['reapply_available'])
        self.assertEqual(self.backend.physical_snapshot(), physical)
        plan = self.manager.plan('demo.markers', 'reapply')
        self.assertTrue(plan['can_apply'], plan['conflicts'])
        self.assertTrue(plan['game_update']['detected'])
        self.assertEqual(self.backend.physical_snapshot(), physical)
        self.manager.apply(plan['id'])
        self.assertIsNone(self.manager.state()['game_update'])
        for name, content in fresh.items():
            self.assertEqual(self.backend.snapshot()[name], content)
        self.assertFalse(next(row for row in self.manager.state()['installed'] if row['id'] == 'demo.markers')['settings']['show_labels'])
        self.apply('demo.markers', 'remove')
        self.apply('demo.legend', 'remove')
        self.assertEqual(self.backend.physical_snapshot(), physical)

    def test_game_update_during_review_invalidates_reapply_without_writes(self):
        self.apply('demo.markers')
        self.updated_game()
        plan = self.manager.plan('demo.markers', 'reapply')
        self.set_target({'ui.py': b'# even newer game\n'})
        physical = self.backend.physical_snapshot()
        with self.assertRaisesRegex(ValueError, 'files changed after review'):
            self.manager.apply(plan['id'])
        self.assertEqual(self.backend.physical_snapshot(), physical)

    def test_reapply_failure_restores_updated_game_instead_of_old_addon_packs(self):
        self.apply('demo.markers')
        _, physical = self.updated_game()
        original_write = self.manager._write_physical
        calls = []
        def fail_once(name, content):
            original_write(name, content)
            calls.append(name)
            if len(calls) == 1:
                raise OSError('reapply I/O failure')
        self.manager._write_physical = fail_once
        plan = self.manager.plan('demo.markers', 'reapply')
        with self.assertRaisesRegex(ValueError, 'previous files were restored'):
            self.manager.apply(plan['id'])
        self.assertEqual(self.backend.physical_snapshot(), physical)
        self.assertTrue(self.manager.state()['game_update']['detected'])

    def test_update_after_full_uninstall_is_baseline_for_next_install(self):
        self.apply('demo.markers')
        self.apply('demo.markers', 'remove')
        _, physical = self.updated_game()
        self.apply('demo.legend')
        self.apply('demo.legend', 'remove')
        self.assertEqual(self.backend.physical_snapshot(), physical)

    def test_partial_external_update_with_addon_files_stays_blocked(self):
        self.apply('demo.markers')
        self.backend.is_clean_game_baseline = lambda files: 'm2hub_config.py' not in files
        files = self.backend.snapshot()
        files['ui.py'] = b'# external edit with remaining Hub files\n'
        self.set_target(files)
        self.assertIsNone(self.manager.state()['game_update'])
        plan = self.manager.plan('demo.markers', 'disable')
        self.assertFalse(plan['can_apply'])
        self.assertTrue(any('External changes' in conflict for conflict in plan['conflicts']))

    def test_compatibility_uses_shared_client_profile_not_installation_identity(self):
        original_profile = self.backend.profile
        self.backend.profile = lambda: dict(original_profile(), profile_id="native-client-profile")
        self.make_package("demo.markers", "markers", compatibility={"profile_ids": ["native-client-profile"]})
        self.assertTrue(self.manager.plan("demo.markers")["can_apply"])
        self.make_package("demo.markers", "markers", compatibility={"profile_ids": ["different-client-profile"]})
        plan = self.manager.plan("demo.markers")
        self.assertTrue(plan["can_apply"])
        self.assertTrue(any('client profile' in warning and 'unverified' in warning for warning in plan['warnings']))

    def test_two_addons_coexist_and_uninstall_independently_exact_baseline(self):
        self.apply("demo.markers")
        self.apply("demo.legend")
        files = self.backend.snapshot()
        self.assertIn("m2hub_addons/markers.py", files)
        self.assertIn("m2hub_addons/legend.py", files)
        self.apply("demo.markers", "remove")
        files = self.backend.snapshot()
        self.assertNotIn("m2hub_addons/markers.py", files)
        self.assertIn("m2hub_addons/legend.py", files)
        self.apply("demo.legend", "remove")
        self.assertEqual(self.backend.physical_snapshot(), self.original_physical)
        self.assertEqual(self.manager.state()["installed"], [])

    def test_disable_and_enable_preserve_payload_and_settings(self):
        self.apply("demo.markers")
        self.apply("demo.markers", "disable")
        files = self.backend.snapshot()
        self.assertIn("m2hub_addons/markers.py", files)
        configuration = {}
        exec(files["m2hub_config.py"], configuration)
        self.assertEqual(configuration["ADDONS"], [])
        self.apply("demo.markers", "enable")
        exec(self.backend.snapshot()["m2hub_config.py"], configuration)
        self.assertEqual(configuration["ADDONS"][0]["settings"], {"show_labels": True})

    def test_configure_is_reviewed_persistent_and_type_checked(self):
        self.apply("demo.markers")
        before = self.backend.physical_snapshot()
        plan = self.manager.plan("demo.markers", "configure", {"show_labels": False})
        self.assertEqual(self.backend.physical_snapshot(), before)
        self.manager.apply(plan["id"])
        configuration = {}
        exec(self.backend.snapshot()["m2hub_config.py"], configuration)
        self.assertEqual(configuration["ADDONS"][0]["settings"], {"show_labels": False})
        restarted = Manager(self.root / "hub-state", self.catalog, lambda path: self.backend)
        self.assertFalse(restarted.state()["installed"][0]["settings"]["show_labels"])
        with self.assertRaisesRegex(ValueError, "type boolean"):
            restarted.plan("demo.markers", "configure", {"show_labels": "false"})
        with self.assertRaisesRegex(ValueError, "Unknown setting"):
            restarted.plan("demo.markers", "configure", {"execute": "anything"})

    def test_virtual_pack_names_are_preserved_without_becoming_physical_paths(self):
        logical = dict(self.original_logical, **{"d:/ymir work/ui/maps/a.sub": b"virtual resource"})
        self.set_target(logical)
        original = self.backend.physical_snapshot()
        self.apply("demo.markers")
        self.apply("demo.markers", "remove")
        self.assertEqual(self.backend.physical_snapshot(), original)
        self.assertFalse((self.root / "d:").exists())

    def test_install_update_remove_uses_immutable_installed_payload(self):
        self.apply("demo.markers")
        self.apply("demo.legend")
        self.make_package("demo.markers", "markers", content=b"NEW = True\n", version="2.0.0")
        self.apply("demo.legend", "remove")
        self.assertNotEqual(self.backend.snapshot()["m2hub_addons/markers.py"], b"NEW = True\n")
        self.apply("demo.markers", "update")
        self.assertEqual(self.backend.snapshot()["m2hub_addons/markers.py"], b"NEW = True\n")
        self.assertEqual(self.manager.state()["installed"][0]["version"], "2.0.0")

    def test_shared_file_ownership_conflict(self):
        shared = {"m2hub_addons/shared.py": b"shared\n"}
        self.make_package("demo.markers", "markers", extra_files=shared)
        self.make_package("demo.legend", "legend", extra_files=shared)
        self.apply("demo.markers")
        plan = self.manager.plan("demo.legend")
        self.assertFalse(plan["can_apply"])
        self.assertTrue(any("both own" in x for x in plan["conflicts"]))

    def test_identical_shared_namespace_initializers_do_not_conflict(self):
        shared = {"m2hub_addons/maps/__init__.py": b"# shared namespace\n"}
        self.make_package("demo.markers", "markers", extra_files=shared)
        self.make_package("demo.legend", "legend", extra_files=shared)
        self.apply("demo.markers")
        self.apply("demo.legend")
        self.apply("demo.markers", "remove")
        self.assertEqual(self.backend.snapshot()["m2hub_addons/maps/__init__.py"], shared["m2hub_addons/maps/__init__.py"])
        self.apply("demo.legend", "remove")
        self.assertEqual(self.backend.physical_snapshot(), self.original_physical)

    def test_existing_common_namespace_initializer_is_preserved(self):
        initializer = b"# original namespace\n"
        self.set_target(dict(self.original_logical, **{"m2hub_addons/__init__.py": initializer}))
        original = self.backend.physical_snapshot()
        self.apply("demo.markers")
        self.apply("demo.legend")
        self.assertEqual(self.backend.snapshot()["m2hub_addons/__init__.py"], initializer)
        self.apply("demo.markers", "remove")
        self.apply("demo.legend", "remove")
        self.assertEqual(self.backend.physical_snapshot(), original)

    def test_unknown_baseline_addon_file_is_not_overwritten(self):
        self.set_target(dict(self.original_logical, **{"m2hub_addons/markers.py": b"manual"}))
        plan = self.manager.plan("demo.markers")
        self.assertFalse(plan["can_apply"])
        self.assertTrue(any("unknown ownership" in x for x in plan["conflicts"]))

    def test_external_manual_drift_blocks_plan(self):
        self.apply("demo.markers")
        files = self.backend.snapshot()
        files["ui.py"] = b"# my edit\n"
        self.set_target(files)
        physical = self.backend.physical_snapshot()
        plan = self.manager.plan("demo.markers", "remove")
        self.assertFalse(plan["can_apply"])
        with self.assertRaisesRegex(ValueError, "External changes"):
            self.manager.apply(plan["id"])
        self.assertEqual(self.backend.physical_snapshot(), physical)

    def test_edit_after_review_invalidates_plan_before_writes(self):
        plan = self.manager.plan("demo.markers")
        self.set_target(dict(self.original_logical, **{"manual.py": b"edit"}))
        physical = self.backend.physical_snapshot()
        with self.assertRaisesRegex(ValueError, "changed after review"):
            self.manager.apply(plan["id"])
        self.assertEqual(self.backend.physical_snapshot(), physical)
        self.assertIsNone(self.manager.state()["pending_plan"])

    def test_changed_catalog_release_invalidates_reviewed_plan(self):
        plan = self.manager.plan("demo.markers")
        self.make_package("demo.markers", "markers", content=b"changed\n", version="2.0.0")
        with self.assertRaisesRegex(ValueError, "release changed"):
            self.manager.apply(plan["id"])
        self.assertEqual(self.backend.physical_snapshot(), self.original_physical)

    def test_new_plan_invalidates_previous_plan(self):
        old = self.manager.plan("demo.markers")
        new = self.manager.plan("demo.legend")
        with self.assertRaisesRegex(ValueError, "no longer current"):
            self.manager.apply(old["id"])
        self.manager.apply(new["id"])
        with self.assertRaisesRegex(ValueError, "no longer current"):
            self.manager.apply(new["id"])

    def test_dependency_install_disable_remove_checks(self):
        self.make_package("demo.legend", "legend", requires=["demo.markers"])
        self.assertFalse(self.manager.plan("demo.legend")["can_apply"])
        self.apply("demo.markers")
        self.apply("demo.legend")
        self.assertFalse(self.manager.plan("demo.markers", "remove")["can_apply"])
        self.assertFalse(self.manager.plan("demo.markers", "disable")["can_apply"])
        self.apply("demo.legend", "disable")
        self.apply("demo.markers", "disable")
        self.assertFalse(self.manager.plan("demo.legend", "enable")["can_apply"])

    def test_declared_conflicts_are_symmetric(self):
        self.make_package("demo.markers", "markers", conflicts=["demo.legend"])
        self.apply("demo.markers")
        self.assertFalse(self.manager.plan("demo.legend")["can_apply"])

    def test_unlisted_versions_warn_but_allow_reviewed_install_and_removal(self):
        self.make_package("demo.markers", "markers", compatibility={"client_versions": ["9.9.9"], "server_versions": ["9.9.9"]})
        plan = self.manager.plan("demo.markers")
        self.assertTrue(plan["can_apply"], plan['conflicts'])
        self.assertEqual(plan['conflicts'], [])
        self.assertTrue(any('2.0.112' in warning and '9.9.9' in warning and 'unverified' in warning for warning in plan['warnings']))
        item = next(row for row in self.manager.catalog()['items'] if row['id'] == 'demo.markers')
        self.assertEqual(item['compatibility_status'], 'unverified')
        self.assertEqual(item['status'], 'available')
        self.manager.apply(plan['id'])
        self.assertEqual(self.manager.state()['installed'][0]['compatibility_status'], 'unverified')
        self.apply('demo.markers', 'disable')
        self.apply('demo.markers', 'enable')
        self.apply('demo.markers', 'remove')
        self.assertEqual(self.backend.physical_snapshot(), self.original_physical)

    def test_game_update_does_not_trap_unverified_addons_during_disable_or_removal(self):
        for addon_id, module in (('demo.markers', 'markers'), ('demo.legend', 'legend')):
            self.make_package(addon_id, module, compatibility={'server_versions': ['2.2.108']})
            self.apply(addon_id)
        original_profile = self.backend.profile
        self.backend.profile = lambda: dict(original_profile(), server_version='2.2.109')
        self.assertTrue(all(row['compatibility_status'] == 'unverified' for row in self.manager.state()['installed']))
        self.apply('demo.markers', 'disable')
        self.apply('demo.markers', 'remove')
        self.apply('demo.legend', 'remove')
        self.assertEqual(self.backend.physical_snapshot(), self.original_physical)

    def test_declared_match_is_not_presented_as_independent_verification(self):
        self.make_package('demo.markers', 'markers', compatibility={'client_versions': ['2.0.112']})
        item = next(row for row in self.manager.catalog()['items'] if row['id'] == 'demo.markers')
        self.assertEqual(item['compatibility_status'], 'declared')
        self.assertFalse(item['tested_in_game'])
        self.assertEqual(item['warnings'], [])
        self.make_package('demo.markers', 'markers', compatibility={'client_versions': ['2.0.112'], 'experimental': True})
        item = next(row for row in self.manager.catalog()['items'] if row['id'] == 'demo.markers')
        self.assertEqual(item['compatibility_status'], 'unverified')

    def test_version_change_after_review_requires_fresh_warning_review(self):
        self.make_package('demo.markers', 'markers', compatibility={'server_versions': ['2.2.108']})
        plan = self.manager.plan('demo.markers')
        original_profile = self.backend.profile
        self.backend.profile = lambda: dict(original_profile(), server_version='2.2.109')
        with self.assertRaisesRegex(ValueError, 'changed.*review'):
            self.manager.apply(plan['id'])
        self.assertEqual(self.backend.physical_snapshot(), self.original_physical)
        updated = self.manager.plan('demo.markers')
        self.assertTrue(updated['can_apply'])
        self.assertTrue(any('2.2.109' in warning for warning in updated['warnings']))
        self.manager.apply(updated['id'])

    def test_read_only_target_can_be_inspected_but_cannot_apply(self):
        self.backend.writable = False
        plan = self.manager.plan("demo.markers")
        self.assertFalse(plan["can_apply"])
        with self.assertRaises(ValueError):
            self.manager.apply(plan["id"])
        self.assertEqual(self.backend.physical_snapshot(), self.original_physical)

    def test_crash_mid_pack_pair_recovers_after_restart(self):
        original_write = self.manager._write_physical
        calls = []
        def interrupted(name, content):
            original_write(name, content)
            calls.append(name)
            if len(calls) == 1:
                raise KeyboardInterrupt("simulated process stop")
        self.manager._write_physical = interrupted
        plan = self.manager.plan("demo.markers")
        with self.assertRaises(KeyboardInterrupt):
            self.manager.apply(plan["id"])
        self.assertNotEqual(self.backend.physical_snapshot(), self.original_physical)
        restarted = Manager(self.root / "hub-state", self.catalog, lambda path: self.backend)
        self.assertIsNotNone(restarted.state()["recovery"])
        self.assertEqual(restarted.recover()["status"], "restored")
        self.assertEqual(self.backend.physical_snapshot(), self.original_physical)
        self.assertEqual(restarted.state()["installed"], [])

    def test_regular_write_error_automatically_restores_files(self):
        original_write = self.manager._write_physical
        calls = []
        def fail_once(name, content):
            original_write(name, content)
            calls.append(name)
            if len(calls) == 1:
                raise OSError("simulated I/O error")
        self.manager._write_physical = fail_once
        plan = self.manager.plan("demo.markers")
        with self.assertRaisesRegex(ValueError, "previous files were restored"):
            self.manager.apply(plan["id"])
        self.assertEqual(self.backend.physical_snapshot(), self.original_physical)
        self.assertIsNone(self.manager.state()["recovery"])

    def test_recovery_preserves_external_edit(self):
        original_write = self.manager._write_physical
        def interrupted(name, content):
            original_write(name, content)
            raise KeyboardInterrupt("stop")
        self.manager._write_physical = interrupted
        plan = self.manager.plan("demo.markers")
        with self.assertRaises(KeyboardInterrupt):
            self.manager.apply(plan["id"])
        staged_data = (self.target / "root.data").read_bytes()
        # This is the second operation. Recovery must validate it before it
        # restores the first operation, which still contains staged bytes.
        (self.target / "root.index").write_bytes(b"outside edit")
        restarted = Manager(self.root / "hub-state", self.catalog, lambda path: self.backend)
        with self.assertRaisesRegex(ValueError, "unexpected changes"):
            restarted.recover()
        self.assertEqual((self.target / "root.index").read_bytes(), b"outside edit")
        self.assertEqual((self.target / "root.data").read_bytes(), staged_data)
        self.assertIsNotNone(restarted.state()["recovery"])

    def test_interruption_after_state_commit_confirms_installation(self):
        def interrupted_history(event):
            raise KeyboardInterrupt("process ended after atomic state commit")
        self.manager._record_history = interrupted_history
        plan = self.manager.plan("demo.markers")
        with self.assertRaises(KeyboardInterrupt):
            self.manager.apply(plan["id"])
        physical = self.backend.physical_snapshot()
        restarted = Manager(self.root / "hub-state", self.catalog, lambda path: self.backend)
        self.assertEqual(restarted.recover()["status"], "committed")
        self.assertEqual(self.backend.physical_snapshot(), physical)
        self.assertEqual([item["id"] for item in restarted.state()["installed"]], ["demo.markers"])
        self.assertIsNone(restarted.state()["recovery"])

    def test_physical_backups_and_history_retained(self):
        self.apply("demo.markers")
        history = self.manager.history()
        self.assertEqual(history[0]["status"], "success")
        backup = Path(history[0]["backup_directory"])
        self.assertTrue(backup.is_dir())
        self.assertEqual(len(list(backup.iterdir())), 2)
        self.assertEqual({x.read_bytes() for x in backup.iterdir()}, set(self.original_physical.values()))

    def test_backend_runtime_injection_is_included_in_recorded_drift_hashes(self):
        prepare = self.backend.prepare
        def inject(logical_files, staging_dir):
            content = dict(logical_files)
            if "m2hub_config.py" in content:
                content["m2hub_runtime.py"] = b"# managed runtime\n"
                content["ui.py"] += b"# bootstrap\n"
            return prepare(content, staging_dir)
        self.backend.prepare = inject
        self.apply("demo.markers")
        self.apply("demo.legend")
        self.apply("demo.markers", "remove")
        self.apply("demo.legend", "remove")
        self.assertEqual(self.backend.physical_snapshot(), self.original_physical)

    def test_backend_preview_shows_generated_files_without_false_removals(self):
        prepare = self.backend.prepare
        def preview(logical_files):
            content = dict(logical_files)
            if "m2hub_config.py" in content:
                content["m2hub_generated.py"] = b"# generated shared framework\n"
                content["ui.py"] += b"# bootstrap\n"
            return content
        self.backend.preview = preview
        self.backend.prepare = lambda files, staging: prepare(preview(files), staging)
        first = self.manager.plan("demo.markers")
        generated = [item for item in first["changes"] if item["path"] == "m2hub_generated.py"]
        self.assertEqual(len(generated), 1)
        self.assertTrue(generated[0]["generated"])
        self.manager.apply(first["id"])
        second = self.manager.plan("demo.legend")
        self.assertEqual(second["preview_kind"], "backend")
        self.assertFalse(any(item["path"] in ("ui.py", "m2hub_generated.py") for item in second["changes"]))
        self.manager.apply(second["id"])
        removal = self.manager.plan("demo.markers", "remove")
        self.assertFalse(any(item["path"] == "m2hub_generated.py" for item in removal["changes"]))

    def test_generated_source_change_invalidates_previewed_plan(self):
        source = {"data": b"first"}
        self.backend.preview = lambda files: dict(files, generated=source["data"])
        plan = self.manager.plan("demo.markers")
        source["data"] = b"changed after review"
        with self.assertRaisesRegex(ValueError, "source data changed after review"):
            self.manager.apply(plan["id"])
        self.assertEqual(self.backend.physical_snapshot(), self.original_physical)


if __name__ == "__main__":
    unittest.main()
