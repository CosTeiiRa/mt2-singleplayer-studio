"""Combined Apply ordering, stale reviews and independent completion receipts."""
import copy
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from metin2_studio.server import Studio


class ApplyWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.pending = [{'path': 'drops.txt'}]
        self.preferences = {}
        self.receipts = []
        self.fingerprints = {'drops.txt': 'reviewed'}
        self.plan = {'id': 'pack-review', 'can_apply': True, 'action': 'reapply',
                     'changes': [{'path': 'm2hub_config.py', 'action': 'add'}]}
        self.service = SimpleNamespace(lock=threading.RLock(),
            state=Mock(return_value={'installed': [{'id': 'example'}], 'pending_plan': self.plan,
                                     'integrity': {'repair_available': True, 'repair_action': 'reapply'}}),
            post=Mock(return_value={'plan': self.plan}), check_review=Mock(),
            apply_reviewed=Mock(side_effect=self.apply_pack))
        s = self.studio = Studio.__new__(Studio)
        s.lock = threading.RLock()
        s._stopping = False
        s._apply_thread = None
        s._addons = self.service
        s.job = {'status': 'idle'}
        s.root = Path('synthetic-world')
        s.compose = s.root / 'compose'
        s.updates = SimpleNamespace(job={'status': 'idle'})
        s.save_recovery = SimpleNamespace(require_clear=Mock())
        s.build_fingerprints = lambda: copy.deepcopy(self.fingerprints)
        s.native_pending = lambda: {'ready': True}
        s.native_crafting = SimpleNamespace(config=lambda: {'recipes': {}}, pending=lambda: False,
                                           preflight=Mock(), applied=lambda: {'recipes': {}})
        s.docker_status = Mock(return_value={'available': True})
        s.runtime_health = Mock(return_value={'gameHealthy': True})
        s.workspace = SimpleNamespace(summary=lambda: {'pending': copy.deepcopy(self.pending), 'drafts': []},
            signature=lambda: 'tracking', interrupted_deployment=lambda: None,
            scan=lambda **kw: {'affectedFiles': 0}, deployment=self.deployment,
            set_preference=lambda key, value: self.preferences.update({key: copy.deepcopy(value)}))
        self.process = Mock(stdout=iter(['Build passed\n']))
        self.process.wait.return_value = 0
        self.process_patch = patch('metin2_studio.server.subprocess.Popen', return_value=self.process)
        self.build = self.process_patch.start()
        self.addCleanup(self.process_patch.stop)
        self.verify_patch = patch('metin2_studio.runtime_checks.verify', return_value={
            'issues': [], 'checkedFields': 0, 'questAccess': {'readable': True, 'detail': 'Verified'}})
        self.verify_patch.start()
        self.addCleanup(self.verify_patch.stop)

    def deployment(self, ident, status, payload):
        self.receipts.append((status, copy.deepcopy(payload)))
        if status == 'succeeded':
            self.pending.clear()

    def apply_pack(self, plan_id):
        # The server receipt must already be durable before any client write.
        if self.studio.job['kind'] == 'combined':
            self.assertEqual(self.receipts[-1][0], 'succeeded')
        return {'transaction': 'pack-transaction'}

    def start(self, **options):
        review = self.studio.apply_workflow.review()
        job = self.studio.apply_workflow.start({'reviewId': review['id'], **options})
        self.studio._apply_thread.join(5)
        self.assertFalse(self.studio._apply_thread.is_alive())
        return job

    def test_review_groups_saved_files_and_saved_addons_without_writes(self):
        review = self.studio.apply_workflow.review()
        self.assertTrue(review['server'])
        self.assertEqual(review['addons'], self.plan)
        self.assertEqual(review['files'], self.pending)
        self.service.post.assert_called_once_with('plan', {'addon_id': 'example', 'action': 'reapply'})
        self.build.assert_not_called()
        self.service.apply_reviewed.assert_not_called()

    def test_combined_apply_verifies_server_before_applying_addons_once(self):
        job = self.start()
        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(job['serverStatus'], 'succeeded')
        self.service.apply_reviewed.assert_called_once_with('pack-review')
        self.assertEqual(self.build.call_count, 1)
        self.assertEqual(self.preferences['lastApplyOperation']['addons']['status'], 'succeeded')
        self.assertEqual(self.pending, [])

    def test_addon_failure_preserves_successful_server_receipt(self):
        self.service.apply_reviewed.side_effect = ValueError('Client was opened after review')
        job = self.start()
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(job['serverStatus'], 'succeeded')
        self.assertEqual(self.receipts[-1][0], 'succeeded')
        self.assertEqual(self.pending, [])
        self.assertIn('Server changes were applied successfully', job['lines'][-1])

    def test_server_failure_does_not_start_addons_or_clear_saved_changes(self):
        self.process.wait.return_value = 1
        job = self.start()
        self.assertEqual(job['status'], 'failed')
        self.assertTrue(self.pending)
        self.assertEqual(job['addons']['status'], 'pending')
        self.service.apply_reviewed.assert_not_called()

    def test_stale_server_files_or_client_review_block_before_any_build(self):
        review = self.studio.apply_workflow.review()
        self.fingerprints['drops.txt'] = 'external-edit'
        with self.assertRaisesRegex(ValueError, 'changed since review'):
            self.studio.apply_workflow.start({'reviewId': review['id']})
        self.build.assert_not_called()
        review = self.studio.apply_workflow.review()
        self.service.check_review.side_effect = ValueError('Client files changed')
        with self.assertRaisesRegex(ValueError, 'Client files changed'):
            self.studio.apply_workflow.start({'reviewId': review['id']})
        self.build.assert_not_called()

    def test_addon_only_apply_does_not_require_docker_or_restart_server(self):
        self.studio.docker_status.side_effect = AssertionError('Docker must not be checked')
        job = self.start(includeServer=False)
        self.assertEqual(job['kind'], 'addons')
        self.assertEqual(job['status'], 'succeeded')
        self.assertTrue(self.pending)
        self.assertFalse(self.receipts)
        self.build.assert_not_called()
        self.studio.runtime_health.assert_not_called()

    def test_server_can_apply_with_addons_left_for_later(self):
        job = self.start(includeAddons=False)
        self.assertEqual(job['status'], 'succeeded')
        self.service.apply_reviewed.assert_not_called()

    def prepare_extension(self):
        self.plan.update(id='extension-mount-review', addon_id='community.legacy-mount-support',
                         name='Legacy Mount Support', kind='game-extension', action='install', server_required=True,
                         server_files=[{'path': 'quest/mounts_legacy.quest'}])
        self.service.stage_reviewed = Mock()
        self.service.server_applied = Mock()
        return self.studio.apply_workflow.review(self.plan['id'])

    def test_extension_review_requires_server_selection_before_any_write(self):
        review = self.prepare_extension()
        self.assertTrue(review['server'])
        self.assertIn('quest/mounts_legacy.quest', [row['path'] for row in review['files']])
        with self.assertRaisesRegex(ValueError, 'Select server files'):
            self.studio.apply_workflow.start({'reviewId': review['id'], 'includeServer': False})
        self.service.stage_reviewed.assert_not_called()
        self.build.assert_not_called()

    def test_extension_server_sources_are_staged_before_build_then_client_applies(self):
        review = self.prepare_extension()
        order = []
        self.service.stage_reviewed.side_effect = lambda key: order.append('save-server')
        self.service.server_applied.side_effect = lambda key: order.append('server-verified')
        original = self.service.apply_reviewed.side_effect
        self.service.apply_reviewed.side_effect = lambda key: (order.append('client'), original(key))[1]
        job = self.studio.apply_workflow.start({'reviewId': review['id']})
        self.studio._apply_thread.join(5)
        self.assertEqual(job['status'], 'succeeded', job['lines'])
        self.assertEqual(order, ['save-server', 'server-verified', 'client'])
        self.service.stage_reviewed.assert_called_once_with(self.plan['id'])

    def test_missing_optional_support_does_not_block_server_review(self):
        self.service.state.side_effect = ImportError('Install pack support')
        review = self.studio.apply_workflow.review()
        self.assertTrue(review['server'])
        self.assertIsNone(review['addons'])
        self.assertIn('Install pack support', review['addonError'])

    def test_disconnected_client_and_expired_explicit_addon_plan(self):
        self.service.state.return_value = {'integrity': None, 'installed': []}
        review = self.studio.apply_workflow.review()
        self.assertIsNone(review['addons'])
        self.assertIsNone(review['addonError'])
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.studio.apply_workflow.review('expired-plan')

    def test_review_is_consumed_and_cannot_dispatch_twice(self):
        review = self.studio.apply_workflow.review()
        self.studio.apply_workflow.start({'reviewId': review['id'], 'includeServer': False})
        self.studio._apply_thread.join(5)
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.studio.apply_workflow.start({'reviewId': review['id']})
        self.assertEqual(self.service.apply_reviewed.call_count, 1)

    def test_crash_between_server_and_addons_cannot_record_combined_success(self):
        self.studio.apply_workflow.record({'kind': 'combined', 'status': 'succeeded', 'finished': 42,
            'serverStatus': 'succeeded', 'addons': {'status': 'pending'}, 'lines': []})
        receipt = self.preferences['lastApplyOperation']
        self.assertEqual(receipt['status'], 'running')
        self.assertEqual(receipt['serverStatus'], 'succeeded')
        self.assertNotIn('finished', receipt)

    def prepare_selection(self, action='reapply'):
        rows = [{'id': 'one', 'name': 'First', 'version': '1.0', 'enabled': True},
                {'id': 'two', 'name': 'Second', 'version': '2.0', 'enabled': False}]
        self.plan.update(action=action, installed=rows, selected_addon_ids=['one', 'two'])
        if action == 'batch':
            self.plan['batch'] = [{**row, 'addon_id': row['id']} for row in rows]
        state = self.service.state.return_value
        state.update(installed=rows, installation={'path': 'fixture-client'})
        state['integrity']['pending_addon_ids'] = ['one', 'two']
        calls = []
        def plan(route, data):
            calls.append((route, copy.deepcopy(data)))
            ids = data.get('addon_ids', ['one', 'two'])
            value = {**self.plan, 'id': 'selection-' + str(len(calls)), 'selected_addon_ids': list(ids)}
            state['pending_plan'] = value
            return {'plan': value}
        self.service.post.side_effect = plan
        return calls

    def test_selection_review_can_apply_a_subset_clear_it_and_select_all_again(self):
        self.prepare_selection()
        workflow = self.studio.apply_workflow
        review = workflow.review()
        self.assertEqual(review['selectedAddonIds'], ['one', 'two'])
        selected = workflow.review(addon_ids=['two'], review_id=review['id'])
        self.assertEqual(selected['selectedAddonIds'], ['two'])
        self.assertEqual([row['id'] for row in selected['selectableAddons']], ['one', 'two'])
        self.assertEqual(selected['addons']['selected_addon_ids'], ['two'])
        empty = workflow.review(addon_ids=[], review_id=selected['id'])
        self.assertIsNone(empty['addons'])
        self.assertEqual(empty['selectedAddonIds'], [])
        self.assertEqual(len(empty['selectableAddons']), 2)
        all_again = workflow.review(addon_ids=['one', 'two'], review_id=empty['id'])
        self.assertEqual(all_again['selectedAddonIds'], ['one', 'two'])
        job = workflow.start({'reviewId': all_again['id'], 'includeServer': False})
        self.studio._apply_thread.join(5)
        self.assertEqual(job['status'], 'succeeded')
        self.service.apply_reviewed.assert_called_once_with(all_again['addons']['id'])

    def test_subset_review_rejects_unlisted_duplicate_and_stale_selection_ids(self):
        self.prepare_selection()
        workflow = self.studio.apply_workflow
        review = workflow.review()
        for ids in (['foreign'], ['one', 'one'], 'one', [None]):
            with self.subTest(ids=ids), self.assertRaisesRegex(ValueError, 'Select distinct'):
                workflow.review(addon_ids=ids, review_id=review['id'])
        chosen = workflow.review(addon_ids=['one'], review_id=review['id'])
        with self.assertRaisesRegex(ValueError, 'expired'):
            workflow.review(addon_ids=['two'], review_id=review['id'])
        with self.assertRaisesRegex(ValueError, 'expired'):
            workflow.start({'reviewId': review['id']})
        self.assertEqual(workflow.pending['public']['id'], chosen['id'])
        self.service.apply_reviewed.assert_not_called()

    def test_changing_addon_target_requires_a_new_selection_review(self):
        self.prepare_selection()
        workflow = self.studio.apply_workflow
        review = workflow.review()
        self.service.state.return_value['installation'] = {'path': 'other-client'}
        with self.assertRaisesRegex(ValueError, 'target changed'):
            workflow.review(addon_ids=['one'], review_id=review['id'])

    def test_explicit_batch_selection_uses_only_selected_catalog_packages(self):
        calls = self.prepare_selection('batch')
        workflow = self.studio.apply_workflow
        review = workflow.review(addon_plan_id=self.plan['id'])
        selected = workflow.review(addon_ids=['one'], review_id=review['id'])
        self.assertEqual(calls, [('plan/batch', {'addon_ids': ['one']})])
        self.assertEqual(selected['selectedAddonIds'], ['one'])
        self.assertEqual(len(selected['selectableAddons']), 2)
