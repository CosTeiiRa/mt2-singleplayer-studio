import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from addonhub.artifacts import build_artifact
from addonhub.collections import create_collection, load_collection, validate_collection
from addonhub.github_source import GitHubSource, identity
from addonhub.hubcore.manager import Manager
from addonhub.repositories import RepositoryStore
from addonhub.transport import HTTPStatusError
from addonhub.updates import update_notices
from collection_fixture import FIRST, SECOND, CollectionFixture, specs
from github_fixture import API, URL
from test_addon_manager import FakeBackend

PROJECT = Path(__file__).resolve().parents[1]
A, B, C = 'a'*40, 'b'*40, 'c'*40


class CollectionTests(unittest.TestCase):
    def setUp(self):
        scratch = PROJECT / '.test-tmp'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temp.name)
        self.fetch = CollectionFixture(self.root / 'creator')
        self.source = self.fetch.snapshot(A, specs())
        self.fetch.publish(FIRST, '1.0.0', A)
        self.fetch.publish(SECOND, '2.0.0', A)
        self.store = RepositoryStore(self.root / 'state', PROJECT / 'addonhub/catalog', self.fetch)

    def tearDown(self):
        self.temp.cleanup()

    def subscribe(self, channel='stable'):
        self.repo = self.store.add(URL, channel)

    def review(self, ident=FIRST, version='1.0.0'):
        return self.store.review(self.repo, ident, version)

    def select(self, ident=FIRST, version='1.0.0'):
        review = self.review(ident, version)
        return self.store.download(review['id'])

    def test_metadata_lists_two_independent_packages_without_selecting_or_downloading(self):
        self.subscribe()
        self.assertEqual(self.store.list()[0]['layout'], 'collection')
        offers = self.store.offers()
        self.assertEqual({row['id'] for row in offers}, {FIRST, SECOND})
        self.assertEqual({row['latest']['version'] for row in offers}, {'1.0.0', '2.0.0'})
        self.assertFalse(self.store._state()['active'])
        self.assertFalse(any('codeload.github.com' in url for url in self.fetch.calls))
        review = self.review()
        self.assertEqual(review['package_path'], 'addons/atlas')
        self.assertTrue(review['collection'])
        self.assertIn('Usage for ' + FIRST, review['readme'])

    def test_shared_commit_caches_and_normalized_archives_are_scoped_to_each_addon(self):
        self.subscribe()
        first = self.select()
        self.assertEqual(set(self.store._state()['active']), {FIRST})
        second = self.select(SECOND, '2.0.0')
        self.assertNotEqual(first['sha256'], second['sha256'])
        self.assertEqual(len(self.store._state()['github_cache']), 2)
        packages = self.store.packages()[0]
        for ident, path, result in [(FIRST, 'addons/atlas', first), (SECOND, 'addons/legend', second)]:
            self.assertEqual(packages[ident].distribution['package_path'], path)
            archive = self.store.root / 'artifacts' / (result['sha256'] + '.zip')
            with zipfile.ZipFile(archive) as bundle:
                self.assertTrue(all(name == 'addon.json' or name.startswith('payload/') for name in bundle.namelist()))
                self.assertEqual(json.loads(bundle.read('addon.json'))['id'], ident)
            cli = self.root / (ident + '.zip')
            self.assertEqual(build_artifact(self.source / path, cli)['sha256'], result['sha256'])

    def test_equal_versions_at_different_commits_do_not_collide(self):
        self.fetch.snapshot(B, specs(second='1.0.0'))
        self.fetch.releases.clear()
        self.fetch.publish(FIRST, '1.0.0', A)
        self.fetch.publish(SECOND, '1.0.0', B)
        self.subscribe()
        self.select()
        self.select(SECOND, '1.0.0')
        self.assertEqual(self.store.packages()[0][FIRST].distribution['commit'], A)
        self.assertEqual(self.store.packages()[0][SECOND].distribution['commit'], B)

    def test_each_addon_updates_and_changelogs_follow_its_own_release_tags(self):
        self.subscribe()
        self.select()
        self.select(SECOND, '2.0.0')
        installed = [self.store.packages()[0][ident].metadata() for ident in (FIRST, SECOND)]
        self.fetch.snapshot(B, specs(first='1.1.0'))
        self.fetch.publish(FIRST, '1.1.0', B)
        self.store.refresh(self.repo)
        notices = update_notices(installed, self.store.offers(installed), [])
        self.assertEqual([row['id'] for row in notices], [FIRST])
        self.assertIn(FIRST, notices[0]['changes'][0]['release_notes'])
        self.select(FIRST, '1.1.0')
        self.assertEqual(self.store.packages()[0][SECOND].distribution['commit'], A)
        self.assertEqual(installed[0]['distribution']['commit'], A)

    def test_development_snapshots_share_commit_without_cross_package_cache_or_false_updates(self):
        self.subscribe('development')
        self.select(FIRST, 'development')
        self.select(SECOND, 'development')
        installed = [self.store.packages()[0][ident].metadata() for ident in (FIRST, SECOND)]
        self.fetch.snapshot(B, specs(first_code=b'# changed original atlas development fixture\n'))
        self.store.refresh(self.repo)
        self.assertEqual([row['id'] for row in self.store.offers(installed) if row['update_available']], [FIRST])
        self.select(FIRST, 'development')
        self.select(SECOND, 'development')
        self.assertEqual(len(self.store._state()['github_cache']), 4)
        self.assertEqual(self.store.packages()[0][FIRST].distribution['commit'], B)
        self.assertEqual(self.store.packages()[0][SECOND].distribution['commit'], B)

    def test_old_release_uses_its_own_pinned_collection_path_after_a_folder_move(self):
        self.subscribe()
        self.fetch.snapshot(B, specs(first='1.1.0', first_path='extensions/atlas'))
        self.fetch.publish(FIRST, '1.1.0', B)
        self.store.refresh(self.repo)
        self.assertEqual(self.review()['package_path'], 'addons/atlas')
        self.select()
        self.assertEqual(self.review(FIRST, '1.1.0')['package_path'], 'extensions/atlas')

    def test_bad_collection_or_manifest_id_preserves_last_good_metadata(self):
        self.subscribe()
        before = copy.deepcopy(self.store._state()['repositories'][self.repo]['index'])
        name = 'addons/atlas/addon.json'
        manifest = json.loads(self.fetch.files[A][name])
        manifest['id'] = 'different.identity'
        self.fetch.files[A][name] = json.dumps(manifest).encode()
        with self.assertRaisesRegex(ValueError, 'id'):
            self.store.refresh(self.repo)
        self.assertEqual(before, self.store._state()['repositories'][self.repo]['index'])

    def test_snapshot_membership_tampering_never_selects_a_package(self):
        self.subscribe()
        review = self.review()
        declaration = json.loads(self.fetch.files[A]['addons.json'])
        declaration['addons'][0]['path'] = 'addons/legend'
        self.fetch.files[A]['addons.json'] = json.dumps(declaration).encode()
        self.fetch.rebuild(A)
        with self.assertRaises(ValueError):
            self.store.download(review['id'])
        self.assertFalse(self.store._state()['active'])

    def test_unselected_sibling_payload_is_not_imported_or_validated_as_the_selected_addon(self):
        self.subscribe()
        for name in list(self.fetch.files[A]):
            if name.startswith('addons/legend/payload/'):
                self.fetch.files[A][name] = b'raise RuntimeError("UNSELECTED SIBLING MUST NOT RUN")\n'
        self.fetch.rebuild(A)
        self.select()
        self.assertEqual(set(self.store._state()['active']), {FIRST})

    def test_moved_tag_stays_bound_to_its_addon_after_remove_and_resubscribe(self):
        self.subscribe()
        self.select()
        self.store.configure(self.repo, remove=True)
        self.fetch.snapshot(B, specs())
        self.fetch.refs[FIRST + '/v1.0.0'] = B
        with self.assertRaisesRegex(ValueError, 'moved'):
            self.subscribe()
        self.assertTrue(self.store.list()[0]['blocked'])
        self.assertEqual(self.store._state()['active'][FIRST]['commit'], A)

    def test_missing_readme_falls_back_to_collection_readme(self):
        del self.fetch.files[A]['addons/atlas/README.md']
        self.subscribe()
        self.assertIn('Original collection instructions', self.review()['readme'])
        self.assertTrue(self.review()['documentation_url'].endswith('/README.md'))

    def test_cached_older_path_is_selectable_offline_after_resubscription(self):
        self.subscribe()
        self.select()
        self.fetch.snapshot(B, specs(first='1.1.0', first_path='extensions/atlas'))
        self.fetch.publish(FIRST, '1.1.0', B)
        self.store.configure(self.repo, remove=True)
        self.subscribe()
        self.fetch.overrides[API] = ValueError('Offline fixture')
        with self.assertRaises(ValueError):
            self.store.refresh(self.repo)
        calls = len(self.fetch.calls)
        self.select()
        self.assertEqual(len(self.fetch.calls), calls)
        self.assertEqual(self.store.packages()[0][FIRST].distribution['package_path'], 'addons/atlas')

    def test_removing_a_member_from_the_collection_retains_its_selected_payload(self):
        self.subscribe()
        self.select()
        active = copy.deepcopy(self.store._state()['active'][FIRST])
        self.fetch.snapshot(B, specs()[1:])
        self.store.refresh(self.repo)
        self.assertEqual(self.store.list()[0]['package_count'], 1)
        self.assertEqual(self.store._state()['active'][FIRST], active)
        self.assertNotIn(FIRST, self.store.packages()[0])

    def test_single_repository_can_become_a_collection_without_reusing_observed_versions(self):
        from github_fixture import GitHubFixture
        single = GitHubFixture(self.root / 'single-creator')
        single.add('1.0.0', A, addon_id=FIRST)
        self.store.fetch = single
        self.subscribe()
        self.select()
        self.fetch.snapshot(B, specs(first='1.1.0'))
        self.fetch.releases.clear()
        self.fetch.publish(FIRST, '1.1.0', B)
        self.fetch.publish(SECOND, '2.0.0', B)
        self.store.fetch = self.fetch
        self.store.refresh(self.repo)
        self.select(FIRST, '1.1.0')
        self.assertTrue(self.store.packages()[0][FIRST].distribution['collection'])
        self.fetch.snapshot(C, specs())
        self.fetch.publish(FIRST, '1.0.0', C)
        self.store.refresh(self.repo)
        with self.assertRaisesRegex(ValueError, 'moved'):
            self.review()

    def test_case_colliding_selected_manifest_is_rejected_inside_collection_archive(self):
        self.subscribe()
        review = self.review()
        original = self.fetch.archives[A]
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(buffer, 'w') as changed:
            for entry in source.infolist():
                raw = source.read(entry)
                changed.writestr(entry, raw)
                if entry.filename.endswith('/addons/atlas/addon.json'):
                    changed.writestr(entry.filename[:-10] + 'ADDON.JSON', raw)
        self.fetch.archives[A] = buffer.getvalue()
        with self.assertRaisesRegex(ValueError, 'case-colliding'):
            self.store.download(review['id'])
        self.assertFalse(self.store._state()['active'])

    def test_collection_tooling_validates_packages_and_refuses_overwrite(self):
        declaration, packages = load_collection(self.source)
        self.assertEqual([package.manifest['id'] for package in packages], [FIRST, SECOND])
        with self.assertRaisesRegex(ValueError, 'exists'):
            create_collection(self.source, ['addons/atlas'], 'Another', 'Creator')
        bad = copy.deepcopy(declaration)
        for entries in ([], [{'id': FIRST, 'path': '../outside'}], [{'id': FIRST, 'path': 'CON'}],
                        [{'id': FIRST, 'path': 'addons/atlas'}, {'id': SECOND, 'path': 'ADDONS/ATLAS'}],
                        [{'id': FIRST, 'path': 'addons'}, {'id': SECOND, 'path': 'addons/nested'}],
                        [{'id': FIRST, 'path': 'a'}, {'id': FIRST, 'path': 'b'}]):
            bad['addons'] = entries
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                validate_collection(bad)

    def test_prerelease_and_unreleased_members_are_separate_and_do_not_require_installing_siblings(self):
        self.fetch.releases.clear()
        self.fetch.publish(FIRST, '1.0.0', A, prerelease=True)
        self.subscribe()
        self.assertTrue(all(row['latest'] is None for row in self.store.offers()))
        self.store.configure(self.repo, channel='prerelease')
        self.store.refresh(self.repo)
        self.select()
        self.assertEqual(set(self.store._state()['active']), {FIRST})
        second = next(row for row in self.store.offers() if row['id'] == SECOND)
        self.assertIsNone(second['latest'])

    def test_independent_settings_enable_remove_and_dependency_validation(self):
        self.subscribe()
        self.select()
        self.select(SECOND, '2.0.0')
        target = self.root / 'target'
        target.mkdir()
        backend = FakeBackend(target)
        original = backend.prepare({'ui.py': b'# original game fixture\n'}, self.root / 'unused')
        for name, raw in original.items():
            (target / name).write_bytes(raw)
        manager = Manager(self.root / 'manager', self.store.bundled_dir, lambda path: backend, catalog_provider=self.store.packages)
        manager.connect(target)
        def apply(ident, action='install', **extra):
            plan = manager.plan(ident, action, **extra)
            self.assertTrue(plan['can_apply'], plan['conflicts'])
            manager.apply(plan['id'])
        apply(FIRST)
        self.assertEqual([row['id'] for row in manager.state()['installed']], [FIRST])
        apply(SECOND)
        apply(FIRST, 'configure', settings={'log_map_changes': False})
        apply(FIRST, 'disable')
        rows = {row['id']: row for row in manager.state()['installed']}
        self.assertFalse(rows[FIRST]['enabled'])
        self.assertTrue(rows[SECOND]['enabled'])
        self.assertTrue(rows[SECOND]['settings']['log_map_changes'])
        apply(FIRST, 'remove')
        apply(SECOND, 'remove')
        self.assertEqual(backend.physical_snapshot(), original)
        package = self.store.packages()[0][FIRST]
        desired = {FIRST: {'manifest': dict(package.manifest, requires=[SECOND]), 'enabled': True, 'settings': {'log_map_changes': False}}}
        conflicts, warnings = manager._desired_valid(desired, backend.profile())
        self.assertTrue(any(SECOND in message for message in conflicts))
