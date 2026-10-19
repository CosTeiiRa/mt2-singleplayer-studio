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

    def test_native_install_keeps_game_values_and_archives_custom_work(self):
        path = self.root / 'drops.txt'
        base, custom, incoming = b'scroll 50\nother 1\n', b'scroll 100\nother 1\n', b'scroll 80\nother 2\n'
        path.write_bytes(custom)
        self.studio.workspace.record_commit([(path, base, custom)], 'Scroll', 'backup')
        raw = package({'drops.txt': incoming, 'new-file.txt': b'new'})
        report = self.updates.stage(io.BytesIO(raw), len(raw), hashlib.sha256(raw).hexdigest())
        choice = report['files'][0]['choices'][0]
        saved, changes, rebased = self.studio.workspace.reconciliation({'id': report['id'], 'decisions': {choice['id']: 'keep'}})
        def native_fixture(args, **kwargs):
            archives = list((self.state / 'updates').glob('*/0.custom'))
            self.assertEqual(len(archives), 1)
            self.assertEqual(archives[0].read_bytes(), custom)
            path.write_bytes(incoming)
            (self.root / 'new-file.txt').write_bytes(b'new')
            result = Path(args[args.index('-ResultPath') + 1])
            result.write_text(json.dumps({'Backup': 'fixture-native-backup'}))
            return SimpleNamespace(returncode=0)
        with patch('protected_updates.subprocess.run', side_effect=native_fixture), patch.object(self.studio, 'write', side_effect=AssertionError('Studio must not rewrite game files after the updater')):
            self.updates._install(report['package'], saved, changes, rebased)
        self.assertEqual(self.updates.job['status'], 'succeeded')
        self.assertEqual(path.read_bytes(), incoming)
        self.assertEqual((self.root / 'new-file.txt').read_bytes(), b'new')
        self.assertTrue(self.studio.workspace.preference('nativeUpdatePending')['ready'])
        tracked = self.studio.workspace.tracked()[0]
        self.assertEqual((tracked['original'], tracked['custom'], tracked['expected']), (base, custom, incoming))
        self.assertEqual(self.studio.workspace.scan(include_deferred=False)['affectedFiles'], 0)
        # The update can be built immediately; custom work remains reviewable.
        self.studio.workspace = Workspace(self.studio)
        later = self.studio.workspace.scan()
        self.assertEqual(later['affectedFiles'], 1)
        self.assertTrue(later['files'][0]['deferred'])
        choice = later['files'][0]['choices'][0]
        _, restore, _ = self.studio.workspace.reconciliation({'id': later['id'], 'decisions': {choice['id']: 'keep'}})
        self.assertEqual(restore[path], b'scroll 100\nother 2\n')
        self.assertEqual(path.read_bytes(), incoming)
        archived = json.loads(next((self.state / 'updates').glob('*/manifest.json')).read_text('utf-8'))
        self.assertEqual(archived['policy'], 'game-first')
        self.assertEqual(archived['nativeBackup'], 'fixture-native-backup')

    def test_package_preserves_review_when_game_adopts_custom_and_leaves_absent_files_alone(self):
        supplied, absent = self.root / 'supplied.txt', self.root / 'absent.txt'
        for path in (supplied, absent):
            path.write_bytes(b'value 100\n')
            self.studio.workspace.record_commit([(path, b'value 50\n', path.read_bytes())], 'Custom', 'backup')
        # Even when upstream adopts our old value, retain the pending review
        # until the user explicitly accepts the new game baseline.
        raw = package({'supplied.txt': supplied.read_bytes()})
        report = self.updates.stage(io.BytesIO(raw), len(raw), hashlib.sha256(raw).hexdigest())
        self.assertEqual(report['priority'], 'game')
        self.assertEqual([row['path'] for row in report['files']], ['supplied.txt'])
        saved, changes, rebased = self.studio.workspace.reconciliation({'id': report['id']})
        def native_fixture(args, **kwargs):
            Path(args[args.index('-ResultPath') + 1]).write_text(json.dumps({'Backup': 'fixture'}))
            return SimpleNamespace(returncode=0)
        with patch('protected_updates.subprocess.run', side_effect=native_fixture):
            self.updates._install(report['package'], saved, changes, rebased)
        self.assertEqual(self.studio.workspace.deferred_paths(), {'supplied.txt'})
        later = self.studio.workspace.scan()
        self.assertEqual(later['files'][0]['choices'], [])
        _, changes, rebased = self.studio.workspace.reconciliation({'id': later['id']})
        self.assertEqual(changes, {})
        self.studio.workspace.record_commit([], 'Accept new game baseline', 'archived', {'reconciled': rebased})
        self.assertEqual([row['path'] for row in self.studio.workspace.tracked()], ['absent.txt'])
        self.assertEqual(absent.read_bytes(), b'value 100\n')

    def test_second_update_preserves_original_custom_work_for_later_merge(self):
        path = self.root / 'drops.txt'
        base, custom = b'item 50\nother 1\n', b'item 100\nother 1\n'
        path.write_bytes(custom)
        self.studio.workspace.record_commit([(path, base, custom)], 'Custom', 'backup')
        for value in (80, 90):
            incoming = ('item %s\nother 9\n' % value).encode()
            raw = package({'drops.txt': incoming})
            report = self.updates.stage(io.BytesIO(raw), len(raw), hashlib.sha256(raw).hexdigest())
            saved, changes, rebased = self.studio.workspace.reconciliation({'id': report['id']})
            def native_fixture(args, **kwargs):
                path.write_bytes(incoming)
                Path(args[args.index('-ResultPath') + 1]).write_text(json.dumps({'Backup': 'fixture'}))
                return SimpleNamespace(returncode=0)
            with patch('protected_updates.subprocess.run', side_effect=native_fixture):
                self.updates._install(report['package'], saved, changes, rebased)
            self.assertEqual(path.read_bytes(), incoming)
            tracked = self.studio.workspace.tracked()[0]
            self.assertEqual((tracked['original'], tracked['custom'], tracked['expected']), (base, custom, incoming))
        later = self.studio.workspace.scan()
        choice = later['files'][0]['choices'][0]
        _, changes, _ = self.studio.workspace.reconciliation({'id': later['id'], 'decisions': {choice['id']: 'keep'}})
        self.assertEqual(changes[path], b'item 100\nother 9\n')

    def test_no_custom_choice_is_required_and_stale_install_is_rejected(self):
        path = self.root / 'drops.txt'
        path.write_bytes(b'item 100\n')
        self.studio.workspace.record_commit([(path, b'item 50\n', path.read_bytes())], 'Custom', 'backup')
        raw = package({'drops.txt': b'item 80\n'})
        report = self.updates.stage(io.BytesIO(raw), len(raw), hashlib.sha256(raw).hexdigest())
        _, changes, _ = self.studio.workspace.reconciliation({'id': report['id']})
        self.assertEqual(changes[path], b'item 80\n')
        path.write_bytes(b'item 75\n')
        with self.assertRaisesRegex(ValueError, 'changed since this review'):
            self.updates.install({'id': report['id']})
