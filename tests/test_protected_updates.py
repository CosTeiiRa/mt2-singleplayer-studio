import hashlib
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protected_updates import ProtectedUpdates, package_members
from workspace import Workspace


def package(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('VERSION', b'2.2.999\n')
        for name, raw in files.items():
            archive.writestr(name, raw)
    return output.getvalue()


class ProtectedUpdateTests(unittest.TestCase):
    def setUp(self):
        self.test_runs = Path(__file__).resolve().parents[1] / 'data' / 'test-runs'
        self.test_runs.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.test_runs)
        self.root = Path(self.temp.name) / 'game'
        self.state = Path(self.temp.name) / 'state'
        self.root.mkdir()
        self.state.mkdir()
        self.studio = SimpleNamespace(root=self.root, state=self.state, app=Path(__file__).resolve().parents[1], settings_schema={}, lock=threading.RLock(), job={'status': 'idle'})
        self.studio.safe = lambda path: Path(path).resolve() if Path(path).resolve().is_relative_to(self.root) else self.fail('Unsafe path')
        self.studio.write = lambda path, raw: path.write_bytes(raw) if raw is not None else path.unlink(missing_ok=True)
        self.studio.workspace = Workspace(self.studio)
        self.updates = ProtectedUpdates(self.studio)

    def tearDown(self):
        assert Path(self.temp.name).resolve().is_relative_to(self.test_runs.resolve())
        self.temp.cleanup()

    def test_preview_only_custom_conflict_and_does_not_install_other_files(self):
        path = self.root / 'drops.txt'
        base, custom = b'scroll 50\nother 1\n', b'scroll 100\nother 1\n'
        path.write_bytes(custom)
        self.studio.workspace.record_commit([(path, base, custom)], 'Scroll', 'backup')
        raw = package({'drops.txt': b'scroll 80\nother 2\n', 'new-file.txt': b'new'})
        report = self.updates.stage(io.BytesIO(raw), len(raw), hashlib.sha256(raw).hexdigest())
        self.assertEqual(report['affectedFiles'], 1)
        self.assertEqual(report['conflicts'], 1)
        self.assertEqual(report['files'][0]['choices'][0]['incoming'], '80')
        self.assertTrue(report['package']['verified'])
        self.assertEqual(path.read_bytes(), custom)
        self.assertFalse((self.root / 'new-file.txt').exists())

    def test_wrong_checksum_tampered_package_and_unverified_install_are_rejected(self):
        raw = package({'a.txt': b'new'})
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            self.updates.stage(io.BytesIO(raw), len(raw), '0' * 64)
        report = self.updates.stage(io.BytesIO(raw), len(raw))
        with self.assertRaisesRegex(ValueError, 'requires the expected SHA-256'):
            self.updates.install({'id': report['id'], 'decisions': {}})
        (self.updates.folder / (report['package']['id'] + '.zip')).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'staged package changed'):
            self.updates.preview(report['package']['id'])

    def test_unsafe_windows_paths_and_aliases_are_rejected_before_install(self):
        for name in ('../outside', '/absolute', 'C:/escape', 'folder\\escape', './alias', 'a//alias', 'a/CON.txt', 'a/file.txt.', 'a/file:stream'):
            with self.subTest(name=name):
                raw = package({name: b'bad'})
                if '\\' in name:
                    raw = raw.replace(name.replace('\\', '/').encode(), name.encode())
                with self.assertRaisesRegex(ValueError, 'unsafe path'):
                    self.updates.stage(io.BytesIO(raw), len(raw))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_duplicate_case_symlinks_and_oversized_version_are_rejected(self):
        raw = package({'A.txt': b'a', 'a.txt': b'b'})
        with self.assertRaisesRegex(ValueError, 'case-colliding'):
            self.updates.stage(io.BytesIO(raw), len(raw))
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('VERSION', '1')
            link = zipfile.ZipInfo('linked')
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, 'target')
        with self.assertRaisesRegex(ValueError, 'Linked'):
            self.updates.stage(io.BytesIO(output.getvalue()), len(output.getvalue()))

    def test_protected_installation_rejects_ordinary_update(self):
        (self.root / 'linux-port').mkdir()
        (self.root / 'linux-port/PROTECTED').write_text('protected')
        raw = package({'a.txt': b'new'})
        with self.assertRaisesRegex(ValueError, 'requires a protected'):
            self.updates.stage(io.BytesIO(raw), len(raw))

    def test_native_install_receipt_restores_reviewed_value_and_keeps_other_update(self):
        path = self.root / 'drops.txt'
        base, custom, incoming = b'scroll 50\nother 1\n', b'scroll 100\nother 1\n', b'scroll 80\nother 2\n'
        path.write_bytes(custom)
        self.studio.workspace.record_commit([(path, base, custom)], 'Scroll', 'backup')
        raw = package({'drops.txt': incoming, 'new-file.txt': b'new'})
        report = self.updates.stage(io.BytesIO(raw), len(raw), hashlib.sha256(raw).hexdigest())
        choice = report['files'][0]['choices'][0]
        saved, changes, rebased = self.studio.workspace.reconciliation({'id': report['id'], 'decisions': {choice['id']: 'keep'}})
        def native_fixture(args, **kwargs):
            path.write_bytes(incoming)
            (self.root / 'new-file.txt').write_bytes(b'new')
            result = Path(args[args.index('-ResultPath') + 1])
            result.write_text(json.dumps({'Backup': 'fixture-native-backup'}))
            return SimpleNamespace(returncode=0)
        with patch('protected_updates.subprocess.run', side_effect=native_fixture):
            self.updates._install(report['package'], saved, changes, rebased)
        self.assertEqual(self.updates.job['status'], 'succeeded')
        self.assertEqual(path.read_bytes(), b'scroll 100\nother 2\n')
        self.assertEqual((self.root / 'new-file.txt').read_bytes(), b'new')
        self.assertTrue(self.studio.workspace.preference('nativeUpdatePending')['ready'])
        tracked = self.studio.workspace.tracked()[0]
        self.assertEqual(tracked['original'], incoming)
        self.assertEqual(self.studio.workspace.scan()['affectedFiles'], 0)
