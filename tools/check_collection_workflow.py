"""Rehearse independent collection add-ons through HTTP on owned pack copies."""
import argparse
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import urllib.request
import uuid

PROJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROJECT), str(PROJECT / 'src')]
from tests.collection_fixture import FIRST, SECOND, CollectionFixture, specs
from tests.github_fixture import URL
from metin2_studio.server import Handler, Studio
from tools.check_github_workflow import hashes

A, B = 'a'*40, 'b'*40


def rehearse(studio, fixture):
    started = time.monotonic()
    studio.addons.repositories.fetch = fixture
    source = studio.addons.source
    original, workspace = hashes(source), studio.workspace.summary()
    steps = []
    class RehearsalHandler(Handler):
        def log_message(self, *args):
            pass
    RehearsalHandler.studio = studio
    server = ThreadingHTTPServer(('127.0.0.1', 0), RehearsalHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:%s' % server.server_port
    def request(route, body=None):
        req = urllib.request.Request(base + '/api/addons/' + route,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json', 'Origin': base, 'X-Studio-Token': studio.token})
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read())
        assert result.get('ok') is not False, result
        return result
    def network(operation, data):
        job = request('jobs/start', {'operation': operation, 'data': data})['job']
        deadline = time.monotonic() + 120
        while job['status'] in ('queued', 'running'):
            assert time.monotonic() < deadline, 'Collection job timed out.'
            time.sleep(.02)
            job = request('job?id=' + job['id'])['job']
        assert job['status'] == 'succeeded', job.get('error')
        return job['result']
    def select(ident, version):
        review = network('releases/review', {'repository_id': repo, 'addon_id': ident, 'version': version})['review']
        assert review['collection'] and review['package_path']
        network('releases/download', {'review_id': review['id']})
    def installed():
        return {row['id']: row for row in request('state')['state']['installed']}
    def apply(ident, action='install', **extra):
        plan = request('plan', {'addon_id': ident, 'action': action, **extra})['plan']
        assert plan['can_apply'], plan['conflicts']
        request('apply', {'plan_id': plan['id']})
        steps.append(action + ' ' + ident)
    try:
        repo = network('repositories/add', {'url': URL})['repositories'][0]['id']
        assert request('repositories')['repositories'][0]['package_count'] == 2
        assert not installed() and not any('codeload.github.com' in url for url in fixture.calls)
        select(FIRST, '1.0.0')
        catalog = request('catalog')['catalog']['items']
        assert FIRST in {row['id'] for row in catalog} and SECOND not in {row['id'] for row in catalog}
        sandbox = Path(request('sandbox', {})['path'])
        apply(FIRST)
        assert list(installed()) == [FIRST]
        select(SECOND, '2.0.0')
        assert list(installed()) == [FIRST]
        apply(SECOND)
        apply(FIRST, 'configure', settings={'log_map_changes': False})
        assert installed()[SECOND]['settings']['log_map_changes'] is True
        apply(FIRST, 'disable')
        assert installed()[SECOND]['enabled'] is True
        apply(FIRST, 'enable')
        fixture.snapshot(B, specs(first='1.1.0'))
        fixture.publish(FIRST, '1.1.0', B)
        network('repositories/check-updates', {})
        updates = request('updates')['updates']
        assert [row['id'] for row in updates] == [FIRST]
        assert FIRST in updates[0]['changes'][0]['release_notes']
        select(FIRST, '1.1.0')
        assert installed()[FIRST]['distribution']['commit'] == A
        assert installed()[SECOND]['distribution']['commit'] == A
        apply(FIRST, 'update')
        assert installed()[FIRST]['version'] == '1.1.0'
        assert installed()[FIRST]['settings']['log_map_changes'] is False
        assert installed()[SECOND]['version'] == '2.0.0'
        assert installed()[SECOND]['distribution']['commit'] == A
        studio._addons = None
        studio.addons.repositories.fetch = fixture
        assert installed()[FIRST]['distribution']['package_path'] == 'addons/atlas'
        assert installed()[SECOND]['settings']['log_map_changes'] is True
        apply(FIRST, 'remove')
        assert list(installed()) == [SECOND]
        request('repositories/remove', {'repository_id': repo})
        assert installed()[SECOND]['distribution']['package_path'] == 'addons/legend'
        apply(SECOND, 'remove')
        assert hashes(sandbox) == original and hashes(source) == original
        assert studio.workspace.summary() == workspace
        request('connect', {'path': str(source)})
        return {'status': 'passed', 'transport': 'controlled collection fixtures over background jobs and real HTTP',
                'steps': steps, 'single_source_two_addons': True, 'no_automatic_selection_or_installation': True,
                'shared_commit_cache_isolation': True, 'independent_versions_settings_and_enabled_state': True,
                'independent_manual_updates_and_changelogs': True, 'restart_retains_package_paths': True,
                'source_removal_preserves_installed_addons': True, 'exact_pack_restoration': True,
                'source_unchanged': True, 'server_workspace_unchanged': True, 'independent_human_trial': False,
                'seconds': round(time.monotonic() - started, 2)}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-root', type=Path)
    args = parser.parse_args()
    root = args.server_root or Path(json.loads((PROJECT / 'data/studio-settings.json').read_text('utf-8-sig'))['serverRoot'])
    scratch = PROJECT / 'data/collection-checks' / uuid.uuid4().hex
    scratch.mkdir(parents=True)
    fixture = CollectionFixture(scratch / 'creator')
    fixture.snapshot(A, specs())
    fixture.publish(FIRST, '1.0.0', A)
    fixture.publish(SECOND, '2.0.0', A)
    studio = Studio(root, scratch / 'state')
    result = rehearse(studio, fixture)
    result['actual_game_pack'] = True
    result['source_pair_sha256'] = hashes(studio.addons.source)
    (PROJECT / 'data/collection-workflow-result.json').write_text(json.dumps(result, indent=2), 'utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
