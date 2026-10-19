"""The integration helper must never apply to the normal client."""
from pathlib import Path
import tempfile
import unittest

from tools.check_merged_integration import exercise


class MergedIntegrationHelperTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / '.test-tmp'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'game/Klient'
        self.state = self.base / 'studio'
        self.fixture = self.state / 'addons/sandboxes/check/Klient'
        self.original = self.state / 'addons/sandboxes/original/Klient'
        for folder in (self.source, self.fixture, self.original):
            (folder / 'pack').mkdir(parents=True)
            for name in ('root.index', 'root.data'):
                (folder / 'pack' / name).write_bytes(b'original bytes')
        self.selected = self.original
        self.installed = set()
        self.pending = None
        self.applies = []
        self.redirect_plan = False
        self.fail_apply = False
        self.bootstrap = {'stateDir': str(self.state)}

    def request(self, path, body=None):
        if path == '/api/addons/state':
            normal = self.selected == self.source
            return {'state': {'source_path': str(self.source),
                'installation': {'path': str(self.selected), 'kind': 'installation' if normal else 'sandbox',
                                 'writable': True, 'profile_id': 'supported-runtime' if normal else None},
                'installed': sorted(self.installed), 'pending_plan': self.pending}}
        if path == '/api/addons/connect':
            self.selected = Path(body['path'])
            self.pending = None
            return {}
        if path == '/api/addons/sandbox':
            self.selected = self.fixture
            return {'path': str(self.fixture)}
        if path == '/api/addons/maps':
            return {'maps': ['map']}
        if path == '/api/addons/map?map=64':
            return {'map': {'regions': [{'source': 'map/boss.txt'}]}}
        if path.startswith('/api/file?id='):
            return {'id': 'map/boss.txt'}
        if path == '/api/workspace':
            return {'drafts': [], 'recent': []}
        if path == '/api/addons/plan':
            self.pending = {'id': 'plan-%s' % len(self.applies), 'can_apply': True, 'conflicts': []}
            self.action = body
            if self.redirect_plan:
                self.selected = self.source
            return {'plan': self.pending}
        if path == '/api/addons/apply':
            if self.fail_apply:
                raise ValueError('fixture apply failure')
            self.applies.append(self.selected)
            if self.action['action'] == 'install':
                self.installed.add(self.action['addon_id'])
            elif self.action['action'] == 'remove':
                self.installed.remove(self.action['addon_id'])
            self.pending = None
            return {}
        self.fail('Unexpected API request: ' + path)

    def test_supported_writable_normal_client_is_inspected_and_all_applies_stay_in_fixture(self):
        report = exercise(self.request, self.bootstrap)
        self.assertEqual(report['status'], 'passed')
        self.assertTrue(report['normal_client_support']['writable'])
        self.assertFalse(report['native_execution'])
        self.assertEqual(self.applies, [self.fixture] * 7)
        self.assertEqual(self.selected, self.original)

    def test_target_switch_after_plan_prevents_apply_to_normal_client(self):
        self.redirect_plan = True
        with self.assertRaisesRegex(ValueError, 'target changed'):
            exercise(self.request, self.bootstrap)
        self.assertFalse(self.applies)
        self.assertEqual(self.selected, self.original)
        self.assertEqual((self.source / 'pack/root.index').read_bytes(), b'original bytes')

    def test_failure_still_restores_the_original_connection(self):
        self.fail_apply = True
        with self.assertRaisesRegex(ValueError, 'fixture apply failure'):
            exercise(self.request, self.bootstrap)
        self.assertEqual(self.selected, self.original)
        self.assertFalse(self.applies)

    def test_reused_fixture_cannot_contain_a_playable_client(self):
        (self.fixture / 'metin2client.exe').write_bytes(b'not allowed')
        with self.assertRaisesRegex(ValueError, 'non-playable'):
            exercise(self.request, self.bootstrap, self.fixture)
        self.assertFalse(self.applies)
        self.assertEqual(self.selected, self.original)


if __name__ == '__main__':
    unittest.main()
