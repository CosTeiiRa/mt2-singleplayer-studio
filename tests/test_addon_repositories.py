import copy
import io
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from metin2_studio.addons.artifacts import archive_members, build_artifact, extract_artifact, inspect_artifact
from metin2_studio.addons.hubcore.manager import Manager
from metin2_studio.addons.hubcore.packages import load_package, parse_json, sha256, validate_manifest
from metin2_studio.addons.repositories import RepositoryStore, validate_index
from metin2_studio.addons.transport import PublicHTTPSFetcher, https_url, public_addresses
from metin2_studio.addons.versions import Version, satisfies
from tools.addon import scaffold, catalog
from tests.test_addon_manager import FakeBackend

PROJECT = Path(__file__).resolve().parents[1]
INDEX_URL = 'https://catalog.example.test/addons.json'
ARTIFACT_URL = 'https://downloads.example.test/overlay.zip'


class FetchFixture:
    def __init__(self):
        self.content = {}
        self.calls = []

    def __call__(self, url, limit):
        self.calls.append((url, limit))
        content = self.content[url]
        if isinstance(content, Exception):
            raise content
        return content


class VersionsTests(unittest.TestCase):
    def test_semver_precedence_and_build_metadata(self):
        ordered = ['1.0.0-alpha', '1.0.0-alpha.1', '1.0.0-alpha.beta', '1.0.0-beta', '1.0.0-beta.2', '1.0.0-beta.11', '1.0.0-rc.1', '1.0.0', '1.9.0', '1.10.0']
        self.assertEqual([item.text for item in sorted(map(Version, reversed(ordered)))], ordered)
        self.assertEqual(Version('1.0.0+one'), Version('1.0.0+two'))

    def test_invalid_versions_and_explicit_ranges(self):
        for value in ['1.2', 'v1.2.3', '01.2.3', '1.0.0-01', '1.0.0-', '1.0.0+']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                Version(value)
        self.assertTrue(satisfies('1.9.0', '>=1.2.3 <2.0.0'))
        self.assertFalse(satisfies('2.0.0', '>=1.2.3 <2.0.0'))
        for expression in ['', ' ', '^1.0.0', '>= 1.0.0']:
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                satisfies('1.0.0', expression)


class UntrustedJSONTests(unittest.TestCase):
    def test_duplicate_keys_nonfinite_numbers_depth_and_surrogates_are_rejected(self):
        for raw in [b'{"version":"1.0.0","version":"2.0.0"}', b'{"value":NaN}', b'[1e999]',
                    b'[' * 40 + b'0' + b']' * 40, b'"\\ud800"', b'\xff', b'[' * 2000]:
            with self.subTest(raw=raw[:80]), self.assertRaises(ValueError):
                parse_json(raw)
        self.assertEqual(parse_json(b'\xef\xbb\xbf{"value":false}'), {'value': False})


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        (PROJECT / '.test-tmp').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=PROJECT / '.test-tmp')
        self.root = Path(self.temp.name)
        self.package_dir = self.root / 'creator'
        scaffold('fixture.overlay', 'Fixture overlay', 'Fixture creator', self.package_dir, version='1.0.0')
        self.artifact = self.root / 'overlay.zip'
        self.info = build_artifact(self.package_dir, self.artifact)
        self.raw = self.artifact.read_bytes()
        self.index = {'schema_version': 1, 'name': 'Fixture catalog', 'publisher': 'Fixture creator',
                      'packages': [{'id': 'fixture.overlay', 'name': 'Fixture overlay', 'description': 'Original fixture',
                                    'releases': [{'version': '1.0.0', 'url': ARTIFACT_URL, 'sha256': sha256(self.raw), 'bytes': len(self.raw)}]}]}
        self.fetch = FetchFixture()
        self.fetch.content[INDEX_URL] = json.dumps(self.index).encode()
        self.fetch.content[ARTIFACT_URL] = self.raw
        self.store = RepositoryStore(self.root / 'state', PROJECT / 'src/metin2_studio/addons/catalog', self.fetch)

    def tearDown(self):
        self.temp.cleanup()

    def subscribe(self):
        self.repo = self.store.add(INDEX_URL)
        return self.repo

    def download(self):
        review = self.store.review(self.repo, 'fixture.overlay', '1.0.0')
        return self.store.download(review['id'])

    def replace_index(self):
        self.fetch.content[INDEX_URL] = json.dumps(self.index).encode()

    def test_creator_artifacts_are_reproducible_and_do_not_include_unlisted_files(self):
        (self.package_dir / 'private.txt').write_text('not part of a release', 'utf-8')
        other = self.root / 'other.zip'
        build_artifact(self.package_dir, other)
        self.assertEqual(self.raw, other.read_bytes())
        info = inspect_artifact(self.raw)
        self.assertEqual(info['manifest']['id'], 'fixture.overlay')
        with zipfile.ZipFile(io.BytesIO(self.raw)) as bundle:
            self.assertNotIn('private.txt', bundle.namelist())

    def test_creator_index_round_trip(self):
        output = self.root / 'catalog.json'
        catalog([self.artifact], 'Created catalog', 'Fixture creator', 'https://downloads.example.test/', output)
        index = validate_index(json.loads(output.read_text('utf-8')))
        self.assertEqual(index['packages'][0]['releases'][0]['sha256'], self.info['sha256'])

    def test_scaffold_and_artifact_outputs_do_not_overwrite_existing_work(self):
        with self.assertRaises(ValueError):
            scaffold('fixture.overlay', 'Name', 'Author', self.package_dir)
        with self.assertRaises(ValueError):
            build_artifact(self.package_dir, self.artifact)

    def test_archive_rejects_traversal_aliases_links_and_undeclared_files(self):
        for name in ['../outside.py', '/absolute.py', 'C:/outside.py', 'payload\\bad.py', 'payload/CON', 'extra.exe']:
            with self.subTest(name=name):
                buffer = io.BytesIO()
                with zipfile.ZipFile(io.BytesIO(self.raw)) as original, zipfile.ZipFile(buffer, 'w') as changed:
                    for member in original.infolist():
                        changed.writestr(member, original.read(member))
                    changed.writestr(name, b'bad')
                with self.assertRaises(ValueError):
                    archive_members(buffer.getvalue())
        for mode in (stat.S_IFLNK | 0o777, stat.S_IFIFO | 0o600):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as archive:
                info = zipfile.ZipInfo('addon.json')
                info.external_attr = mode << 16
                archive.writestr(info, b'{}')
            with self.assertRaises(ValueError):
                archive_members(buffer.getvalue())

    def test_archive_rejects_case_collisions_and_size_limits(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.raw)) as original, zipfile.ZipFile(buffer, 'w') as changed:
            for member in original.infolist():
                changed.writestr(member, original.read(member))
            changed.writestr('ADDON.JSON', b'{}')
        with self.assertRaises(ValueError):
            archive_members(buffer.getvalue())
        with patch('metin2_studio.addons.artifacts.MAX_ARCHIVE_BYTES', 10), self.assertRaises(ValueError):
            archive_members(self.raw)
        with patch('metin2_studio.addons.artifacts.MAX_FILE_BYTES', 8), self.assertRaises(ValueError):
            archive_members(self.raw)

    def test_archive_payload_tampering_is_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.raw)) as original, zipfile.ZipFile(buffer, 'w') as changed:
            for member in original.infolist():
                changed.writestr(member, b'changed' if member.filename.startswith('payload/') else original.read(member))
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            extract_artifact(buffer.getvalue(), self.root / 'invalid-release')

    def test_nul_alias_in_archived_manifest_filename_is_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.raw)) as original, zipfile.ZipFile(buffer, 'w') as changed:
            for member in original.infolist():
                changed.writestr('addon.jsonXsuffix' if member.filename == 'addon.json' else member.filename, original.read(member))
        raw = buffer.getvalue().replace(b'addon.jsonXsuffix', b'addon.json\x00suffix')
        with self.assertRaisesRegex(ValueError, 'NUL'):
            archive_members(raw)

    def test_creator_catalog_uses_newest_metadata_and_refuses_duplicate_filenames(self):
        newest = self.root / 'newest'
        scaffold('fixture.overlay', 'Renamed fixture', 'Fixture creator', newest, version='1.1.0')
        artifact = self.root / 'overlay-1.1.0.zip'
        build_artifact(newest, artifact)
        output = self.root / 'newest-index.json'
        catalog([self.artifact, artifact], 'Creator catalog', 'Fixture creator', 'https://example.test/releases/', output)
        self.assertEqual(json.loads(output.read_text())['packages'][0]['name'], 'Renamed fixture')
        duplicate = self.root / 'another' / self.artifact.name
        duplicate.parent.mkdir()
        duplicate.write_bytes(artifact.read_bytes())
        with self.assertRaisesRegex(ValueError, 'filenames'):
            catalog([self.artifact, duplicate], 'Creator catalog', 'Fixture creator', 'https://example.test/releases/', self.root / 'invalid.json')

    def test_future_sdk_api_and_invalid_dependency_constraints_are_rejected(self):
        manifest = copy.deepcopy(load_package(self.package_dir).manifest)
        manifest['api_version'] = 3
        with self.assertRaises(ValueError):
            validate_manifest(manifest)
        manifest['api_version'] = 1
        manifest['dependency_versions'] = {'other.addon': '>=1.0.0'}
        with self.assertRaises(ValueError):
            validate_manifest(manifest)

    def test_download_adds_catalog_release_without_touching_an_installation(self):
        self.subscribe()
        result = self.download()
        self.assertEqual(result['downloaded'], 'fixture.overlay')
        packages, errors = self.store.packages()
        self.assertIn('fixture.overlay', packages)
        self.assertFalse(errors)
        self.assertFalse((self.store.root / 'targets').exists())
        self.assertNotIn('publisher_verified', self.store.list()[0])

    def test_release_promotion_retries_brief_windows_folder_locks(self):
        self.subscribe()
        rename = Path.rename
        attempts = []
        def sharing_lock(path, destination):
            if path.name == 'release':
                attempts.append(path)
                if len(attempts) < 3:
                    error = PermissionError('Brief Windows sharing lock'); error.winerror = 32
                    raise error
            return rename(path,destination)
        with patch('pathlib.Path.rename',sharing_lock):
            result = self.download()
        self.assertEqual(result['downloaded'],'fixture.overlay')
        self.assertGreaterEqual(len(attempts),3)
        self.assertIn('fixture.overlay',self.store.packages()[0])

    def test_local_archive_import_needs_no_repository_and_survives_reopening(self):
        result = self.store.import_archive(self.raw, 'my-addon.m2addon.zip')
        self.assertEqual(result['imported'], 'fixture.overlay')
        self.assertFalse(self.fetch.calls)
        self.assertFalse(self.store.list())
        reopened = RepositoryStore(self.store.root, self.store.bundled_dir, self.fetch)
        packages, errors = reopened.packages()
        self.assertFalse(errors)
        self.assertEqual(packages['fixture.overlay'].manifest['version'], '1.0.0')
        item = reopened.annotate([{'id': 'fixture.overlay'}])[0]
        self.assertEqual(item['distribution'], {'kind': 'local', 'filename': 'my-addon.m2addon.zip', 'sha256': self.info['sha256']})
        self.assertNotIn('publisher_verified', item)
        reopened.policy_check('fixture.overlay', 'enable')
        self.assertFalse((self.store.root / 'targets').exists())

    def test_local_import_cannot_shadow_bundled_ids_or_use_path_filenames(self):
        for filename in ('../addon.zip', 'C:\\addon.zip', 'bad\n.zip', 'addon.exe', '', ' addon.zip'):
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                self.store.import_archive(self.raw, filename)
        package = self.root / 'reserved'
        scaffold('community.boss-atlas', 'Reserved fixture', 'Creator', package)
        artifact = self.root / 'reserved.zip'
        build_artifact(package, artifact)
        with self.assertRaisesRegex(ValueError, 'bundled'):
            self.store.import_archive(artifact.read_bytes(), artifact.name)
        self.assertFalse(self.store._state()['active'])

    def test_local_build_changes_are_explicit_and_keep_previous_installed_payload(self):
        self.store.import_archive(self.raw, 'overlay.zip')
        target = self.root / 'local-target'
        target.mkdir()
        backend = FakeBackend(target)
        for name, raw in backend.prepare({'ui.py': b'# original game UI\n'}, self.root / 'unused').items():
            (target / name).write_bytes(raw)
        original = backend.physical_snapshot()
        manager = Manager(self.root / 'local-state', self.store.bundled_dir, lambda path: backend, catalog_provider=self.store.packages)
        manager.connect(target)
        plan = manager.plan('fixture.overlay')
        manager.apply(plan['id'])
        previous = backend.physical_snapshot()
        manifest = json.loads((self.package_dir / 'addon.json').read_text('utf-8'))
        data = b'raise RuntimeError("Studio must not execute imported code")\n'
        (self.package_dir / 'payload' / manifest['files'][0]['source']).write_bytes(data)
        manifest['files'][0]['sha256'] = sha256(data)
        (self.package_dir / 'addon.json').write_text(json.dumps(manifest), 'utf-8')
        artifact = self.root / 'new-build.zip'
        build_artifact(self.package_dir, artifact)
        result = self.store.import_archive(artifact.read_bytes(), artifact.name)
        self.assertTrue(result['same_version_changed'])
        self.assertEqual(backend.physical_snapshot(), previous)
        manager.catalog_changed()
        plan = manager.plan('fixture.overlay', 'update')
        manager.apply(plan['id'])
        self.assertEqual(backend.snapshot()[manifest['files'][0]['target']], data)
        plan = manager.plan('fixture.overlay', 'remove')
        manager.apply(plan['id'])
        self.assertEqual(backend.physical_snapshot(), original)

    def test_import_invalidates_download_review_and_remote_source_switch_stays_explicit(self):
        self.subscribe()
        review = self.store.review(self.repo, 'fixture.overlay', '1.0.0')
        self.store.import_archive(self.raw, 'local.zip')
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.store.download(review['id'])
        review = self.store.review(self.repo, 'fixture.overlay', '1.0.0')
        self.assertTrue(review['source_changed'])
        self.assertEqual(review['previous_source'], 'Local file: local.zip')
        with self.assertRaisesRegex(ValueError, 'accept'):
            self.store.download(review['id'])
        self.store.download(review['id'], accept_source_change=True)
        state = self.store._state()
        del state['active']['fixture.overlay']['source_kind']  # alpha-1.2 repository records
        self.store._save(state)
        self.assertIn('fixture.overlay', self.store.packages()[0])

    def test_invalid_or_corrupt_local_archive_does_not_replace_selected_package(self):
        self.store.import_archive(self.raw, 'valid.zip')
        original = self.store.path.read_bytes()
        for raw in (b'not a ZIP', b''):
            with self.assertRaises(ValueError):
                self.store.import_archive(raw, 'invalid.zip')
            self.assertEqual(self.store.path.read_bytes(), original)
        cached = self.store.root / 'artifacts' / (self.info['sha256'] + '.zip')
        cached.write_bytes(b'external change')
        with self.assertRaisesRegex(ValueError, 'unexpected changes'):
            self.store.import_archive(self.raw, 'retry.zip')
        self.assertEqual(self.store.path.read_bytes(), original)

    def test_downloaded_payload_is_never_executed_by_studio(self):
        manifest = json.loads((self.package_dir / 'addon.json').read_text('utf-8'))
        data = b'raise RuntimeError("PAYLOAD WAS EXECUTED")\n'
        (self.package_dir / 'payload' / manifest['files'][0]['source']).write_bytes(data)
        manifest['files'][0]['sha256'] = sha256(data)
        (self.package_dir / 'addon.json').write_text(json.dumps(manifest), 'utf-8')
        path = self.root / 'unexecuted.zip'
        info = build_artifact(self.package_dir, path)
        self.raw = path.read_bytes()
        release = self.index['packages'][0]['releases'][0]
        release.update(sha256=info['sha256'], bytes=info['bytes'])
        self.replace_index()
        self.fetch.content[ARTIFACT_URL] = self.raw
        self.subscribe()
        self.download()

    def test_bad_archive_hash_or_identity_never_changes_selected_release(self):
        self.subscribe()
        review = self.store.review(self.repo, 'fixture.overlay', '1.0.0')
        self.fetch.content[ARTIFACT_URL] = self.raw + b'changed'
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.store.download(review['id'])
        self.assertFalse(self.store._state()['active'])
        self.assertNotIn('fixture.overlay', self.store.packages()[0])

    def test_refresh_invalidates_download_reviews(self):
        self.subscribe()
        review = self.store.review(self.repo, 'fixture.overlay', '1.0.0')
        self.store.refresh(self.repo)
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.store.download(review['id'])

    def test_malformed_remote_json_preserves_the_last_verified_index(self):
        self.subscribe()
        self.download()
        self.fetch.content[INDEX_URL] = b'{"schema_version":1,"schema_version":1}'
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            self.store.refresh(self.repo)
        self.assertEqual(self.store.offers()[0]['latest']['version'], '1.0.0')
        self.assertIn('fixture.overlay', self.store.packages()[0])
        self.assertTrue(self.store.list()[0]['error'])

    def test_archive_identity_must_match_catalog_even_when_hash_is_correct(self):
        self.index['packages'][0]['id'] = 'fixture.other'
        self.replace_index()
        self.subscribe()
        review = self.store.review(self.repo, 'fixture.other', '1.0.0')
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.store.download(review['id'])
        self.assertFalse(self.store._state()['active'])

    def test_manual_repository_state_edit_invalidates_a_download_review(self):
        self.subscribe()
        review = self.store.review(self.repo, 'fixture.overlay', '1.0.0')
        state = self.store._state()
        state['repositories'][self.repo]['index']['publisher'] = 'Unexpected publisher'
        self.store.path.write_text(json.dumps(state), 'utf-8')
        with self.assertRaisesRegex(ValueError, 'changed after review'):
            self.store.download(review['id'])

    def test_mutated_same_version_is_blocked_even_after_removing_and_readding_repository(self):
        self.subscribe()
        self.index['packages'][0]['releases'][0]['sha256'] = 'a' * 64
        self.replace_index()
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.store.refresh(self.repo)
        self.assertTrue(self.store.list()[0]['blocked'])
        self.store.configure(self.repo, remove=True)
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.store.add(INDEX_URL)

    def test_withdrawal_blocks_new_installation_and_enable_but_allows_removal(self):
        self.subscribe()
        self.download()
        self.index['packages'][0]['releases'][0].update(withdrawn=True, reason='Creator withdrawal fixture')
        self.replace_index()
        self.store.refresh(self.repo)
        for action in ('install', 'update', 'enable'):
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.store.policy_check('fixture.overlay', action)
        self.store.policy_check('fixture.overlay', 'remove')
        self.assertNotIn('fixture.overlay', self.store.packages()[0])

    def test_cached_versions_remain_available_offline(self):
        self.subscribe()
        self.download()
        self.fetch.content[INDEX_URL] = ValueError('Offline fixture')
        with self.assertRaises(ValueError):
            self.store.refresh(self.repo)
        count = len(self.fetch.calls)
        review = self.store.review(self.repo, 'fixture.overlay', '1.0.0')
        self.store.download(review['id'])
        self.assertEqual(len(self.fetch.calls), count)
        self.assertIn('fixture.overlay', self.store.packages()[0])

    def test_cached_artifact_tampering_is_not_silently_trusted(self):
        self.subscribe()
        self.download()
        (self.store.root / 'artifacts' / (self.info['sha256'] + '.zip')).write_bytes(b'changed')
        review = self.store.review(self.repo, 'fixture.overlay', '1.0.0')
        with self.assertRaises(ValueError):
            self.store.download(review['id'])

    def test_stable_channel_excludes_prereleases_and_sorts_numerically(self):
        for version in ['1.9.0', '1.10.0', '2.0.0-beta.1']:
            self.index['packages'][0]['releases'].append({**self.index['packages'][0]['releases'][0], 'version': version})
        self.replace_index()
        self.subscribe()
        self.assertEqual(self.store.offers()[0]['latest']['version'], '1.10.0')
        self.store.configure(self.repo, channel='prerelease')
        self.assertEqual(self.store.offers()[0]['latest']['version'], '2.0.0-beta.1')

    def test_competing_repositories_require_source_selection_and_explicit_source_change(self):
        self.subscribe()
        self.download()
        second_url = 'https://other.example.test/catalog.json'
        self.fetch.content[second_url] = self.fetch.content[INDEX_URL]
        second = self.store.add(second_url)
        self.assertTrue(all(item['blocked'] for item in self.store.offers()))
        with self.assertRaises(ValueError):
            self.store.review(second, 'fixture.overlay', '1.0.0')
        self.store.configure(self.repo, enabled=False)
        review = self.store.review(second, 'fixture.overlay', '1.0.0')
        self.assertTrue(review['source_changed'])
        with self.assertRaisesRegex(ValueError, 'accept'):
            self.store.download(review['id'])
        self.store.download(review['id'], accept_source_change=True)

    def test_bundled_ids_cannot_be_shadowed_by_a_repository(self):
        self.index['packages'][0]['id'] = 'community.boss-atlas'
        self.replace_index()
        self.subscribe()
        self.assertTrue(self.store.offers()[0]['blocked'])

    def test_installed_addon_survives_repository_removal_and_can_be_uninstalled(self):
        self.subscribe()
        self.download()
        target = self.root / 'target'
        target.mkdir()
        backend = FakeBackend(target)
        original = backend.prepare({'ui.py': b'# original\n'}, self.root / 'unused')
        for name, raw in original.items():
            (target / name).write_bytes(raw)
        manager = Manager(self.root / 'manager-state', self.store.bundled_dir, lambda path: backend, catalog_provider=self.store.packages)
        manager.connect(target)
        plan = manager.plan('fixture.overlay')
        manager.apply(plan['id'])
        self.store.configure(self.repo, remove=True)
        manager.catalog_changed()
        self.assertEqual(len(manager.state()['installed']), 1)
        plan = manager.plan('fixture.overlay', 'remove')
        manager.apply(plan['id'])
        self.assertEqual(backend.physical_snapshot(), original)

    def test_dependency_version_constraints_block_incompatible_installed_versions(self):
        self.subscribe()
        self.download()
        target = self.root / 'version-target'
        target.mkdir()
        backend = FakeBackend(target)
        for name, raw in backend.prepare({}, self.root / 'unused').items():
            (target / name).write_bytes(raw)
        manager = Manager(self.root / 'version-state', self.store.bundled_dir, lambda path: backend, catalog_provider=self.store.packages)
        manager.connect(target)
        manifest = copy.deepcopy(load_package(self.package_dir).manifest)
        manifest['requires'] = ['fixture.dependency']
        manifest['dependency_versions'] = {'fixture.dependency': '>=2.0.0 <3.0.0'}
        desired = {'fixture.overlay': {'manifest': manifest, 'enabled': True},
                   'fixture.dependency': {'manifest': dict(manifest, id='fixture.dependency', requires=[], dependency_versions={}, version='1.9.0'), 'enabled': True}}
        conflicts, warnings = manager._desired_valid(desired, backend.profile())
        self.assertTrue(any('>=2.0.0' in text for text in conflicts))
        desired['fixture.dependency']['manifest']['version'] = '2.1.0'
        conflicts, warnings = manager._desired_valid(desired, backend.profile())
        self.assertFalse(conflicts)


class TransportTests(unittest.TestCase):
    def test_urls_reject_local_credentials_downgrade_ports_and_fragments(self):
        for value in ['http://example.test/x', 'https://127.0.0.1/x', 'https://localhost/x', 'https://printer.local/x', 'https://user:secret@example.test/x', 'https://example.test:8443/x', 'https://example.test/x#fragment', 'https://example.test/ bad']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                https_url(value)
        self.assertEqual(https_url('https://EXAMPLE.test/file'), 'https://example.test/file')

    def test_dns_private_and_mixed_answers_are_rejected(self):
        for addresses in [['127.0.0.1'], ['10.0.0.1'], ['169.254.169.254'], ['::1'], ['8.8.8.8', '192.168.1.1']]:
            rows = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', (ip, 443)) for ip in addresses]
            with patch('metin2_studio.addons.transport.socket.getaddrinfo', return_value=rows), self.assertRaises(ValueError):
                public_addresses('example.test')

    def test_transport_pins_address_and_retains_tls_hostname(self):
        class Response:
            status = 200
            def __init__(self): self.content = io.BytesIO(b'public fixture')
            def getheader(self, name, default=None): return {'Content-Length': '14'}.get(name, default)
            def read(self, count): return self.content.read(count)
        response = Response()
        with patch('metin2_studio.addons.transport.public_addresses', return_value=['8.8.8.8']), patch('metin2_studio.addons.transport.socket.create_connection') as connect, patch('metin2_studio.addons.transport.ssl.create_default_context') as context, patch('metin2_studio.addons.transport.http.client.HTTPSConnection') as connection:
            connection.return_value.getresponse.return_value = response
            self.assertEqual(PublicHTTPSFetcher()('https://example.test/a', 100), b'public fixture')
            connect.assert_called_once_with(('8.8.8.8', 443), timeout=15)
            context.return_value.wrap_socket.assert_called_once_with(connect.return_value, server_hostname='example.test')

    def test_private_redirect_is_rejected_before_another_connection(self):
        class Response:
            status = 302
            def getheader(self, name, default=None): return 'http://127.0.0.1/private'
        with patch('metin2_studio.addons.transport.public_addresses', return_value=['8.8.8.8']), patch('metin2_studio.addons.transport.socket.create_connection'), patch('metin2_studio.addons.transport.ssl.create_default_context'), patch('metin2_studio.addons.transport.http.client.HTTPSConnection') as connection:
            connection.return_value.getresponse.return_value = Response()
            with self.assertRaises(ValueError):
                PublicHTTPSFetcher()('https://example.test/a', 100)
            self.assertEqual(connection.call_count, 1)

    def test_response_encoding_length_and_body_limits_are_enforced(self):
        class Response:
            status = 200
            def __init__(self, headers, body): self.headers, self.body = headers, io.BytesIO(body)
            def getheader(self, name, default=None): return self.headers.get(name, default)
            def read(self, count): return self.body.read(count)
        for headers, body in [({'Content-Encoding': 'gzip'}, b'zip'), ({'Content-Length': '999'}, b'x'),
                              ({'Content-Length': '3'}, b'x'), ({}, b'x' * 11)]:
            with self.subTest(headers=headers), patch('metin2_studio.addons.transport.public_addresses', return_value=['8.8.8.8']), patch('metin2_studio.addons.transport.socket.create_connection'), patch('metin2_studio.addons.transport.ssl.create_default_context'), patch('metin2_studio.addons.transport.http.client.HTTPSConnection') as connection:
                connection.return_value.getresponse.return_value = Response(headers, body)
                with self.assertRaises(ValueError):
                    PublicHTTPSFetcher()('https://example.test/a', 10)
