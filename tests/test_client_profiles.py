"""Exact runtime identities select integration support, never version labels."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from addonhub import client_adapter


class RecordedClientProfilesTests(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parents[1] / '.test-tmp'
        test_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'profiles').mkdir()

    def write(self, name, **changes):
        value = {'schema_version': 1, 'id': name, 'executable_sha256': 'a' * 64, **changes}
        (self.root / 'profiles' / (name + '.json')).write_text(json.dumps(value), 'utf-8')
        return value

    def test_bundled_profiles_are_unique_exact_smoke_validated_identities(self):
        paths = sorted((client_adapter.PROJECT / 'profiles').glob('*.json'))
        self.assertGreaterEqual(len(paths), 2)
        hashes, identities = set(), set()
        for path in paths:
            profile = json.loads(path.read_text('utf-8'))
            digest = profile['executable_sha256']
            self.assertRegex(digest, r'^[a-f0-9]{64}$')
            self.assertNotIn(digest, hashes)
            self.assertNotIn(profile['id'], identities)
            hashes.add(digest)
            identities.add(profile['id'])
            self.assertEqual(client_adapter.recorded_profile(digest), profile)
            for field in ('native_startup_and_import', 'native_widget_construction',
                          'actual_pack_roundtrip', 'exact_uninstall_restoration'):
                self.assertIs(profile['validation'][field], True)
            self.assertIs(profile['validation']['interactive_gameplay'], False)
            self.assertTrue(profile['limits'])

    def test_unknown_hash_cannot_be_admitted_by_version_or_profile_name(self):
        self.write('client-2.0.114', client_version='2.0.114')
        with patch.object(client_adapter, 'PROJECT', self.root):
            self.assertIsNotNone(client_adapter.recorded_profile('a' * 64))
            for value in (None, '', '2.0.114', 'client-2.0.114', 'b' * 64):
                self.assertIsNone(client_adapter.recorded_profile(value))

    def test_ambiguous_executable_records_fail_closed(self):
        self.write('first')
        self.write('second')
        with patch.object(client_adapter, 'PROJECT', self.root):
            self.assertIsNone(client_adapter.recorded_profile('a' * 64))

    def test_damaged_or_unsupported_profile_does_not_hide_another_valid_profile(self):
        expected = self.write('supported')
        self.write('future', schema_version=999)
        (self.root / 'profiles/broken.json').write_text('{', 'utf-8')
        (self.root / 'profiles/invalid.json').write_text('[]', 'utf-8')
        with patch.object(client_adapter, 'PROJECT', self.root):
            self.assertEqual(client_adapter.recorded_profile('a' * 64), expected)


if __name__ == '__main__':
    unittest.main()
