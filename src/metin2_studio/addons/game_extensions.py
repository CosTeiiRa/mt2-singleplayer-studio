"""Reviewed coordination for the built-in server/client mount extension.

Packages supply quest resources, never an installer to execute. Server writes
use Studio's save receipts; client pack writes have their own durable journal.
"""
from __future__ import annotations

import copy
import difflib
import secrets
import time
from pathlib import Path

from .hubcore.manager import _atomic_bytes, _atomic_json, _json, _now
from .hubcore.packages import confined_file, sha256
from . import mounts_client

IDENT = 'community.legacy-mount-support'
REMOVE = ('disable', 'remove')


def file_hash(path):
    return sha256(path.read_bytes()) if path.is_file() else None


class GameExtensions:
    def __init__(self, service):
        self.service = service
        self.studio = service.studio
        self.directory = service.state_dir / 'extensions' / 'legacy-mount-support'
        self.state_path = self.directory / 'state.json'
        self.journal_path = self.directory / 'journal.json'
        self.pending = None
        self._notification_hashes = {}

    def _notification_hash(self, path):
        # Only read-only reminders use the stat cache. Apply always hashes its
        # inputs again through the component guards.
        stat = path.stat() if path.is_file() else None
        signature = (stat.st_size, stat.st_mtime_ns) if stat else None
        previous = self._notification_hashes.get(str(path))
        if previous and previous[0] == signature:
            return previous[1]
        digest = file_hash(path)
        self._notification_hashes[str(path)] = (signature, digest)
        return digest

    def stored(self):
        result = _json(self.state_path, {'schema_version': 1, 'record': None, 'pending': None, 'retired': None})
        if result.get('schema_version') != 1:
            raise ValueError('Unsupported mount add-on state. Preserve the add-on backups.')
        return result

    def invalidate(self):
        self.pending = None

    def _object(self, raw):
        if raw is None:
            return None
        digest = sha256(raw)
        path = self.directory / 'objects' / digest
        if path.exists() and file_hash(path) != digest:
            raise ValueError('A mount add-on backup is corrupt. Preserve the add-on state directory.')
        if not path.exists():
            _atomic_bytes(path, raw)
        return digest

    def _bytes(self, digest):
        if digest is None:
            return None
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid mount add-on backup checksum.')
        raw = (self.directory / 'objects' / digest).read_bytes()
        if sha256(raw) != digest:
            raise ValueError('A mount add-on backup failed verification.')
        return raw

    def _target(self, *, writable=True):
        backend = self.service.manager._require()
        profile = backend.profile()
        if profile.get('kind') != 'installation' or Path(backend.target_root).resolve() != self.service.source:
            raise ValueError('Legacy Mount Support changes this world’s server and sibling game client. Connect the normal Klient target first.')
        if hasattr(self.service.manager, '_journal_path') and self.service.manager._journal_path.exists():
            raise ValueError('Recover the unfinished client add-on transaction before changing mount support.')
        if hasattr(self.studio, 'save_recovery'):
            self.studio.save_recovery.require_clear()
        if writable:
            backend.check_writable()
        return backend, profile

    def _observed(self, record):
        missing = []
        for rel, expected in record.get('server_hashes', {}).items():
            path = self.studio.safe(self.studio.root / rel)
            if self._notification_hash(path) != expected:
                missing.append(rel)
        client = Path(record['client'])
        for rel, expected in record.get('client_hashes', {}).items():
            if self._notification_hash(confined_file(client, rel)) != expected:
                missing.append('client/' + rel)
        indexes = record.get('client_asset_indexes')
        if indexes and sorted(path.relative_to(client).as_posix() for path in (client / 'pack').glob('*.index')) != indexes:
            missing.append('client/pack asset inventory')
        return missing

    def state(self):
        stored = self.stored()
        record = stored.get('record')
        pending = stored.get('pending')
        installed = []
        if record:
            missing = self._observed(record)
            status = 'missing' if missing or pending else 'healthy'
            item = copy.deepcopy(record['manifest'])
            item.update(installed=True, enabled=record['enabled'], package_digest=record['package_digest'],
                        tested_in_game=False, reapply_pending=status == 'missing',
                        integrity={'status': status, 'message': 'Review and reapply after the game or server files changed.' if status == 'missing' else 'Recorded server and client outputs match.',
                                   'paths': missing}, components=record.get('components', []))
            installed.append(item)
        recovery = None
        if self.journal_path.exists():
            recovery = {'id': _json(self.journal_path)['id'], 'phase': 'mount-client-transaction',
                        'message': 'Recover the unfinished mount client-data transaction before changing add-ons.'}
        warnings = []
        if pending:
            warnings.append('Legacy Mount Support has saved server changes awaiting completion. Review this add-on again to continue.')
        return {'installed': installed, 'recovery': recovery, 'warnings': warnings,
                'pending_plan': copy.deepcopy(self.pending['public']) if self.pending else None}

    def catalog(self, packages):
        state = self.state()
        installed = {row['id']: row for row in state['installed']}
        result = []
        for ident, package in packages.items():
            if package.manifest['kind'] != 'game-extension':
                continue
            item = package.metadata()
            record = installed.get(ident)
            item.update(bundled=package.path.resolve().is_relative_to(self.service.repositories.bundled_dir),
                        installed=bool(record), enabled=bool(record and record['enabled']),
                        installed_version=record['version'] if record else None,
                        update_available=bool(record and record['package_digest'] != package.digest),
                        status='installed' if record else 'available', tested_in_game=False)
            if record:
                item.update(integrity=record['integrity'], reapply_pending=record['reapply_pending'], components=record['components'])
            result.append(item)
        return result

    def plan(self, ident, action='install'):
        from . import mounts_activation
        if ident != IDENT or action not in ('install', 'update', 'reapply', 'repair', 'enable', 'disable', 'remove'):
            raise ValueError('Unsupported game-extension action.')
        if self.journal_path.exists():
            raise ValueError('Recover the unfinished mount add-on transaction first.')
        backend, profile = self._target(writable=False)
        packages, _ = self.service.repositories.packages()
        package = packages.get(ident)
        if not package or package.manifest['kind'] != 'game-extension':
            raise ValueError('The mount add-on package is unavailable. Restore its reviewed package first.')
        stored = self.stored()
        previous = stored.get('record')
        staged = stored.get('pending')
        owner = (staged or {}).get('candidate') or previous or stored.get('retired') or {}
        if staged:
            source_hash = file_hash(self.studio.game / mounts_activation.SOURCE)
            # A durable intent may precede a failed save. In that case the old
            # committed source still has its original, valid ownership receipt.
            for committed in (previous, stored.get('retired')):
                if committed and source_hash == committed.get('activation_ownership', {}).get('source_sha256'):
                    owner = committed
                    break
        client_owner = previous or stored.get('retired') or {}
        if action in ('update', 'reapply', 'repair', 'enable', 'disable', 'remove') and not previous and not staged:
            raise ValueError('Install Legacy Mount Support before changing its saved selection.')
        enabled = action not in REMOVE
        if action in ('update', 'reapply', 'repair'):
            enabled = (previous or owner).get('enabled', True)
        effective_action = action if enabled or action in REMOVE else 'disable'
        baseline = {name: self._bytes(value) for name, value in client_owner.get('client_baseline', {}).items()}
        client = mounts_client.plan_client_fixes(backend.target_root, 'reapply' if effective_action == 'repair' else effective_action,
                    ownership=client_owner.get('client_ownership'), server_root=self.studio.root,
                    model_requests=mounts_activation.model_requests(package), baseline=baseline)
        activation = mounts_activation.plan_activation(self.studio, package, effective_action,
                    asset_availability=client.get('asset_availability'), owned=owner.get('activation_ownership'))
        conflicts = [*client['conflicts'], *activation['conflicts']]
        if not profile.get('writable'):
            conflicts.append(profile.get('details', {}).get('read_only_reason') or 'Connect a supported writable game client before applying.')
        conflicts += getattr(backend, 'mutation_blockers', lambda: [])()
        warnings = [*client['warnings'], *activation['warnings']]
        changes = activation['changes']
        server_files = []
        for path, raw in changes.items():
            before = path.read_bytes() if path.is_file() else None
            if before == raw:
                continue
            diff = '\n'.join(difflib.unified_diff((before or b'').decode('utf-8', 'replace').splitlines(),
                    (raw or b'').decode('utf-8', 'replace').splitlines(), fromfile='before', tofile='after', lineterm=''))
            server_files.append({'path': path.relative_to(self.studio.root).as_posix(), 'diff': diff[:120000]})
        required = bool(activation.get('requires_build'))
        if staged and not staged.get('server_verified'):
            required = True
        # A new source can match a failed prior build exactly: it still needs deployment.
        tracked_pending = {row['path'] for row in self.studio.workspace.summary().get('pending', [])}
        if tracked_pending.intersection(path.relative_to(self.studio.root).as_posix() for path, _ in activation['guards']):
            required = True
        activation_component = copy.deepcopy(activation['component'])
        activation_component['message'] = ('Cleanup only: recorded rides are cleared when characters return.'
            if activation['ownership'].get('cleanup_only') else
            '%d legacy seals can activate; %d refuse activation because their models are missing. %d native seals retain game handlers.' %
            (activation_component.get('available', 0), activation_component.get('refused_missing_assets', 0),
             len(activation_component.get('native_seals_untouched', []))))
        components = [activation_component, {'id': 'client-fixes', 'name': 'Client model and seal fixes',
                       'status': client['status'], 'message': client.get('summary', 'Inspect the client-data conflicts.') }]
        public = {'id': 'extension-' + secrets.token_urlsafe(18), 'addon_id': ident, 'kind': 'game-extension',
                  'entry': 'legacy-mount-support', 'action': action, 'name': package.manifest['name'],
                  'can_apply': not conflicts, 'conflicts': conflicts, 'warnings': warnings,
                  'server_required': required, 'server_files': server_files, 'components': components,
                  'changes': [{'path': 'client/' + rel, 'action': 'modify'} for rel in client['outputs']],
                  'client_changes': copy.deepcopy(client['changes']),
                  'summary': 'Legacy Mount Support: review activation and client-data fixes together.',
                  'target': profile, 'desired_state': [{**package.metadata(), 'enabled': enabled}],
                  'selected_addon_ids': [ident], 'tested_in_game': False}
        self.pending = {'public': public, 'at': time.time(), 'package': package, 'client': client,
                        'activation': activation, 'client_root': Path(backend.target_root), 'owner': owner,
                        'client_owner': client_owner,
                        'effective_action': effective_action, 'enabled': enabled,
                        'stored': stored, 'staged': False, 'server_verified': not required}
        return copy.deepcopy(public)

    def check_plan(self, plan_id, *, files=True):
        plan = self.pending
        if not plan or plan['public']['id'] != plan_id or time.time() - plan['at'] > 1800:
            raise ValueError('The mount add-on review expired. Review a new plan.')
        if not plan['public']['can_apply']:
            raise ValueError('Resolve the mount add-on conflicts before applying.')
        backend, _ = self._target()
        if Path(backend.target_root) != plan['client_root'] or self.stored() != plan['stored']:
            raise ValueError('The mount add-on target or saved selection changed. Review again.')
        if files:
            mounts_client.verify_client_guards(backend.target_root, plan['client'])
            for path, expected in plan['activation']['guards']:
                if file_hash(path) != expected:
                    raise ValueError(path.name + ' changed since the mount review. Review again.')
            from . import mounts_activation
            current = mounts_activation.plan_activation(self.studio, plan['package'], plan['effective_action'],
                asset_availability=plan['client'].get('asset_availability'),
                owned=plan['activation']['ownership'] if plan['staged'] else plan['owner'].get('activation_ownership'))
            if current['context_sha256'] != plan['activation']['context_sha256'] or current['conflicts']:
                raise ValueError('Mount item definitions or competing quest handlers changed since review. Prepare a new plan.')
        return plan

    def _candidate(self, plan):
        old = plan['owner']
        root = self.studio.root
        server = dict(old.get('server_hashes', {}))
        for path, expected in plan['activation']['guards']:
            server[path.relative_to(root).as_posix()] = expected
        server.update({path.relative_to(root).as_posix(): sha256(raw) if raw is not None else None
                       for path, raw in plan['activation']['changes'].items()})
        for guard in plan['client'].get('external_guards', []):
            path = Path(guard['path'])
            if path.is_relative_to(root):
                server[path.relative_to(root).as_posix()] = guard['sha256']
        # Persist originals once, keeping removal safe after an unchanged reapply.
        client_owner = plan['client_owner']
        before = dict(client_owner.get('client_baseline', {}))
        ownership = plan['client']['ownership']
        if ownership.get('before_sha256') != client_owner.get('client_ownership', {}).get('before_sha256'):
            before = {}
            for rel in mounts_client.PACK_FILES:
                raw = (plan['client_root'] / rel).read_bytes()
                if sha256(raw) != plan['client']['guards'][rel]:
                    raise ValueError('Client mount data changed while backing up its baseline. Review again.')
                before[rel] = self._object(raw)
        client_hashes = dict(plan['client']['guards'])
        client_hashes.update(ownership.get('after_sha256', {}))
        components = copy.deepcopy(plan['public']['components'])
        for component in components:
            if component['status'] in ('ready', 'adopted', 'already-integrated'):
                component['status'] = 'installed'
        return {'manifest': plan['package'].metadata(), 'package_digest': plan['package'].digest,
                'enabled': plan['enabled'], 'client': str(plan['client_root']),
                'client_ownership': ownership, 'client_baseline': before,
                'activation_ownership': plan['activation']['ownership'], 'server_hashes': server,
                'client_hashes': client_hashes, 'client_asset_indexes': plan['client'].get('asset_index_paths', []),
                'components': components}

    def stage_server(self, plan_id):
        """Save reviewed server inputs before Studio starts its normal build."""
        plan = self.check_plan(plan_id)
        guards = []
        for path, expected in plan['activation']['guards']:
            raw = path.read_bytes() if path.is_file() else None
            if (sha256(raw) if raw is not None else None) != expected:
                raise ValueError(path.name + ' changed while preparing the server save. Review again.')
            guards.append((path, raw))
        candidate = self._candidate(plan)
        staged = copy.deepcopy(plan['stored'])
        staged['pending'] = {'action': plan['public']['action'], 'candidate': candidate,
                             'server_verified': plan['server_verified'], 'at': _now()}
        _atomic_json(self.state_path, staged)
        plan['stored'] = staged
        changes = {path: raw for path, raw in plan['activation']['changes'].items()
                   if (path.read_bytes() if path.is_file() else None) != raw}
        if changes:
            reviewed = self.studio.plan('Legacy Mount Support: ' + plan['public']['action'], changes,
                         'Activation and client data fixes; combat support is separate.', from_disk=True,
                         metadata={'guards': guards, 'category': 'addons'})
            receipt = self.studio.commit(reviewed['id'])
            staged['pending']['save_receipt'] = receipt.get('id')
            _atomic_json(self.state_path, staged)
        plan['staged'] = True
        # After saving, guards refer to the reviewed postimages for the build continuation.
        updated_guards = []
        for path, expected in plan['activation']['guards']:
            if path in plan['activation']['changes']:
                raw = plan['activation']['changes'][path]
                expected = sha256(raw) if raw is not None else None
            if file_hash(path) != expected:
                raise ValueError(path.name + ' changed during the reviewed server save. Review again.')
            updated_guards.append((path, expected))
        plan['activation']['guards'] = updated_guards
        plan['stored'] = staged
        return copy.deepcopy(staged['pending'])

    def server_applied(self, plan_id):
        plan = self.pending
        if not plan or plan['public']['id'] != plan_id or self.stored() != plan['stored']:
            raise ValueError('The mount server deployment record changed. Review again.')
        for path, expected in plan['activation']['guards']:
            if file_hash(path) != expected:
                raise ValueError('The mount server inputs changed during deployment. Review and build again.')
        plan['server_verified'] = True
        if plan['stored'].get('pending'):
            plan['stored']['pending']['server_verified'] = True
            _atomic_json(self.state_path, plan['stored'])

    def apply(self, plan_id):
        plan = self.check_plan(plan_id)
        if not plan['server_verified']:
            raise ValueError('This mount add-on needs a verified server build. Apply it through Review & apply.')
        if not plan['staged']:
            self.stage_server(plan_id)
        candidate = self._candidate(plan)
        new_state = copy.deepcopy(plan['stored'])
        new_state.update(pending=None, record=None if plan['public']['action'] == 'remove' else candidate,
                         retired=candidate if plan['public']['action'] == 'remove' else None)
        new_state['history'] = [*new_state.get('history', []), {'id': secrets.token_hex(12), 'time': _now(),
            'action': plan['public']['action'], 'addon_id': IDENT, 'status': 'succeeded',
            'kind': 'game-extension', 'name': plan['package'].manifest['name']}][-100:]
        rows = []
        for rel, raw in plan['client']['outputs'].items():
            path = confined_file(plan['client_root'], rel)
            rows.append({'path': rel, 'before': self._object(path.read_bytes()), 'after': self._object(raw)})
        transaction = {'id': secrets.token_hex(12), 'client': str(plan['client_root']), 'phase': 'prepared',
                       'rows': rows, 'new_state': new_state, 'time': _now(), 'addon_id': IDENT,
                       'action': plan['public']['action']}
        _atomic_json(self.journal_path, transaction)
        committed = False
        try:
            mounts_client.verify_client_guards(plan['client_root'], plan['client'])
            for row in rows:
                self._target()
                path = confined_file(plan['client_root'], row['path'])
                if file_hash(path) != row['before']:
                    raise ValueError('Mount client data changed during installation. Recover and review again.')
                _atomic_bytes(path, self._bytes(row['after']))
            if any(file_hash(confined_file(plan['client_root'], row['path'])) != row['after'] for row in rows):
                raise ValueError('Mount client-data output verification failed.')
            transaction['phase'] = 'committed'
            _atomic_json(self.journal_path, transaction)
            committed = True
            _atomic_json(self.state_path, new_state)
            self.journal_path.unlink()
            self.pending = None
        except Exception:
            # Recovery rolls back only bytes from this transaction. A later game
            # update is retained and leaves a visible recovery conflict.
            if not committed:
                self.recover(rollback=True)
            raise
        result = {'status': 'applied', 'transaction': transaction['id']}
        try:
            result['state'] = self.service.state()
        except (OSError, ValueError) as error:
            result['warning'] = 'Applied outputs were verified; refresh the add-on status: ' + str(error)
        return result

    def recover(self, rollback=False):
        if not self.journal_path.exists():
            return {'status': 'nothing-to-recover'}
        journal = _json(self.journal_path)
        client = Path(journal['client']).resolve()
        if client != self.service.source:
            raise ValueError('The unfinished mount transaction belongs to a different client. Preserve its backups.')
        rows = journal['rows']
        observed = {row['path']: file_hash(confined_file(client, row['path'])) for row in rows}
        if any(observed[row['path']] not in (row['before'], row['after']) for row in rows):
            raise ValueError('Mount recovery found a later client-data change. It was retained; preserve backups and review the conflict.')
        if not rollback and journal['phase'] == 'committed':
            if any(observed[row['path']] != row['after'] for row in rows):
                raise ValueError('The committed mount outputs changed. Preserve backups before recovery.')
            _atomic_json(self.state_path, journal['new_state'])
        else:
            self._target()
            for row in reversed(rows):
                path = confined_file(client, row['path'])
                if file_hash(path) == row['after'] and row['after'] != row['before']:
                    _atomic_bytes(path, self._bytes(row['before']))
        self.journal_path.unlink()
        self.pending = None
        return {'status': 'recovered', 'transaction': journal['id']}
