"""Manual update notices from cached metadata; discovery and reading never download."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from metin2_studio.addons.artifacts import build_artifact
from metin2_studio.addons.repositories import RepositoryStore
from metin2_studio.addons.transport import HTTPStatusError
from metin2_studio.addons.updates import update_notices
from tests.github_fixture import ADDON_ID, API, URL, GitHubFixture

PROJECT = Path(__file__).resolve().parents[1]
A, B, C = 'a' * 40, 'b' * 40, 'c' * 40


class UpdateNoticeTests(unittest.TestCase):
    def setUp(self):
        scratch = PROJECT / '.test-tmp'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temp.name)
        self.fetch = GitHubFixture(self.root / 'creator')
        self.fetch.add('1.0.0', A)
        self.store = RepositoryStore(self.root / 'state', PROJECT / 'src/metin2_studio/addons/catalog', self.fetch)
        self.repo = self.store.add(URL)
        self.select('1.0.0')
        self.installed = [self.store.packages()[0][ADDON_ID].metadata()]

    def tearDown(self):
        self.temp.cleanup()

    def select(self, version):
        review = self.store.review(self.repo, ADDON_ID, version)
        return self.store.download(review['id'])

    def notices(self):
        catalog = []
        for package in self.store.packages()[0].values():
            item = package.metadata()
            item['update_available'] = item['id'] == ADDON_ID and item['package_digest'] != self.installed[0]['package_digest']
            catalog.append(item)
        return update_notices(self.installed, self.store.offers(self.installed), catalog)

    def test_check_and_cached_changelog_do_not_fetch_archives_or_change_selections(self):
        before = copy.deepcopy(self.store._state()['active'])
        self.fetch.add('1.1.0', B)
        self.fetch.add('1.2.0', C)
        self.fetch.releases[-1]['body'] = 'New labels\n<script>literal author text</script>'
        archive_count = sum('codeload.github.com' in url for url in self.fetch.calls)
        self.assertEqual(self.notices(), [])  # A publication alone never triggers a network request.
        self.store.refresh(self.repo)
        count, fingerprint = len(self.fetch.calls), self.store.fingerprint()
        row = self.notices()[0]
        self.assertEqual([change['version'] for change in row['changes']], ['1.2.0', '1.1.0'])
        self.assertIn('<script>', row['changes'][0]['release_notes'])
        self.assertFalse(row['download_ready'])
        self.assertEqual(row['installed_version'], '1.0.0')
        self.assertEqual(row['available_version'], '1.2.0')
        self.assertEqual(len(self.fetch.calls), count)
        self.assertEqual(self.store.fingerprint(), fingerprint)
        self.assertEqual(self.store._state()['active'], before)
        self.assertEqual(sum('codeload.github.com' in url for url in self.fetch.calls), archive_count)

    def test_download_marks_ready_but_notice_remains_until_user_applies(self):
        self.fetch.add('1.1.0', B)
        self.store.refresh(self.repo)
        self.select('1.1.0')
        self.assertTrue(self.notices()[0]['download_ready'])
        self.assertEqual(self.installed[0]['distribution']['commit'], A)
        self.installed = [self.store.packages()[0][ADDON_ID].metadata()]
        self.assertEqual(self.notices(), [])

    def test_disabled_competing_or_unrelated_sources_do_not_advertise_an_update(self):
        self.fetch.add('1.1.0', B)
        self.store.refresh(self.repo)
        other = 'https://catalog.example.test/index.json'
        index = {'schema_version': 1, 'name': 'Other source', 'publisher': 'Another creator', 'packages': [{
            'id': ADDON_ID, 'name': 'Different source', 'description': 'Fixture', 'releases': [{
                'version': '9.0.0', 'url': 'https://catalog.example.test/asset.zip', 'sha256': 'f'*64, 'bytes': 100}]}]}
        original = self.store.fetch
        self.store.fetch = lambda url, limit: json.dumps(index).encode() if url == other else original(url, limit)
        self.store.add(other)
        self.assertEqual(self.notices(), [])
        self.store.configure(self.repo, enabled=False)
        self.assertEqual(self.notices(), [])

    def test_local_install_does_not_receive_an_unrelated_repository_notification(self):
        self.installed[0]['distribution'] = {'kind': 'local', 'filename': 'original.zip'}
        self.fetch.add('1.1.0', B)
        self.store.refresh(self.repo)
        self.assertEqual(self.notices(), [])

    def test_unproven_legacy_origin_does_not_receive_a_repository_notification(self):
        self.installed[0].pop('distribution')
        self.installed[0]['package_digest'] = 'unknown older package'
        self.fetch.add('1.1.0', B)
        self.store.refresh(self.repo)
        rows = self.notices()
        self.assertFalse(any(row['kind'] == 'repository' for row in rows))
        self.assertFalse(any(row['available_version'] == '1.1.0' for row in rows))

    def test_failed_check_retains_changelog_but_disables_uncached_download(self):
        self.fetch.add('1.1.0', B)
        self.store.refresh(self.repo)
        self.fetch.overrides[API] = HTTPStatusError(429)
        with self.assertRaises(ValueError):
            self.store.refresh(self.repo)
        row = self.notices()[0]
        self.assertIn('rate limit', row['check_error'])
        self.assertFalse(row['can_download'])
        self.assertIn('1.1.0', row['changes'][0]['release_notes'])

    def test_prereleases_require_the_selected_channel_and_removed_releases_stop_notices(self):
        self.fetch.add('2.0.0-beta.1', B, prerelease=True)
        self.store.refresh(self.repo)
        self.assertEqual(self.notices(), [])
        self.store.configure(self.repo, channel='prerelease')
        self.store.refresh(self.repo)
        self.assertEqual(self.notices()[0]['available_version'], '2.0.0-beta.1')
        self.fetch.releases.pop()
        self.store.refresh(self.repo)
        self.assertEqual(self.notices(), [])

    def test_development_changes_use_manifest_notes_and_unchanged_payload_does_not_notify(self):
        self.store.configure(self.repo, channel='development')
        self.fetch.add('1.0.0', B, published=False)
        self.store.refresh(self.repo)
        self.assertEqual(self.notices(), [])
        self.fetch.add('1.0.0', C, published=False, code=b'# changed development fixture\n')
        self.store.refresh(self.repo)
        row = self.notices()[0]
        expected = json.loads(self.fetch.manifests[C])['release_notes']
        self.assertEqual(row['changes'][0]['release_notes'], expected)
        self.assertTrue(row['development'])
        self.assertEqual(row['available_commit'], C)
        self.assertFalse(row['download_ready'])

    def test_imported_same_version_change_has_changelog_and_requires_review(self):
        package = self.fetch.add('1.0.0', B, published=False, code=b'# original local iteration fixture\n')
        path = self.root / 'local.m2addon.zip'
        build_artifact(package, path)
        self.store.import_archive(path.read_bytes(), path.name)
        row = self.notices()[0]
        self.assertEqual(row['kind'], 'selected')
        self.assertTrue(row['download_ready'])
        self.assertEqual(row['available_version'], self.installed[0]['version'])
        self.assertTrue(row['changes'][0]['release_notes'])
