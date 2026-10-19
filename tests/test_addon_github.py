import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from addonhub.artifacts import build_artifact
from addonhub.github_source import identity
from addonhub.hubcore.manager import Manager
from addonhub.repositories import RepositoryStore
from addonhub.transport import HTTPStatusError
from github_fixture import ADDON_ID, API, URL, GitHubFixture
from test_addon_manager import FakeBackend

PROJECT = Path(__file__).resolve().parents[1]
A, B, C = 'a' * 40, 'b' * 40, 'c' * 40


class GitHubTests(unittest.TestCase):
    def setUp(self):
        scratch = PROJECT / '.test-tmp'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temp.name)
        self.fetch = GitHubFixture(self.root / 'creator')
        self.package = self.fetch.add('1.0.0', A)
        self.store = RepositoryStore(self.root / 'state', PROJECT / 'addonhub/catalog', self.fetch)

    def tearDown(self):
        self.temp.cleanup()

    def subscribe(self, channel='stable'):
        self.repo = self.store.add(URL, channel)

    def review(self, version='1.0.0'):
        return self.store.review(self.repo, ADDON_ID, version)

    def download(self, version='1.0.0'):
        review = self.review(version)
        return self.store.download(review['id'])

    def test_normalizes_repository_urls_and_rejects_non_repository_paths(self):
        self.assertEqual(identity('https://GitHub.com/Fixture-Creator/Atlas-Addon.git/')['url'], URL)
        self.assertIsNone(identity('https://example.test/catalog.json'))
        for url in (URL + '/tree/main', URL + '?token=private', URL + '#readme', 'https://github.com/a/../b', 'http://github.com/a/b'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                identity(url)
        self.subscribe()
        with self.assertRaisesRegex(ValueError, 'already'):
            self.store.add(URL.upper().replace('HTTPS', 'https') + '.git')

    def test_add_reads_metadata_without_staging_code_and_pins_download_review(self):
        self.subscribe()
        self.assertFalse(self.store._state()['active'])
        self.assertEqual(self.store.list()[0]['kind'], 'github')
        review = self.review()
        self.assertEqual(review['commit'], A)
        self.assertEqual(review['source_ref'], 'v1.0.0')
        self.assertIsNone(review['sha256'])
        self.assertIn('Original creator documentation', review['readme'])
        self.assertFalse(any('codeload.github.com' in call for call in self.fetch.calls))

    def test_download_normalizes_only_declared_files_without_executing_payload_or_build_script(self):
        self.subscribe()
        result = self.download()
        package = self.store.packages()[0][ADDON_ID]
        self.assertEqual(package.distribution['commit'], A)
        self.assertEqual(package.distribution['kind'], 'github')
        artifact = self.store.root / 'artifacts' / (result['sha256'] + '.zip')
        with zipfile.ZipFile(artifact) as archive:
            self.assertFalse(any('setup.py' in name or 'README' in name for name in archive.namelist()))
            self.assertIn('addon.json', archive.namelist())
        original = self.root / 'cli.zip'
        self.assertEqual(build_artifact(self.package, original)['sha256'], result['sha256'])
        self.assertFalse((self.store.root / 'targets').exists())

    def test_tag_move_after_review_downloads_pinned_commit_then_blocks_on_next_check(self):
        self.subscribe()
        review = self.review()
        self.fetch.add('1.0.0', B, published=False)
        self.fetch.refs['v1.0.0'] = B
        self.store.download(review['id'])
        self.assertEqual(self.store._state()['active'][ADDON_ID]['commit'], A)
        with self.assertRaisesRegex(ValueError, 'moved'):
            self.store.refresh(self.repo)
        self.assertTrue(self.store.list()[0]['blocked'])
        self.assertEqual(self.store._state()['active'][ADDON_ID]['commit'], A)

    def test_release_channels_keep_default_branch_separate(self):
        self.fetch.add('2.0.0-beta.1', B, prerelease=True)
        self.subscribe()
        self.assertEqual(self.store.offers()[0]['latest']['version'], '1.0.0')
        with self.assertRaisesRegex(ValueError, 'channel'):
            self.review('development')
        self.store.configure(self.repo, channel='prerelease')
        self.assertEqual(self.store.offers()[0]['latest']['version'], '2.0.0-beta.1')
        self.store.configure(self.repo, channel='development')
        self.assertEqual(self.store.offers()[0]['latest']['version'], 'development')
        review = self.review('development')
        self.assertEqual(review['commit'], B)
        self.assertEqual(review['version'], '2.0.0-beta.1')

    def test_repository_without_releases_requires_explicit_development_selection(self):
        self.fetch.releases.clear()
        self.subscribe()
        self.assertIsNone(self.store.offers()[0]['latest'])
        self.store.configure(self.repo, channel='development')
        self.download('development')
        self.assertEqual(self.store.packages()[0][ADDON_ID].manifest['version'], '1.0.0')

    def test_branch_move_is_pinned_and_update_uses_installed_digest_not_download_selection(self):
        self.subscribe('development')
        review = self.review('development')
        self.fetch.add('1.0.0', B, published=False, code=b'# changed development build\n')
        self.store.download(review['id'])
        target = self.root / 'target'
        target.mkdir()
        backend = FakeBackend(target)
        original = backend.prepare({'ui.py': b'# game\n'}, self.root / 'unused')
        for name, raw in original.items():
            (target / name).write_bytes(raw)
        manager = Manager(self.root / 'manager', self.store.bundled_dir, lambda path: backend, catalog_provider=self.store.packages)
        manager.connect(target)
        plan = manager.plan(ADDON_ID)
        manager.apply(plan['id'])
        self.store.refresh(self.repo)
        self.assertTrue(self.store.offers(manager.state()['installed'])[0]['update_available'])
        self.download('development')
        self.assertEqual(manager.state()['installed'][0]['distribution']['commit'], A)
        self.assertTrue(self.store.offers(manager.state()['installed'])[0]['update_available'])
        manager.catalog_changed()
        plan = manager.plan(ADDON_ID, 'update')
        manager.apply(plan['id'])
        self.assertEqual(manager.state()['installed'][0]['distribution']['commit'], B)
        self.assertFalse(self.store.offers(manager.state()['installed'])[0]['update_available'])
        self.store.configure(self.repo, remove=True)
        manager.catalog_changed()
        plan = manager.plan(ADDON_ID, 'remove')
        manager.apply(plan['id'])
        self.assertEqual(backend.physical_snapshot(), original)

    def test_offline_cached_snapshot_survives_store_reopening_and_needs_no_fetch(self):
        self.subscribe()
        self.download()
        self.fetch.overrides[API] = ValueError('Offline fixture')
        with self.assertRaises(ValueError):
            self.store.refresh(self.repo)
        self.store = RepositoryStore(self.store.root, self.store.bundled_dir, self.fetch)
        count = len(self.fetch.calls)
        self.download()
        self.assertEqual(len(self.fetch.calls), count)

    def test_missing_layout_and_manifest_tag_mismatch_explain_the_problem(self):
        raw = 'https://raw.githubusercontent.com/fixture-creator/atlas-addon/' + A + '/addon.json'
        self.fetch.overrides[raw] = HTTPStatusError(404)
        with self.assertRaisesRegex(ValueError, 'addon.json'):
            self.subscribe()
        self.repo = self.store.list()[0]['id']
        self.fetch.overrides.clear()
        self.fetch.manifests[A] = self.fetch.manifests[A].replace(b'"1.0.0"', b'"1.1.0"')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.store.refresh(self.repo)

    def test_missing_readme_is_optional_but_rate_limit_errors_are_actionable(self):
        self.fetch.readmes.clear()
        self.subscribe()
        self.assertEqual(self.review()['readme'], '')
        self.fetch.overrides[API] = HTTPStatusError(403)
        with self.assertRaisesRegex(ValueError, 'rate limit'):
            self.store.refresh(self.repo)

    def test_declared_symlinks_and_tampered_payloads_never_select_a_release(self):
        self.subscribe()
        archive = self.fetch.archives[A]
        for symlink in (False, True):
            buffer = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(archive)) as original, zipfile.ZipFile(buffer, 'w') as changed:
                for entry in original.infolist():
                    content = original.read(entry)
                    if '/payload/' in entry.filename:
                        if symlink:
                            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                        else:
                            content = b'tampered bytes'
                    changed.writestr(entry, content)
            self.fetch.archives[A] = buffer.getvalue()
            review = self.review()
            with self.assertRaises(ValueError):
                self.store.download(review['id'])
            self.assertFalse(self.store._state()['active'])

    def test_local_to_github_source_change_requires_acknowledgement(self):
        archive = self.root / 'local.zip'
        build_artifact(self.package, archive)
        self.store.import_archive(archive.read_bytes(), archive.name)
        self.subscribe()
        review = self.review()
        self.assertTrue(review['source_changed'])
        with self.assertRaisesRegex(ValueError, 'accept'):
            self.store.download(review['id'])
        self.store.download(review['id'], accept_source_change=True)

    def test_failed_refresh_keeps_last_good_selection_and_payload(self):
        self.subscribe()
        self.download()
        before = self.store._state()['active']
        for response in (HTTPStatusError(429), b'{"private":true}', b'{"private":false,"disabled":true}'):
            self.fetch.overrides[API] = response
            with self.assertRaises(ValueError):
                self.store.refresh(self.repo)
            self.assertEqual(self.store._state()['active'], before)
            self.assertIn(ADDON_ID, self.store.packages()[0])
            self.assertTrue(self.store.offers()[0]['latest']['cached'])

    def test_refresh_and_channel_changes_invalidate_a_download_review(self):
        self.subscribe()
        for change in (lambda: self.store.refresh(self.repo), lambda: self.store.configure(self.repo, channel='prerelease')):
            review = self.review()
            change()
            with self.assertRaisesRegex(ValueError, 'expired|changed'):
                self.store.download(review['id'])
        self.assertFalse(self.store._state()['active'])

    def test_oversized_metadata_and_readme_do_not_stage_code(self):
        for url, raw in ((API, b'x' * (2 * 1024 * 1024 + 1)),
                         ('https://raw.githubusercontent.com/fixture-creator/atlas-addon/' + A + '/README.md', b'x' * (256 * 1024 + 1))):
            with self.subTest(url=url):
                self.fetch.overrides = {url: raw}
                if self.store.list():
                    with self.assertRaisesRegex(ValueError, 'size limit'):
                        self.store.refresh(self.store.list()[0]['id'])
                else:
                    with self.assertRaisesRegex(ValueError, 'size limit'):
                        self.subscribe()
                self.assertFalse(self.store._state()['active'])

    def test_archive_missing_case_colliding_or_changed_manifest_never_replaces_selection(self):
        self.subscribe()
        self.download()
        before = self.store._state()['active']
        self.fetch.add('1.1.0', B)
        self.store.refresh(self.repo)
        original = self.fetch.archives[B]
        for fault in ('missing', 'case', 'manifest'):
            buffer = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(original)) as archive, zipfile.ZipFile(buffer, 'w') as changed:
                for entry in archive.infolist():
                    if fault == 'missing' and '/payload/' in entry.filename:
                        continue
                    content = archive.read(entry)
                    if fault == 'manifest' and entry.filename.endswith('/addon.json'):
                        content = content.replace(b'"1.1.0"', b'"1.2.0"')
                    changed.writestr(entry, content)
                    if fault == 'case' and '/payload/' in entry.filename:
                        changed.writestr(entry.filename.upper().replace('ATLAS-ADDON-', 'atlas-addon-').replace(B.upper(), B), content)
            self.fetch.archives[B] = buffer.getvalue()
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.download('1.1.0')
            self.assertEqual(self.store._state()['active'], before)

    def test_manifest_source_claims_cannot_spoof_package_distribution(self):
        self.subscribe()
        self.download()
        package = self.store.packages()[0][ADDON_ID]
        package.manifest['distribution'] = {'kind': 'verified', 'commit': 'spoofed'}
        self.assertEqual(package.metadata()['distribution']['commit'], A)
        self.assertEqual(package.metadata()['distribution']['kind'], 'github')

    def test_same_payload_at_another_development_commit_does_not_offer_an_update(self):
        self.subscribe('development')
        self.download('development')
        package = self.store.packages()[0][ADDON_ID]
        installed = [{'id': ADDON_ID, 'version': '1.0.0', 'package_digest': package.digest, 'distribution': package.distribution}]
        self.fetch.add('1.0.0', B, published=False)
        self.store.refresh(self.repo)
        self.assertFalse(self.store.offers(installed)[0]['update_available'])

    def test_release_id_change_and_observed_tag_move_after_resubscription_are_blocked(self):
        self.subscribe()
        self.store.configure(self.repo, remove=True)
        self.fetch.add('1.0.0', B, published=False)
        self.fetch.refs['v1.0.0'] = B
        with self.assertRaisesRegex(ValueError, 'moved'):
            self.subscribe()
        self.assertTrue(self.store.list()[0]['blocked'])
