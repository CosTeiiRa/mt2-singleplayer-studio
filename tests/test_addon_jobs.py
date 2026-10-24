"""Concurrency, isolation and restart boundaries for background repository work."""
import copy
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from metin2_studio.addons.integration import AddonService
from metin2_studio.addons.artifacts import build_artifact
from metin2_studio.addons.jobs import HISTORY_LIMIT, JobCancelled
from metin2_studio.addons.hubcore.manager import _atomic_json
from metin2_studio.addons.repositories import RepositoryStore
from metin2_studio.addons.transport import HTTPStatusError, PublicHTTPSFetcher
from tests.github_fixture import ADDON_ID, API, URL, GitHubFixture
from metin2_studio.server import Handler, Studio

PROJECT = Path(__file__).resolve().parents[1]
A = 'a' * 40


class RepositoryJobTests(unittest.TestCase):
    def setUp(self):
        scratch = PROJECT / '.test-tmp'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temp.name)
        self.studio = Studio.__new__(Studio)
        self.studio.root = self.root / 'world/Serwer'
        self.studio.root.mkdir(parents=True)
        self.studio.state = self.root / 'state'
        self.studio.lock = threading.RLock()
        self.studio._operation_lock = threading.RLock()
        self.studio._active_mutations = 0
        self.studio._stopping = False
        self.studio._apply_thread = None
        self.studio.job = {'status': 'idle'}
        self.studio.updates = SimpleNamespace(job={'status': 'idle'})
        self.studio.workspace = SimpleNamespace(summary=lambda: {'drafts': [], 'recent': []},
                                               set_preference=lambda key, value: {'key': key, 'value': value})
        self.studio.items = {'1': {}}
        self.studio.token = 'background-fixture-token'
        self.studio._addons = None
        self.service = self.studio.addons
        self.fetch = GitHubFixture(self.root / 'creator')
        self.fetch.add('1.0.0', A)
        self.service.repositories.fetch = self.fetch
        self.entered, self.release = threading.Event(), threading.Event()

    def tearDown(self):
        self.release.set()
        if self.service.jobs.thread:
            self.service.jobs.thread.join(timeout=5)
            self.assertFalse(self.service.jobs.thread.is_alive())
        self.temp.cleanup()

    def start(self, operation, data):
        return self.service.post('jobs/start', {'operation': operation, 'data': data})['job']

    def finish(self, job, status='succeeded'):
        self.service.jobs.thread.join(timeout=5)
        self.assertFalse(self.service.jobs.thread.is_alive())
        result = self.service.get('job', {'id': job['id']})['job']
        self.assertEqual(result['status'], status, result.get('error'))
        return result

    def perform(self, operation, data):
        return self.finish(self.start(operation, data))['result']

    def subscribe(self):
        self.repo = self.perform('repositories/add', {'url': URL})['repositories'][0]['id']

    def review(self):
        return self.perform('releases/review', {'repository_id': self.repo, 'addon_id': ADDON_ID, 'version': '1.0.0'})['review']

    def stalled_fetch(self, url, limit):
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise ValueError('Fixture release timed out.')
        return self.fetch(url, limit)

    def test_stalled_network_leaves_reads_and_studio_lock_available_and_cancel_discards_metadata(self):
        self.service.repositories.fetch = self.stalled_fetch
        before = self.service.repositories.fingerprint()
        job = self.start('repositories/add', {'url': URL})
        self.assertTrue(self.entered.wait(timeout=2))
        self.assertTrue(self.studio.lock.acquire(timeout=.2))
        self.studio.lock.release()
        self.assertFalse(self.service.get('repositories', {})['repositories'])
        self.assertEqual(len(self.service.get('catalog', {})['catalog']['items']), 5)
        self.assertEqual(self.service.get('state', {})['state']['network_job']['status'], 'running')
        for route, data in [('connect', {'path': 'unused'}), ('jobs/start', {'operation': 'repositories/add', 'data': {'url': URL}}), ('repositories/remove', {'repository_id': 'unused'})]:
            with self.assertRaisesRegex(ValueError, 'job is running'):
                self.service.post(route, data)
        self.service.post('jobs/cancel', {'job_id': job['id']})
        self.release.set()
        self.finish(job, 'cancelled')
        self.assertEqual(before, self.service.repositories.fingerprint())

    def test_background_add_review_download_and_reopen_preserve_verified_selection(self):
        self.subscribe()
        review = self.review()
        self.assertEqual(review['commit'], A)
        self.assertIn('Original creator documentation', review['readme'])
        self.perform('releases/download', {'review_id': review['id']})
        self.assertEqual(self.service.repositories.packages()[0][ADDON_ID].distribution['commit'], A)
        self.assertFalse(self.service.state()['installed'])
        persisted = json.loads(self.service.jobs.path.read_text('utf-8'))
        self.assertTrue(all('result' not in row for row in persisted['jobs']))
        reopened = AddonService(self.studio)
        self.assertFalse(reopened.jobs.latest()['result_available'])
        self.assertEqual(reopened.repositories.packages()[0][ADDON_ID].distribution['commit'], A)

    def test_failed_check_retains_last_good_metadata_and_cache(self):
        self.subscribe()
        review = self.review()
        self.perform('releases/download', {'review_id': review['id']})
        before = copy.deepcopy(self.service.repositories._state()['active'])
        self.fetch.overrides[API] = HTTPStatusError(429)
        job = self.finish(self.start('repositories/refresh', {'repository_id': self.repo}), 'failed')
        self.assertIn('rate limit', job['error'])
        self.assertEqual(before, self.service.repositories._state()['active'])
        self.assertTrue(self.service.repositories.offers()[0]['latest']['cached'])
        self.assertIn('rate limit', self.service.repositories.list()[0]['error'])
        self.assertEqual(self.service.state()['network_job']['status'], 'failed')

    def test_external_metadata_change_is_not_overwritten_by_a_finishing_job(self):
        self.subscribe()
        self.service.repositories.fetch = self.stalled_fetch
        job = self.start('repositories/refresh', {'repository_id': self.repo})
        self.assertTrue(self.entered.wait(timeout=2))
        state = self.service.repositories._state()
        state['repositories'][self.repo]['enabled'] = False
        self.service.repositories._save(state)
        self.release.set()
        result = self.finish(job, 'failed')
        self.assertIn('state changed', result['error'])
        self.assertFalse(self.service.repositories.list()[0]['enabled'])

    def test_cancel_after_validation_keeps_cache_but_never_selects_prepared_payload(self):
        self.subscribe()
        review = self.review()
        original = RepositoryStore.download
        def delayed(store, *args, **kwargs):
            result = original(store, *args, **kwargs)
            self.entered.set()
            self.release.wait(timeout=5)
            return result
        with patch.object(RepositoryStore, 'download', delayed):
            job = self.start('releases/download', {'review_id': review['id']})
            self.assertTrue(self.entered.wait(timeout=2))
            self.assertFalse(self.service.repositories._state()['active'])
            self.service.post('jobs/cancel', {'job_id': job['id']})
            self.release.set()
            self.finish(job, 'cancelled')
        self.assertFalse(self.service.repositories._state()['active'])
        self.assertTrue(list((self.service.state_dir / 'artifacts').glob('*.zip')))
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.start('releases/download', {'review_id': review['id']})

    def test_restart_marks_unfinished_work_interrupted_and_never_replays_it(self):
        self.subscribe()
        persisted = json.loads(self.service.jobs.path.read_text('utf-8'))
        persisted['jobs'][-1]['status'] = 'running'
        _atomic_json(self.service.jobs.path, persisted)
        calls = len(self.fetch.calls)
        reopened = AddonService(self.studio)
        self.assertEqual(reopened.jobs.latest()['status'], 'interrupted')
        self.assertIn('stopped', reopened.jobs.latest()['error'])
        self.assertIsNone(reopened.jobs.thread)
        self.assertEqual(len(self.fetch.calls), calls)
        self.assertEqual(reopened.repositories.list()[0]['url'], URL)

    def test_history_is_bounded_and_does_not_persist_inputs_or_readme_results(self):
        self.subscribe()
        first = self.service.jobs.latest()['id']
        for _ in range(HISTORY_LIMIT):
            self.perform('repositories/refresh', {'repository_id': self.repo})
        self.assertEqual(len(self.service.get('jobs', {})['jobs']), HISTORY_LIMIT)
        text = self.service.jobs.path.read_text('utf-8')
        for private in ('Original creator documentation', URL, first, '"result":'):
            self.assertNotIn(private, text)

    def test_job_input_validation_and_cancel_reject_unknown_or_finished_work(self):
        for operation, data in [('apply', {}), ('repositories/add', {}), ('repositories/add', {'url': []}),
                                ('repositories/add', {'url': URL, 'execute': True}), ('releases/download', {'review_id': 'missing', 'accept_source_change': 'yes'})]:
            with self.subTest(operation=operation, data=data), self.assertRaises(ValueError):
                self.start(operation, data)
        self.assertIsNone(self.service.jobs.thread)
        with self.assertRaises(ValueError):
            self.service.post('jobs/cancel', {'job_id': 'missing'})
        self.subscribe()
        with self.assertRaises(ValueError):
            self.service.post('jobs/cancel', {'job_id': self.service.jobs.latest()['id']})

    def test_failed_enqueue_does_not_leave_a_phantom_active_job(self):
        with patch.object(self.service.jobs, '_save', side_effect=OSError('Fixture disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.start('repositories/add', {'url': URL})
        self.assertIsNone(self.service.jobs.latest())
        self.assertIsNone(self.service.jobs.thread)
        self.subscribe()

    def test_expired_download_reviews_are_not_exposed_as_reusable_job_results(self):
        self.subscribe()
        self.review()
        job_id = self.service.jobs.latest()['id']
        self.assertTrue(self.service.jobs.get(job_id)['result_available'])
        self.service.post('repositories/configure', {'repository_id': self.repo, 'enabled': False})
        job = self.service.jobs.get(job_id)
        self.assertFalse(job['result_available'])
        self.assertNotIn('result', job)

    def test_catalog_jobs_and_cached_offline_selection_reuse_the_same_flow(self):
        archive = self.root / 'catalog-package.zip'
        info = build_artifact(self.fetch.root / A, archive)
        catalog_url, asset_url = 'https://catalog.example.test/index.json', 'https://catalog.example.test/package.zip'
        index = {'schema_version': 1, 'name': 'Fixture catalog', 'publisher': 'Fixture creator', 'packages': [{
            'id': ADDON_ID, 'name': 'Fixture package', 'description': 'Original fixture', 'releases': [{
                'version': '1.0.0', 'url': asset_url, 'sha256': info['sha256'], 'bytes': info['bytes']}]}]}
        content = {catalog_url: json.dumps(index).encode(), asset_url: archive.read_bytes()}
        self.service.repositories.fetch = lambda url, limit: content[url]
        self.repo = self.perform('repositories/add', {'url': catalog_url})['repositories'][0]['id']
        review = self.review()
        self.perform('releases/download', {'review_id': review['id']})
        self.assertEqual(self.service.repositories.packages()[0][ADDON_ID].distribution['kind'], 'repository')
        def offline(url, limit):
            raise ValueError('Offline fixture')
        self.service.repositories.fetch = offline
        self.finish(self.start('repositories/refresh', {'repository_id': self.repo}), 'failed')
        review = self.review()
        self.perform('releases/download', {'review_id': review['id']})
        self.assertEqual(self.service.repositories.packages()[0][ADDON_ID].distribution['sha256'], info['sha256'])

    def test_transport_progress_reports_bytes_and_cancellation_closes_connection(self):
        class Response:
            status = 200
            def getheader(self, name, default=None):
                return '5' if name == 'Content-Length' else default
            def read(self, count):
                return b'bytes'
        observations = []
        def progress(received, total):
            observations.append((received, total))
            if received:
                raise JobCancelled()
        with patch('metin2_studio.addons.transport.public_addresses', return_value=['8.8.8.8']), patch('metin2_studio.addons.transport.socket.create_connection'), patch('metin2_studio.addons.transport.ssl.create_default_context'), patch('metin2_studio.addons.transport.http.client.HTTPSConnection') as connection:
            connection.return_value.getresponse.return_value = Response()
            with self.assertRaises(JobCancelled):
                PublicHTTPSFetcher()('https://example.test/fixture.zip', 10, progress=progress)
            connection.return_value.close.assert_called_once()
        self.assertIn((0, 5), observations)
        self.assertIn((5, 5), observations)

    def test_manual_update_check_reports_partial_errors_and_skips_disabled_sources(self):
        self.subscribe()
        other = 'https://catalog.example.test/index.json'
        original = self.service.repositories.fetch
        broken = False
        def fetch(url, limit):
            if url == other:
                if broken:
                    raise ValueError('Offline second source')
                return b'{"schema_version":1,"name":"Second source","publisher":"Fixture","packages":[]}'
            return original(url, limit)
        self.service.repositories.fetch = fetch
        self.perform('repositories/add', {'url': other})
        other_id = next(row['id'] for row in self.service.repositories.list() if row['url'] == other)
        before = copy.deepcopy(self.service.repositories._state()['active'])
        broken = True
        result = self.perform('repositories/check-updates', {})
        self.assertEqual(len(result['checked_repositories']), 2)
        self.assertEqual(result['check_errors'], 1)
        self.assertEqual(before, self.service.repositories._state()['active'])
        self.assertFalse(any('codeload.github.com' in url for url in self.fetch.calls))
        self.assertEqual(self.service.get('updates', {}), {'policy': 'manual', 'updates': []})
        self.service.post('repositories/configure', {'repository_id': other_id, 'enabled': False})
        result = self.perform('repositories/check-updates', {})
        self.assertEqual(result['check_errors'], 0)
        self.assertEqual(len(result['checked_repositories']), 1)

    def test_cancel_all_source_check_discards_metadata_prepared_before_cancellation(self):
        self.subscribe()
        self.service.repositories.fetch = self.stalled_fetch
        before = self.service.repositories.fingerprint()
        job = self.start('repositories/check-updates', {})
        self.assertTrue(self.entered.wait(timeout=2))
        self.service.post('jobs/cancel', {'job_id': job['id']})
        self.release.set()
        self.finish(job, 'cancelled')
        self.assertEqual(before, self.service.repositories.fingerprint())

    def test_http_stalled_job_keeps_source_reads_and_server_preferences_responsive(self):
        self.service.repositories.fetch = self.stalled_fetch
        class TestHandler(Handler):
            def log_message(self, *args):
                pass
        TestHandler.studio = self.studio
        server = ThreadingHTTPServer(('127.0.0.1', 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:%s' % server.server_port
        def request(path, body=None, **headers):
            req = urllib.request.Request(base + '/api/' + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={'Content-Type': 'application/json', 'Origin': base, 'X-Studio-Token': self.studio.token, **headers})
            with urllib.request.urlopen(req, timeout=2) as response:
                return response.status, json.loads(response.read())
        try:
            for headers in ({'Origin': 'https://foreign.invalid'}, {'X-Studio-Token': 'wrong'}):
                with self.assertRaises(urllib.error.HTTPError):
                    request('addons/jobs/start', {'operation': 'repositories/add', 'data': {'url': URL}}, **headers)
            code, result = request('addons/jobs/start', {'operation': 'repositories/add', 'data': {'url': URL}})
            self.assertEqual(code, 202)
            self.assertTrue(self.entered.wait(timeout=2))
            self.assertEqual(request('addons/state')[1]['state']['network_job']['status'], 'running')
            self.assertFalse(request('addons/repositories')[1]['repositories'])
            self.assertEqual(request('workspace')[1]['drafts'], [])
            self.assertEqual(request('preferences', {'key': 'itemFavourites', 'value': ['1']})[1]['value'], ['1'])
            with self.assertRaises(urllib.error.HTTPError):
                request('addons/plan', {'addon_id': ADDON_ID})
            request('addons/jobs/cancel', {'job_id': result['job']['id']})
            self.release.set()
            self.finish(result['job'], 'cancelled')
        finally:
            self.release.set()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
