"""World-bound add-on services for the existing Studio process.

Imports involving the optional pack codec happen only when this module is used.
The Studio server workflow does not depend on pack dependencies being installed.
"""
from __future__ import annotations

import copy
from pathlib import Path
import threading

from .client_adapter import ClientAdapter, create_sandbox, create_playable_copy, normalized_client
from .hubcore.manager import Manager
from .map_data import WorldData
from .repositories import RepositoryStore
from .jobs import RepositoryJobs
from .updates import update_notices

PACKAGE = Path(__file__).resolve().parent


class AddonService:
    def __init__(self, studio):
        self.studio = studio
        self.state_dir = studio.state / 'addons'
        self.lock = threading.RLock()
        self.source = None
        self.warning = None
        try:
            self.source = normalized_client(studio.root, allow_missing_packs=True)
        except (ValueError, OSError):
            self.warning = 'No sibling Klient root packs were found. The atlas and server editors remain available.'
        self.repositories = RepositoryStore(self.state_dir, PACKAGE / 'catalog')
        self.manager = Manager(self.state_dir, PACKAGE / 'catalog', self._backend, catalog_provider=self.repositories.packages)
        self._review_tokens = {}
        self._reference_cache = None
        self.jobs = RepositoryJobs(self.state_dir / 'repository-jobs.json', self.repositories, self._finish_network_job)
        if not self.manager.state()['installation'] and self.source:
            self.manager.connect(self.source)

    def _backend(self, path):
        backend = ClientAdapter(path, self.state_dir)
        backend.reference_provider = self.reference
        backend.world_provider = lambda: self.world(fresh=True)
        if backend.server_root.resolve() != self.studio.root.resolve():
            raise ValueError('This add-on target belongs to another world. Select a target belonging to this Studio world.')
        if not backend.marker and (self.source is None or backend.target_root != self.source):
            raise ValueError('Connect the selected world\'s sibling Klient folder or an owned test target.')
        return backend

    def reference(self):
        """Called only by an explicit reviewed pack composition, never by GET."""
        import json
        from datetime import datetime, timezone
        from .knowledge import build_index, encoded
        data = build_index(self.studio)
        ident = data['meta']['snapshot']
        cache = self.state_dir / 'reference-cache' / (ident + '.json')
        if cache.is_file():
            old = json.loads(cache.read_bytes())
            # Cached files supply only stable creation time, never replacement data.
            data['meta']['generated_at'] = str(old.get('meta', {}).get('generated_at', 'Unknown'))[:40]
        else:
            data['meta']['generated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
            from .hubcore.manager import _atomic_bytes
            _atomic_bytes(cache, encoded(data))
        self._reference_cache = data
        return data

    def state(self):
        from .client_pack import lzokay, np
        result = self.manager.state()
        catalogue_revision = self.studio.catalogue_status().get('revision') if hasattr(self.studio, 'catalogue') else None
        if result.get('reference') and catalogue_revision:
            result['reference']['catalogue_current'] = result['reference'].get('catalogue_revision') == catalogue_revision
        for item in result['installed']:
            try:
                self.repositories.policy_check(item['id'], 'enable')
            except ValueError as exc:
                result['warnings'].append(item['name'] + ': ' + str(exc))
        result.update(world={'server_root': str(self.studio.root), 'client_root': str(self.source) if self.source else None},
                      dependencies={'lzokay': lzokay is not None, 'numpy_acceleration': np is not None},
                      source_path=str(self.source) if self.source else None,
                      startup_warning=self.warning,
                      sandbox_targets=self.targets(), repository_count=len(self.repositories.list()), network_job=self.jobs.latest(),
                      update_policy='manual')
        return result

    def _finish_network_job(self, row, working, expected, result, error):
        with self.studio.lock, self.lock:
            try:
                self.jobs.finish(row, working, expected, result, error)
            finally:
                self.manager.catalog_changed()
                self._review_tokens.clear()

    def targets(self):
        import json
        result = []
        markers = list((self.state_dir / 'sandboxes').glob('*/hub-sandbox.json')) + list((self.state_dir / 'playable-clients').glob('*/hub-sandbox.json'))
        for marker in sorted(markers):
            try:
                data = json.loads(marker.read_text('utf-8'))
                target = Path(data['client']).resolve()
                if any(target.is_relative_to((self.state_dir / folder).resolve()) for folder in ('sandboxes', 'playable-clients')) and Path(data['server_root']).resolve() == self.studio.root.resolve():
                    label = 'Playable copy ' if data.get('format') == 'm2hub-playable-copy-v1' else 'Sandbox '
                    result.append({'path': str(target), 'name': label + marker.parent.name})
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return result

    def diagnostics(self):
        state = self.state()
        profile = state['installation'] or {}
        return {'module': 'addon-hub', 'version': state['version'], 'dependencies': state['dependencies'],
                'world': state['world'], 'state_directory': str(self.state_dir),
                'catalog': {'kind': 'bundled examples and explicitly subscribed repositories', 'remote_catalog': True,
                            'trust_model': 'user-selected-sources', 'local_package_import': True, 'github_repositories': True,
                            'repository_count': len(self.repositories.list())},
                'capabilities': {'live_installation_writes': True, 'sandbox_writes': True,
                                 'background_repository_jobs': True, 'playable_test_copies': True,
                                 'automatic_addon_updates': False,
                                 'interactive_gameplay': False, 'boss_presence_telemetry': False},
                'validation': profile.get('details', {}).get('validation')}

    def support_report(self):
        """An explicit allowlist: never serialize raw diagnostics, errors or settings."""
        import re
        state = self.state()
        profile = state['installation'] or {}
        repositories = self.repositories.list()
        def version(value):
            return value if isinstance(value, str) and re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}', value) else None
        return {'report_schema': 1, 'manager_version': state['version'], 'client_api_version': 2,
                'dependencies': state['dependencies'],
                'installation': {'connected': bool(profile), 'sandbox': profile.get('kind') == 'sandbox',
                                 'writable': bool(profile.get('writable')),
                                 'client_version': version(profile.get('client_version')),
                                 'server_version': version(profile.get('server_version'))},
                'installed': [{'id': item['id'], 'version': item['version'], 'enabled': item['enabled']}
                              for item in state['installed']],
                'repositories': {'count': len(repositories), 'enabled': sum(row['enabled'] for row in repositories),
                                 'blocked': sum(row['blocked'] for row in repositories),
                                 'check_errors': sum(bool(row['error']) for row in repositories)},
                'warning_count': len(state['warnings']), 'recovery_required': bool(state.get('recovery')),
                'capabilities': {'live_installation_writes': True, 'interactive_gameplay_verified': False,
                                 'local_package_import': True, 'trust_model': 'user-selected-sources'}}

    def _check_idle(self):
        if self.studio.server_busy() or getattr(self.studio.updates, 'job', {}).get('status') == 'running':
            raise ValueError('Wait for the server build or package update to finish before changing add-ons.')

    def import_archive(self, stream, length, filename):
        from .artifacts import MAX_ARCHIVE_BYTES
        with self.lock:
            self._check_idle()
            self.jobs.assert_idle()
            if not 0 < length <= MAX_ARCHIVE_BYTES:
                raise ValueError('Choose a nonempty add-on ZIP no larger than 66 MiB.')
            raw = bytearray()
            while len(raw) < length:
                chunk = stream.read(min(65536, length - len(raw)))
                if not chunk:
                    raise ValueError('The add-on upload was incomplete. Choose the file again.')
                raw.extend(chunk)
            try:
                return self.repositories.import_archive(bytes(raw), filename)
            finally:
                self.manager.catalog_changed()
                self._review_tokens.clear()

    def world(self, fresh=False):
        # Always read the saved selected-world configuration, not an active draft.
        if fresh and hasattr(self.studio, 'catalogue'):
            self.studio.refresh_catalog(force=True)
        return WorldData(self.studio.root, mobs=getattr(self.studio, 'mobs', None), include_monsters=True)

    def map(self, ident):
        result = copy.deepcopy(self.world().map(ident))
        if result['image_url']:
            result['image_url'] = '/api/addons/map-image?map=%s' % int(ident)
        for region in result['regions']:
            region['drop_target_id'] = str(region['mob_id'])
        return result

    def get(self, route, query):
        with self.lock:
            if route == 'jobs':
                return {'jobs': self.jobs.list()}
            if route == 'job':
                return {'job': self.jobs.get(query.get('id'))}
            if route == 'state':
                return {'state': self.state()}
            if route == 'catalog':
                catalog = self.manager.catalog()
                self.repositories.annotate(catalog['items'])
                return {'catalog': catalog}
            if route == 'repositories':
                return {'repositories': self.repositories.list()}
            if route == 'releases':
                return {'releases': self.repositories.offers(self.manager.state()['installed'])}
            if route == 'updates':
                installed = self.manager.state()['installed']
                return {'policy': 'manual', 'updates': update_notices(installed, self.repositories.offers(installed),
                                                                    self.manager.catalog()['items'])}
            if route == 'history':
                import json
                rows = []
                for history in (self.state_dir / 'targets').glob('*/history.jsonl'):
                    for line in history.read_text('utf-8').splitlines()[-100:]:
                        row = json.loads(line)
                        row['target_id'] = history.parent.name
                        rows.append(row)
                legacy = self.studio.state / 'legacy-addon-history.json'
                if legacy.is_file():
                    recorded = json.loads(legacy.read_text('utf-8'))
                    if Path(recorded['server_root']).resolve() == self.studio.root.resolve():
                        rows += recorded['items']
                return {'history': sorted(rows, key=lambda row: row.get('time', ''), reverse=True)[:100]}
            if route == 'diagnostics':
                return {'diagnostics': self.diagnostics()}
            if route == 'support-report':
                return {'report': self.support_report()}
            if route == 'maps':
                return self.world().catalog()
            if route == 'map':
                return {'map': self.map(int(query.get('map', '64')))}
        raise ValueError('Unknown add-on endpoint.')

    def post(self, route, data):
        with self.lock:
            if route == 'jobs/cancel':
                return {'job': self.jobs.cancel(data.get('job_id'))}
            self._check_idle()
            self.jobs.assert_idle()
            if route == 'jobs/start':
                job = self.jobs.start(data.get('operation'), data.get('data'))
                self.manager.catalog_changed()
                self._review_tokens.clear()
                return {'job': job}
            if route == 'connect':
                return {'state': self.manager.connect(data['path'])}
            if route == 'sandbox':
                if not self.source:
                    raise ValueError('This world has no sibling Klient packs to copy.')
                sandbox = create_sandbox(self.source, self.state_dir)
                return {'state': self.manager.connect(sandbox), 'path': str(sandbox)}
            if route == 'test-client':
                if not self.source:
                    raise ValueError('This world has no sibling client to copy.')
                client = create_playable_copy(self.source, self.state_dir)
                return {'state': self.manager.connect(client), 'path': str(client)}
            if route == 'plan/batch':
                ids = data.get('addon_ids')
                if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(not isinstance(ident, str) for ident in ids):
                    raise ValueError('Select between 1 and 100 add-ons for this batch.')
                catalog = {item['id']: item for item in self.manager.catalog()['items'] if item.get('valid', True)}
                for ident in ids:
                    item = catalog.get(ident, {})
                    action = 'update' if item.get('update_available') else 'reapply' if item.get('installed') else 'install'
                    self.repositories.policy_check(ident, action)
                plan = self.manager.plan_batch(ids)
                self._review_tokens = {plan['id']: self.repositories.fingerprint()}
                return {'plan': plan}
            if route == 'plan':
                self.repositories.policy_check(data['addon_id'], data.get('action', 'install'))
                plan = self.manager.plan(data['addon_id'], data.get('action', 'install'), settings=data.get('settings'))
                self._review_tokens = {plan['id']: self.repositories.fingerprint()}
                return {'plan': plan}
            if route == 'apply':
                if type(data.get('launch_client', False)) is not bool:
                    raise ValueError('Choose whether to open the game client after installation.')
                if self._review_tokens.get(data['plan_id']) != self.repositories.fingerprint():
                    raise ValueError('Repository policy changed or this review expired. Review a new installation plan.')
                result = self.manager.apply(data['plan_id'])
                if data.get('launch_client'):
                    try:
                        result['client_launch'] = self.manager._require().launch_client()
                    except (OSError, ValueError) as error:
                        result['client_launch'] = {'status': 'failed', 'message': str(error)}
                return result
            if route == 'recover':
                return self.manager.recover()
            if route == 'releases/review':
                try:
                    return {'review': self.repositories.review(data['repository_id'], data['addon_id'], data['version'])}
                finally:
                    if any(row['id'] == data['repository_id'] and row['kind'] == 'github' for row in self.repositories.list()):
                        self.manager.catalog_changed()
                        self._review_tokens.clear()
            if route.startswith('repositories/') or route in ('releases/download', 'packages/forget'):
                try:
                    if route == 'repositories/add':
                        self.repositories.add(data['url'], data.get('channel', 'stable'))
                    elif route == 'repositories/refresh':
                        self.repositories.refresh(data['repository_id'])
                    elif route == 'repositories/configure':
                        self.repositories.configure(data['repository_id'], enabled=data.get('enabled'), channel=data.get('channel'))
                    elif route == 'repositories/remove':
                        self.repositories.configure(data['repository_id'], remove=True)
                    elif route == 'releases/download':
                        return self.repositories.download(data['review_id'], data.get('accept_source_change', False))
                    elif route == 'packages/forget':
                        return self.repositories.forget_import(data['addon_id'])
                    else:
                        raise ValueError('Unknown repository operation.')
                    return {'repositories': self.repositories.list()}
                finally:
                    self.manager.catalog_changed()
                    self._review_tokens.clear()
        raise ValueError('Unknown add-on endpoint.')
