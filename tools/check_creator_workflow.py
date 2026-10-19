"""Rehearse creator CLI -> local Studio import -> owned pack lifecycle."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import quote, urlsplit
import urllib.error
import urllib.request
import uuid

PROJECT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8780')
    args = parser.parse_args()
    base = args.url.rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('Use the loopback Studio address, without credentials or extra URL components.')
    token = None

    def request(route, body=None, archive=None):
        headers = {'Origin': base, 'Content-Type': 'application/zip' if archive else 'application/json'}
        if token:
            headers['X-Studio-Token'] = token
        if archive:
            headers['X-Addon-Filename'] = quote(archive.name)
        data = archive.read_bytes() if archive else json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + route, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise ValueError(json.loads(error.read()).get('error', 'Studio API operation failed.')) from error
        if result.get('error') or result.get('ok') is False:
            raise ValueError(result.get('error', 'Studio API operation failed.'))
        return result

    bootstrap = request('/api/bootstrap')
    if Path(bootstrap['projectRoot']).resolve() != PROJECT:
        raise ValueError('The running Studio belongs to another project copy.')
    token = bootstrap['token']
    state = request('/api/addons/state')['state']
    if not state['dependencies']['lzokay'] or not state['source_path']:
        raise ValueError('Install optional add-on support and select a world with sibling client packs first.')
    original_target = state['installation']['path'] if state['installation'] else state['source_path']
    source = Path(state['source_path'])
    def hashes(client):
        return {name: hashlib.sha256((client / 'pack' / name).read_bytes()).hexdigest() for name in ('root.index', 'root.data')}
    original_pair = hashes(source)
    original_workspace = request('/api/workspace')
    ident = 'fixture.creator-' + uuid.uuid4().hex[:10]
    scratch = PROJECT / 'data' / 'creator-checks' / ident
    scratch.mkdir(parents=True)
    archives = {}
    for version in ('1.0.0', '1.1.0'):
        package, archive = scratch / version, scratch / (ident + '-' + version + '.m2addon.zip')
        for arguments in [
            ['new', ident, '--name', 'Creator workflow fixture', '--author', 'Local automated fixture', '--version', version, '--output', str(package)],
            ['validate', str(package)], ['pack', str(package), '--output', str(archive)], ['inspect', str(archive)],
        ]:
            result = subprocess.run([sys.executable, str(PROJECT / 'tools/addon.py'), *arguments], cwd=PROJECT,
                                    capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise ValueError(result.stderr or result.stdout)
        archives[version] = archive
    steps = []
    start = time.monotonic()
    def apply(addon_id, action, **extra):
        plan = request('/api/addons/plan', {'addon_id': addon_id, 'action': action, **extra})['plan']
        assert plan['can_apply'], plan['conflicts']
        request('/api/addons/apply', {'plan_id': plan['id']})
        steps.append(action + ' ' + addon_id)
        print(steps[-1], flush=True)

    request('/api/addons/packages/import', archive=archives['1.0.0'])
    assert hashes(source) == original_pair
    sandbox = Path(request('/api/addons/sandbox', {})['path'])
    assert hashes(sandbox) == original_pair
    apply(ident, 'install')
    apply('community.map-legend', 'install')
    apply(ident, 'configure', settings={'log_map_changes': False})
    request('/api/addons/packages/import', archive=archives['1.1.0'])
    installed = request('/api/addons/state')['state']['installed']
    assert next(row for row in installed if row['id'] == ident)['version'] == '1.0.0'
    apply(ident, 'update')
    installed = request('/api/addons/state')['state']['installed']
    current = next(row for row in installed if row['id'] == ident)
    assert current['version'] == '1.1.0' and current['settings']['log_map_changes'] is False
    apply(ident, 'disable')
    apply(ident, 'enable')
    request('/api/addons/packages/forget', {'addon_id': ident})
    apply(ident, 'remove')
    assert [row['id'] for row in request('/api/addons/state')['state']['installed']] == ['community.map-legend']
    apply('community.map-legend', 'remove')
    assert hashes(sandbox) == original_pair and hashes(source) == original_pair
    current_workspace = request('/api/workspace')
    assert current_workspace['recent'] == original_workspace['recent']
    assert current_workspace['drafts'] == original_workspace['drafts']
    request('/api/addons/connect', {'path': original_target})
    report = {'status': 'passed', 'creator_cli_commands': 8, 'local_imports': 2, 'steps': steps,
              'settings_preserved_on_update': True, 'other_addon_preserved': True,
              'exact_pack_restoration': True, 'source_unchanged': True, 'server_drafts_and_history_unchanged': True,
              'catalog_fixture_removed': True, 'previous_target_reconnected': True,
              'independent_human_trial': False, 'seconds': round(time.monotonic() - start, 2)}
    (PROJECT / 'data/creator-workflow-result.json').write_text(json.dumps(report, indent=2), 'utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
