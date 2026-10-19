"""Developer rehearsal: controlled GitHub responses through Studio HTTP and owned packs.

Reads the selected game installation. All writable state and pack copies belong to
this project. No public repository is created, and this is not an independent trial.
"""
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / 'tests'))
from github_fixture import ADDON_ID, API, URL, GitHubFixture
from server import Handler, Studio
from addonhub.transport import HTTPStatusError

A, B = 'a' * 40, 'b' * 40


def hashes(client):
    return {name: hashlib.sha256((Path(client) / 'pack' / name).read_bytes()).hexdigest()
            for name in ('root.index', 'root.data')}


def rehearse(studio, fixture):
    start = time.monotonic()
    service = studio.addons
    service.repositories.fetch = fixture
    source = service.source
    original = hashes(source)
    workspace = studio.workspace.summary()
    steps = []
    class RehearsalHandler(Handler):
        def log_message(self, *args):
            pass
    RehearsalHandler.studio = studio
    server = ThreadingHTTPServer(('127.0.0.1', 0), RehearsalHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:%s' % server.server_port
    def request(route, body=None, headers=None):
        req = urllib.request.Request(base + '/api/addons/' + route,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json', 'Origin': base,
                     'X-Studio-Token': studio.token, **(headers or {})})
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read())
        assert result.get('ok') is not False, result
        return result
    def rejected(route, body, headers=None):
        try:
            request(route, body, headers)
        except urllib.error.HTTPError as error:
            assert error.code == 400, error.code
            return
        raise AssertionError('Expected the request to be rejected: ' + route)
    def network(operation, data, expected='succeeded'):
        job = request('jobs/start', {'operation': operation, 'data': data})['job']
        deadline = time.monotonic() + 120
        while job['status'] in ('queued', 'running'):
            assert time.monotonic() < deadline, 'Repository job timed out.'
            time.sleep(.02)
            job = request('job?id=' + job['id'])['job']
        assert job['status'] == expected, job.get('error')
        return job.get('result') if expected == 'succeeded' else job
    def selected(version):
        return network('releases/review', {'repository_id': repository_id, 'addon_id': ADDON_ID, 'version': version})['review']
    def apply(ident, action='install', **extra):
        plan = request('plan', {'addon_id': ident, 'action': action, **extra})['plan']
        assert plan['can_apply'], plan['conflicts']
        request('apply', {'plan_id': plan['id']})
        steps.append(action + ' ' + ident)
    def installed():
        return next(row for row in request('state')['state']['installed'] if row['id'] == ADDON_ID)
    try:
        for headers in ({'X-Studio-Token': 'wrong'}, {'Origin': 'https://foreign.invalid'}):
            rejected('jobs/start', {'operation': 'repositories/add', 'data': {'url': URL}}, headers)
        assert not request('repositories')['repositories']
        repository_id = network('repositories/add', {'url': URL})['repositories'][0]['id']
        assert not request('state')['state']['installed']
        assert not any('codeload.github.com' in call for call in fixture.calls)
        review = selected('1.0.0')
        assert review['commit'] == A and 'Original creator documentation' in review['readme']
        network('releases/download', {'review_id': review['id']})
        assert not request('state')['state']['installed']
        sandbox = Path(request('sandbox', {})['path'])
        assert hashes(sandbox) == original
        stale = request('plan', {'addon_id': ADDON_ID})['plan']
        selected('1.0.0')
        rejected('apply', {'plan_id': stale['id']})
        assert hashes(sandbox) == original
        apply(ADDON_ID)
        apply('community.map-legend')
        apply(ADDON_ID, 'configure', settings={'log_map_changes': False})
        fixture.add('1.1.0', B)
        calls = len(fixture.calls)
        assert request('updates')['updates'] == []
        assert len(fixture.calls) == calls
        archives_before = sum('codeload.github.com' in url for url in fixture.calls)
        checked = network('repositories/check-updates', {})
        assert checked['check_errors'] == 0
        updates = request('updates')
        assert updates['policy'] == 'manual' and request('state')['state']['update_policy'] == 'manual'
        assert updates['updates'][0]['available_version'] == '1.1.0'
        assert 'Original fixture release 1.1.0' in updates['updates'][0]['changes'][0]['release_notes']
        assert not updates['updates'][0]['download_ready']
        assert sum('codeload.github.com' in url for url in fixture.calls) == archives_before
        assert installed()['distribution']['commit'] == A
        assert request('releases')['releases'][0]['update_available']
        review = selected('1.1.0')
        network('releases/download', {'review_id': review['id']})
        assert installed()['distribution']['commit'] == A
        assert installed()['version'] == '1.0.0'
        assert request('updates')['updates'][0]['download_ready']
        fixture.overrides[API] = HTTPStatusError(429)
        network('repositories/refresh', {'repository_id': repository_id}, expected='failed')
        assert installed()['distribution']['commit'] == A
        assert installed()['settings']['log_map_changes'] is False
        fixture.overrides.clear()
        network('repositories/refresh', {'repository_id': repository_id})
        apply(ADDON_ID, 'update')
        assert installed()['version'] == '1.1.0'
        assert request('updates')['updates'] == []
        assert installed()['distribution']['commit'] == B
        assert installed()['settings']['log_map_changes'] is False
        studio._addons = None
        studio.addons.repositories.fetch = fixture
        assert installed()['distribution']['commit'] == B
        assert installed()['settings']['log_map_changes'] is False
        apply(ADDON_ID, 'disable')
        apply(ADDON_ID, 'enable')
        request('repositories/remove', {'repository_id': repository_id})
        assert installed()['distribution']['commit'] == B
        apply(ADDON_ID, 'remove')
        assert [row['id'] for row in request('state')['state']['installed']] == ['community.map-legend']
        apply('community.map-legend', 'remove')
        assert hashes(sandbox) == original and hashes(source) == original
        assert studio.workspace.summary() == workspace
        request('connect', {'path': str(source)})
        return {'status': 'passed', 'transport': 'controlled GitHub response fixtures; background jobs over real loopback HTTP',
                'background_repository_jobs': True, 'manual_update_policy': True,
                'changelog_visible_before_download': True, 'metadata_checks_do_not_download': True,
                'update_notice_remains_until_apply': True, 'network_jobs': len(studio.addons.jobs.list()),
                'steps': steps, 'settings_preserved_on_update': True, 'installed_revision_preserved_until_apply': True,
                'restart_retains_revision_and_settings': True, 'failed_check_preserves_installation': True,
                'stale_plan_rejected': True, 'session_and_origin_checks': True, 'other_addon_preserved': True,
                'exact_pack_restoration': True, 'source_unchanged': True, 'server_workspace_unchanged': True,
                'fixture_subscription_removed': True, 'source_reconnected_read_only': True,
                'independent_human_trial': False, 'seconds': round(time.monotonic() - start, 2)}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-root', type=Path)
    args = parser.parse_args()
    root = args.server_root
    if root is None:
        root = Path(json.loads((PROJECT / 'data/studio-settings.json').read_text('utf-8-sig'))['serverRoot'])
    scratch = PROJECT / 'data/github-checks' / uuid.uuid4().hex
    scratch.mkdir(parents=True)
    fixture = GitHubFixture(scratch / 'creator')
    fixture.add('1.0.0', A)
    studio = Studio(root, scratch / 'state')
    report = rehearse(studio, fixture)
    report['actual_game_pack'] = True
    report['source_pair_sha256'] = hashes(studio.addons.source)
    (PROJECT / 'data/github-workflow-result.json').write_text(json.dumps(report, indent=2), 'utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
