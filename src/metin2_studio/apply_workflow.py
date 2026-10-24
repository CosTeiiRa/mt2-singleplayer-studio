"""One reviewed operation for saved server files and client add-ons.

Server deployment and pack transactions retain their own receipts. A failed
add-on apply must never make an already verified server build pending again.
"""
from __future__ import annotations

import copy
import secrets
import threading
import time

from . import deployment_progress


class ApplyWorkflow:
    def __init__(self, studio):
        self.studio = studio
        self.pending = None

    def snapshot(self):
        s = self.studio
        summary = s.workspace.summary()
        return {'files': s.build_fingerprints(), 'package': s.native_pending(),
                'crafting': s.native_crafting.config(), 'pending': summary['pending'],
                'tracking': s.workspace.signature()}

    @staticmethod
    def _selection_rows(plan, state):
        records = {row['id']: row for row in [*state.get('installed', []), *plan.get('desired_state', plan.get('installed', []))]}
        if plan.get('kind') == 'game-extension':
            rows = [records.get(plan.get('addon_id'), {'id': plan.get('addon_id'), 'name': plan.get('name')})]
        elif plan.get('action') == 'batch':
            rows = [{**row, 'id': row.get('addon_id', row.get('id'))} for row in plan.get('batch', [])]
        elif plan.get('action') in ('reapply', 'repair'):
            ids = plan.get('selected_addon_ids') or (state.get('integrity') or {}).get('pending_addon_ids')
            rows = [records[ident] for ident in ids if ident in records] if ids else list(records.values())
        else:
            rows = [records.get(plan.get('addon_id'), {'id': plan.get('addon_id')})]
        return [{'id': row['id'], 'name': row.get('name', row['id']),
                 'version': row.get('version', ''), 'enabled': row.get('enabled', True)}
                for row in rows if isinstance(row.get('id'), str)]

    def review(self, addon_plan_id=None, addon_ids=None, review_id=None):
        s = self.studio
        with s.lock:
            s.require_running()
            if s.server_busy() or s.updates.job.get('status') == 'running':
                raise ValueError('Wait for the current operation to finish before reviewing changes.')
            context = None
            if addon_ids is not None or review_id is not None:
                previous = self.pending
                if (not review_id or not previous or previous['public']['id'] != review_id
                        or time.time() - previous['at'] > 1800):
                    raise ValueError('The selection review expired. Open Review & apply again.')
                context = copy.deepcopy(previous.get('selection_context'))
                if not context:
                    raise ValueError('This review has no selectable add-ons.')
                allowed = {row['id'] for row in context['rows']}
                if (not isinstance(addon_ids, list) or len(addon_ids) > 100
                        or any(not isinstance(ident, str) or ident not in allowed for ident in addon_ids)
                        or len(set(addon_ids)) != len(addon_ids)):
                    raise ValueError('Select distinct add-ons from this review.')
            snapshot = self.snapshot()
            server = bool(snapshot['pending'] or snapshot['package'] or s.native_crafting.pending())
            addon_plan, addon_error, selected = None, None, []
            try:
                service = s.addons
                with service.lock:
                    state = service.state()
                    if context:
                        target = (state.get('installation') or {}).get('path')
                        if target != context.get('target'):
                            raise ValueError('The add-on target changed. Open a new review for that client.')
                        selected = list(addon_ids)
                        if selected:
                            action = context['plan']['action']
                            if action == 'batch':
                                addon_plan = service.post('plan/batch', {'addon_ids': selected})['plan']
                            elif action in ('reapply', 'repair'):
                                addon_plan = service.post('plan', {'addon_id': selected[0], 'action': action,
                                                                  'addon_ids': selected})['plan']
                            else:
                                addon_plan = state.get('pending_plan')
                                if not addon_plan or addon_plan['id'] != context['plan']['id']:
                                    raise ValueError('The add-on review expired. Select the add-on changes again.')
                    else:
                        if addon_plan_id:
                            addon_plan = state.get('pending_plan')
                            if not addon_plan or addon_plan['id'] != addon_plan_id:
                                raise ValueError('The add-on review expired. Select the add-on changes again.')
                        elif (state.get('integrity') or {}).get('repair_available'):
                            pending_ids = (state.get('integrity') or {}).get('pending_addon_ids', [])
                            clients = [row for row in state['installed'] if row.get('kind') != 'game-extension'
                                       and (not pending_ids or row['id'] in pending_ids)]
                            repair_id = clients[0]['id'] if clients else pending_ids[0] if pending_ids else state['installed'][0]['id']
                            addon_plan = service.post('plan', {
                                'addon_id': repair_id,
                                'action': state['integrity']['repair_action']})['plan']
                        if addon_plan:
                            rows = self._selection_rows(addon_plan, state)
                            context = {'rows': rows, 'plan': copy.deepcopy(addon_plan),
                                       'target': (state.get('installation') or {}).get('path')}
                            selected = [row['id'] for row in rows]
            except (ValueError, OSError, ImportError) as error:
                if addon_plan_id or review_id:
                    raise ValueError(str(error)) from error
                addon_error = str(error)
            extension_files = (addon_plan or {}).get('server_files', [])
            server = server or bool((addon_plan or {}).get('server_required'))
            paths = {row['path'] for row in snapshot['pending']}
            public = {'id': secrets.token_urlsafe(18), 'server': server,
                      'files': snapshot['pending'] + [row for row in extension_files if row['path'] not in paths], 'package': bool(snapshot['package']),
                      'crafting': bool(s.native_crafting.pending()),
                      'addons': addon_plan, 'addonError': addon_error,
                      'selectableAddons': copy.deepcopy(context['rows']) if context else [],
                      'selectedAddonIds': selected,
                      'drafts': len(s.workspace.summary()['drafts'])}
            self.pending = {'public': public, 'snapshot': snapshot, 'at': time.time(),
                            'selection_context': context}
            return copy.deepcopy(public)

    def start(self, data):
        s = self.studio
        with s.lock:
            s.require_running()
            review = self.pending
            if (not review or data.get('reviewId') != review['public']['id']
                    or time.time() - review['at'] > 1800):
                raise ValueError('This review expired. Open Review & apply again.')
            if s.server_busy() or s.updates.job.get('status') == 'running':
                raise ValueError('Wait for the current operation to finish.')
            if self.snapshot() != review['snapshot']:
                raise ValueError('Saved files or game updates changed since review. Review & apply again.')
            include = data.get('includeAddons', True)
            include_server = data.get('includeServer', True)
            if type(include) is not bool or type(include_server) is not bool:
                raise ValueError('Choose which reviewed changes to include.')
            public = review['public']
            plan = public['addons'] if include else None
            if plan:
                s.addons.check_review(plan['id'])
                if plan.get('server_required') and not include_server:
                    raise ValueError('Legacy Mount Support requires its server quest build. Select server files before applying this add-on.')
            server = public['server'] and include_server
            if not server and not plan:
                raise ValueError('There are no selected changes to apply.')
            if server:
                # Keep every existing build/recovery/Docker guard. The same worker
                # continues with add-ons after the server receipt is persisted.
                if plan and plan.get('kind') == 'game-extension':
                    s.save_recovery.require_clear()
                    if not s.docker_status()['available']:
                        raise ValueError('Start Docker Desktop before applying this server and client add-on.')
                    s.addons.stage_reviewed(plan['id'])
                job = s.apply(acknowledge_interrupted=data.get('acknowledgeInterrupted'),
                              addon_plan_id=plan['id'] if plan else None)
            else:
                s.save_recovery.require_clear()
                s.job = {'id': secrets.token_hex(12), 'kind': 'addons', 'status': 'running',
                         'started': time.time(), 'lines': [], 'addons': {'status': 'pending'}}
                job = s.job
                self.record(job)
                s._apply_thread = threading.Thread(target=self.apply_addons, args=(job, plan['id']), daemon=False)
                s._apply_thread.start()
            self.pending = None
            return job

    def apply_addons(self, job, plan_id):
        job.pop('finished', None)
        job['status'] = 'running'
        job['addons'] = {'status': 'running'}
        progress = job.setdefault('progress', {'current': None, 'steps': []})
        progress['steps'].append({'id': 'addons', 'label': 'Apply client add-ons',
                                  'detail': 'Rebuilding and verifying the reviewed client packs.', 'status': 'pending'})
        deployment_progress.enter(job, 'addons')
        job['lines'].append('Applying the reviewed add-ons. Keep the game client closed until this finishes.')
        try:
            self.record(job)
            service = self.studio.addons
            with self.studio.lock, service.lock:
                if job.get('serverStatus') == 'succeeded' and plan_id.startswith('extension-'):
                    service.server_applied(plan_id)
                result = service.apply_reviewed(plan_id)
            job['addons'] = {'status': 'succeeded', 'transaction': result.get('transaction')}
            job['lines'].append('Client add-ons applied and verified. You can reopen the game client.')
            job['status'] = 'succeeded'
        except Exception as error:
            job['addons'] = {'status': 'failed', 'error': str(error)}
            job['status'] = 'failed'
            job['lines'].append(('Server changes were applied successfully. ' if job.get('serverStatus') == 'succeeded' else '')
                                + 'Add-ons still need attention: ' + str(error))
        finally:
            deployment_progress.finish(job)
            try:
                self.record(job)
            except OSError as error:
                job['status'] = 'unverified'
                job['lines'].append('The operation receipt could not be saved: ' + str(error))

    def record(self, job):
        receipt = copy.deepcopy(job)
        if (receipt.get('kind') == 'combined' and receipt.get('serverStatus') == 'succeeded'
                and receipt.get('addons', {}).get('status') in ('pending', 'running')):
            # A crash between the server receipt and pack work must not look
            # like a completed combined operation when Studio next starts.
            receipt['status'] = 'running'
            receipt.pop('finished', None)
        receipt['lines'] = receipt.get('lines', [])[-80:]
        self.studio.workspace.set_preference('lastApplyOperation', receipt)
