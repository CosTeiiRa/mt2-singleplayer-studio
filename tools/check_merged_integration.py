"""Exercise the running API using a disposable, non-playable root-pack fixture.

Normal-client packs are only read. No game process, build or server deployment
is started. Use clean upstream source packs, or reuse an empty owned pack-only
sandbox with --sandbox. Native checks live in check_pocket_native.py.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import urllib.parse

PROJECT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8780')
    parser.add_argument('--sandbox', type=Path, help='Reuse an empty owned pack-only sandbox; never a playable copy or the normal client.')
    args = parser.parse_args()
    base = args.url.rstrip('/')
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path:
        raise ValueError('Use the loopback Studio address.')
    token = None
    def request(path, body=None):
        headers = {'Content-Type': 'application/json', 'Origin': base}
        if token:
            headers['X-Studio-Token'] = token
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read())
            if data.get('error') or data.get('ok') is False:
                raise ValueError(data.get('error', 'API operation failed'))
            return data
    bootstrap = request('/api/bootstrap')
    if Path(bootstrap['projectRoot']).resolve() != PROJECT:
        raise ValueError('The running Studio belongs to another project copy.')
    token = bootstrap['token']
    report = exercise(request, bootstrap, args.sandbox)
    destination = PROJECT / 'data/merged-integration-result.json'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), 'utf-8')
    print(json.dumps(report, indent=2))


def exercise(request, bootstrap, existing_sandbox=None):
    """Keep every apply scoped to a verified disposable pack-only target."""
    state = request('/api/addons/state')['state']
    source = Path(state['source_path']).resolve()
    original_target = (state.get('installation') or {}).get('path') or str(source)
    def hashes(client):
        return {name: hashlib.sha256((client / 'pack' / name).read_bytes()).hexdigest() for name in ('root.index', 'root.data')}
    before = hashes(source)
    start = time.monotonic()
    saved = request('/api/workspace')
    steps = []
    try:
        request('/api/addons/connect', {'path': str(source)})
        normal = request('/api/addons/state')['state']['installation']
        assert normal['kind'] == 'installation' and Path(normal['path']).resolve() == source
        # A validated normal client can be writable. Inspect support without
        # preparing or applying any plan against the player's real client.
        normal_support = {'writable': normal['writable'], 'profile_id': normal.get('profile_id')}
        maps = request('/api/addons/maps')['maps']
        atlas = request('/api/addons/map?map=64')['map']
        assert request('/api/file?id=' + urllib.parse.quote(atlas['regions'][0]['source']))['id'] == atlas['regions'][0]['source']
        allowed = (Path(bootstrap['stateDir']) / 'addons/sandboxes').resolve()
        if existing_sandbox is not None:
            sandbox = Path(existing_sandbox).resolve()
            if not sandbox.is_relative_to(allowed):
                raise ValueError('Reuse an owned pack-only sandbox beneath this Studio world data folder.')
            request('/api/addons/connect', {'path': str(sandbox)})
        else:
            sandbox = Path(request('/api/addons/sandbox', {})['path']).resolve()
        fixture = request('/api/addons/state')['state']
        if (not sandbox.is_relative_to(allowed) or fixture['installation']['kind'] != 'sandbox'
                or Path(fixture['installation']['path']).resolve() != sandbox
                or (sandbox / 'metin2client.exe').exists()):
            raise ValueError('The API did not select an owned, non-playable pack-only fixture.')
        if fixture['installed']:
            raise ValueError('The test fixture already has add-ons. Choose an empty disposable pack-only sandbox.')
        fixture_before = hashes(sandbox)
        if existing_sandbox is None:
            assert fixture_before == before
        for ident, action, settings in [
            ('community.boss-atlas', 'install', None),
            ('community.map-legend', 'install', None),
            ('community.boss-atlas', 'configure', {'show_metins': True}),
            ('community.map-legend', 'disable', None),
            ('community.map-legend', 'enable', None),
            ('community.boss-atlas', 'remove', None),
            ('community.map-legend', 'remove', None),
        ]:
            body = {'addon_id': ident, 'action': action}
            if settings is not None:
                body['settings'] = settings
            plan = request('/api/addons/plan', body)['plan']
            assert plan['can_apply'], plan['conflicts']
            reviewed = request('/api/addons/state')['state']
            if (reviewed['installation']['kind'] != 'sandbox'
                    or Path(reviewed['installation']['path']).resolve() != sandbox
                    or (reviewed.get('pending_plan') or {}).get('id') != plan['id']):
                raise ValueError('The selected target changed during the check. No reviewed apply was sent.')
            request('/api/addons/apply', {'plan_id': plan['id']})
            steps.append(action + ' ' + ident)
            print(steps[-1], flush=True)
        assert request('/api/addons/state')['state']['installed'] == []
        assert hashes(sandbox) == fixture_before
        current = request('/api/workspace')
        assert current['recent'] == saved['recent']
        assert current['drafts'] == saved['drafts']
        return {'status': 'passed', 'steps': steps, 'maps': len(maps), 'atlas_to_editor': True,
                'normal_client_support': normal_support,
                'fixture_scope': 'owned non-playable root packs only',
                'native_execution': False, 'native_check': 'tools/check_pocket_native.py',
                'exact_pack_restoration': True, 'source_unchanged': True,
                'server_drafts_and_history_unchanged': True,
                'seconds': round(time.monotonic() - start, 2)}
    finally:
        try:
            request('/api/addons/connect', {'path': original_target})
        finally:
            assert hashes(source) == before, 'Normal client packs changed while checking the disposable fixture.'


if __name__ == '__main__':
    main()
