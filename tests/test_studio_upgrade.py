import copy
import base64
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch, Mock

import tests.test_studio as test_studio
from metin2_studio.server import ACTIVE_CHANGESET, digest
from metin2_studio.studio_features import combined_drops, drop_index, table_plan, table_view, bulk_drop_plan, search


class UpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_studio.StudioTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        test_studio.StudioTests.tearDownClass.__func__(cls)

    def setUp(self):
        test_studio.StudioTests.setUp(self)
        with self.s.workspace.connect() as conn:
            conn.execute('DELETE FROM preferences')
        for name in ('_drop_hover_cache', '_item_usage_cache'):
            if hasattr(self.s, name):
                delattr(self.s, name)
        self.token = ACTIVE_CHANGESET.set(None)

    def tearDown(self):
        ACTIVE_CHANGESET.reset(self.token)

    def quest(self, **values):
        return dict(id='studio_new_exchange', title='Village supplies', intro='Bring supplies.', npc='9001', target='8001', reward='25041', quantity=1, kills=10, level=5, yang=100, exp=20, **values)

    def test_turnin_cooldown_inventory_guards_without_analytics_logging(self):
        _, code = self.s.quest_code(self.quest(template='exchange', requiredItem='30001', requiredCount=4, cooldown=3600))
        self.assertIn('pc.count_item(30001) < 4', code)
        self.assertIn('pc.remove_item(30001, 4)', code)
        self.assertNotIn('STUDIO_Q_ITEM', code)
        self.assertIn('pc.give_item2(25041, 1)', code)
        self.assertIn('get_time() + 3600', code)
        self.assertNotIn('state hunting begin', code)
        self.assertLess(code.index('pc.remove_item'), code.index('pc.give_item2'))

    def test_quest_library_round_trip_and_stale_edit(self):
        from metin2_studio.quest_templates import library
        body = self.quest(template='collection', requiredItem='30001', requiredCount=3)
        self.s.commit(self.s.quest_plan(body)['id'])
        row = next(row for row in library(self.s) if row['template'])
        changed = dict(row['template'], hash=row['hash'])
        changed['quantity'] = 2
        self.s.quest_plan(changed)
        with self.assertRaises(ValueError):
            self.s.quest_plan(dict(changed, hash='stale'))
        with self.assertRaises(ValueError):
            self.s.quest_plan(dict(changed, template='hunt'))

    def test_combined_groups_preserve_configured_parameters_not_final_chances(self):
        data = combined_drops(self.s, '8010')
        self.assertGreaterEqual(len(data['groups']), 2)
        self.assertTrue(any(len(row['path']) > 1 for row in data['rows']))
        self.assertIn('not a final', data['scope'])
        index = drop_index(self.s)
        self.assertTrue(any(row['contains'] for row in index['groups']))

    def test_guided_table_preserves_legacy_comments_and_crlf(self):
        file = self.s.locale / 'fishing.txt'
        original = b'\xb0\xa1\t27803 27833 27863 10 20 30 40 5 0 10 20 30 0 0 0 0 0 0 0 0 0 0\t# keep me\r\n'
        file.write_bytes(original)
        info = self.s.file(file.relative_to(self.s.root).as_posix())
        view = table_view(self.s, info)
        self.assertTrue(view['rows'][0]['valid'])
        plan = table_plan(self.s, {'id': info['id'], 'hash': info['hash'], 'edits': [{'line': 1, 'column': 4, 'value': '55'}]})
        new = self.s.plans[plan['id']]['files'][0][2]
        self.assertEqual(new, original.replace(b'10 20 30 40', b'55 20 30 40'))
        with self.assertRaises(ValueError):
            table_plan(self.s, {'id': info['id'], 'hash': 'stale', 'edits': []})
        file.unlink()

    def test_bulk_drop_edits_are_direct_and_keep_valid_200_parameter(self):
        group = self.s.group('mob-base', '8001 drop')
        item = next(row['item'] for row in group['entries'] if row['item'].isdigit())
        plan = bulk_drop_plan(self.s, {'item': item, 'field': 'prob', 'value': '200', 'groups': [{'source': 'mob-base', 'key': group['key']}]})
        self.assertIn('+', plan['files'][0]['diff'])
        self.assertIn('200', plan['files'][0]['diff'])

    def test_multi_file_set_publish_checks_all_sources_before_writing(self):
        ident = self.s.workspace.create_set({'name': 'Balance release'})['id']
        ACTIVE_CHANGESET.set(ident)
        group = self.s.group('mob-base', '8001 drop')
        group['entries'][0]['prob'] = '123'
        self.s.commit(self.s.drop_plan(group)['id'])
        settings = self.s.settings()
        self.s.commit(self.s.settings_plan({'hash': settings['hash'], 'values': {'M2_MAX_LEVEL': '119'}})['id'])
        ACTIVE_CHANGESET.set(None)
        plan = self.s.workspace.publish_plan(ident)
        self.assertEqual(len(plan['files']), 2)
        env = self.s.compose / '.env'
        env.write_bytes(env.read_bytes() + b'# outside\r\n')
        before = (self.s.locale / 'mob_drop_item.txt').read_bytes()
        with self.assertRaises(ValueError):
            self.s.commit(plan['id'])
        self.assertEqual((self.s.locale / 'mob_drop_item.txt').read_bytes(), before)

    def test_set_rebase_preserves_unrelated_updates(self):
        ident = self.s.workspace.create_set({'name': 'Staged edit'})['id']
        path = self.s.locale / 'blend.txt'
        path.write_bytes(b'value 50\nother 1\n')
        with self.s.workspace.connect() as conn:
            conn.execute('INSERT INTO staged VALUES (?,?,?,?,?)', (ident, path.relative_to(self.s.root).as_posix(), path.read_bytes(), b'value 100\nother 1\n', 'Edit'))
        path.write_bytes(b'value 80\nother 2\n')
        report = self.s.workspace.review_set(ident)
        self.assertEqual(report['conflicts'], 1)
        decisions = {choice['id']: 'keep' for row in report['files'] for choice in row['choices']}
        self.s.workspace.rebase_set({'id': report['id'], 'decisions': decisions})
        self.assertEqual(path.read_bytes(), b'value 80\nother 2\n')
        self.assertEqual(self.s.workspace.read(path, ident), b'value 100\nother 2\n')
        path.unlink()

    def test_preserved_draft_can_recover_its_cached_original_after_update(self):
        group = self.s.group('mob-base', '8001 drop')
        group['entries'][0]['prob'] = '123'
        self.s.workspace.save_draft({'id': 'draft', 'kind': 'drops', 'title': group['name'], 'payload': {'group': group}})
        file = self.s.locale / 'mob_drop_item.txt'
        file.write_bytes(file.read_bytes() + b'\n# incoming independent update\n')
        created = self.s.workspace.draft_to_set('draft')
        self.assertEqual(len(self.s.workspace.change_set(created['id'])['files']), 1)
        review = self.s.workspace.review_set(created['id'])
        self.s.workspace.rebase_set({'id': review['id'], 'decisions': {}})
        merged = self.s.workspace.read(file, created['id'])
        self.assertIn(b'# incoming independent update', merged)
        self.assertIn(b'123', merged)

    def test_build_fingerprint_ignores_native_derived_env_values(self):
        before = self.s.build_fingerprints()
        env = self.s.compose / '.env'
        env.write_bytes(env.read_bytes() + b'M2_INTERNAL_REVISION=999\r\n')
        self.assertEqual(before, self.s.build_fingerprints())
        env.write_bytes(env.read_bytes().replace(b'M2_MAX_LEVEL=120', b'M2_MAX_LEVEL=119'))
        self.assertNotEqual(before, self.s.build_fingerprints())

    def test_merged_files_matching_an_older_build_stay_pending_until_verified_apply(self):
        from metin2_studio.workspace import Workspace
        paths = [self.s.game / 'Dockerfile', self.s.game / '.dockerignore']
        originals = {path: path.read_bytes() for path in paths}
        custom = {path: raw + b'\n# Saved Studio integration\n' for path, raw in originals.items()}
        self.s.commit(self.s.plan('Custom build integration', custom, 'Fixture')['id'])
        self.s.workspace.deployment('previous-build', 'succeeded', {'files': self.s.build_fingerprints()})
        self.assertEqual(self.s.workspace.summary()['pending'], [])
        # The game launcher can build new package files without a Studio
        # deployment record. A later merge may restore byte-identical edits.
        for path, raw in originals.items():
            path.write_bytes(raw)
        report = self.s.workspace.scan()
        self.assertEqual(report['affectedFiles'], 2)
        review = self.s.workspace.reconcile_plan({'id': report['id']})
        self.s.commit(review['id'])
        expected = {path.relative_to(self.s.root).as_posix() for path in paths}
        self.assertEqual({row['path'] for row in self.s.workspace.summary()['pending']}, expected)
        self.s.workspace = Workspace(self.s)
        for status in ('validated', 'failed', 'unverified'):
            self.s.workspace.deployment('attempt-' + status, status, {'files': self.s.build_fingerprints()})
            self.assertEqual({row['path'] for row in self.s.workspace.summary()['pending']}, expected)
        # Only a successful deployment that includes the saved files clears them.
        self.s.workspace.deployment('verified-build', 'succeeded', {'files': self.s.build_fingerprints()})
        self.assertEqual(self.s.workspace.summary()['pending'], [])

    def test_accepting_game_values_without_file_writes_does_not_require_an_apply(self):
        path = self.s.game / 'Dockerfile'
        original = path.read_bytes()
        custom = original + b'\n# Saved Studio integration\n'
        self.s.commit(self.s.plan('Custom build integration', {path: custom}, 'Fixture')['id'])
        self.s.workspace.deployment('previous-build', 'succeeded', {'files': self.s.build_fingerprints()})
        path.write_bytes(original)
        report = self.s.workspace.scan()
        decisions = {choice['id']: 'update' for row in report['files'] for choice in row['choices']}
        review = self.s.workspace.reconcile_plan({'id': report['id'], 'decisions': decisions})
        self.assertEqual(review['files'], [])
        self.s.commit(review['id'])
        self.assertEqual(self.s.workspace.summary()['pending'], [])

    def test_validate_build_records_validation_without_restart(self):
        process = Mock(stdout=iter(['qc succeeded\n']))
        process.wait.return_value = 0
        self.s.job = {'status': 'running', 'lines': [], 'files': self.s.build_fingerprints(), 'id': 'validation-test'}
        with patch('metin2_studio.server.subprocess.Popen', return_value=process) as run:
            self.s.run_apply(True)
        self.assertEqual(self.s.job['status'], 'validated')
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ['docker','compose','build','game'])

    def test_native_pending_apply_uses_native_launcher_and_health(self):
        self.s.workspace.set_preference('nativeUpdatePending', {'ready': True})
        process = Mock(stdout=iter(['native build passed\n']))
        process.wait.return_value = 0
        self.s.job = {'status': 'running', 'lines': [], 'files': self.s.build_fingerprints(), 'id': 'native-test'}
        with patch('metin2_studio.server.subprocess.Popen', return_value=process) as run, patch.object(self.s, 'runtime_health', return_value={'gameHealthy': True}), patch('metin2_studio.runtime_checks.verify_quest_access', return_value={'readable': True, 'detail': 'Quest state files readable: 230'}):
            self.s.run_apply()
        self.assertEqual(self.s.job['status'], 'succeeded')
        self.assertIn('Metin2-Launcher.ps1', ' '.join(run.call_args.args[0]))
        self.assertFalse(self.s.workspace.preference('nativeUpdatePending'))

    def test_game_update_can_run_with_custom_merge_pending_and_without_native_overrides(self):
        path = self.s.sources['mob-base'][0]
        base = b'Group fixture\n{\n Type drop\n Mob 8001\n 1 25041 1 50\n}\n'
        custom, incoming = base.replace(b'1 50', b'1 100'), base.replace(b'1 50', b'1 80')
        path.write_bytes(custom)
        self.s.workspace.record_commit([(path, base, custom)], 'Custom', 'backup')
        path.write_bytes(incoming)
        report = self.s.workspace.scan()
        self.s.commit(self.s.workspace.defer_plan({'id': report['id']})['id'])
        self.assertEqual(path.read_bytes(), incoming)
        with self.assertRaisesRegex(ValueError, 'pending custom merge'):
            self.s.plan('Unrelated new edit in same file', {path: b'value 70\n'}, 'Review')
        self.s.workspace.set_preference('nativeUpdatePending', {'ready': True})
        with patch.object(self.s, 'docker_status', return_value={'available': True}), patch('metin2_studio.server.threading.Thread'), patch.object(self.s.native_crafting, 'preflight', side_effect=AssertionError('A native custom review must not gate the game update')):
            self.s.apply()
        process = Mock(stdout=iter(['native build passed\n']))
        process.wait.return_value = 0
        with patch('metin2_studio.server.subprocess.Popen', return_value=process) as run, patch.object(self.s, 'runtime_health', return_value={'gameHealthy': True}), patch('metin2_studio.runtime_checks.verify_quest_access', return_value={'readable': True, 'detail': 'Readable'}), patch('metin2_studio.runtime_checks.subprocess.run', side_effect=AssertionError('Deferred drops are not deployed custom overrides')), patch.object(self.s.native_crafting, 'config', return_value={'recipes': {'1': 'saved custom recipe'}}), patch.object(self.s.native_crafting, 'apply', side_effect=AssertionError('Do not reapply native overrides during the game update')):
            self.s.run_apply()
        self.assertEqual(self.s.job['status'], 'succeeded')
        self.assertEqual(self.s.job['runtime']['checkedFields'], 0)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(self.s.workspace.summary()['pendingMerges'], [path.relative_to(self.s.root).as_posix()])
        self.assertEqual(self.s.workspace.scan()['affectedFiles'], 1)
        self.assertEqual(path.read_bytes(), incoming)
        path.unlink()

    def test_healthy_container_with_unreadable_quests_is_not_successful(self):
        self.s.workspace.set_preference('nativeUpdatePending', {'ready': True})
        process = Mock(stdout=iter(['native build passed\n']))
        process.wait.return_value = 0
        self.s.job = {'status': 'running', 'lines': [], 'files': self.s.build_fingerprints(), 'id': 'quest-access-test'}
        with patch('metin2_studio.server.subprocess.Popen', return_value=process), patch.object(self.s, 'runtime_health', return_value={'gameHealthy': True}), patch('metin2_studio.runtime_checks.verify_quest_access', return_value={'readable': False, 'issue': 'Quest files are not readable by the game account.'}):
            self.s.run_apply()
        self.assertEqual(self.s.job['status'], 'unverified')
        self.assertFalse(self.s.job['runtime']['questAccess']['readable'])
        self.assertTrue(self.s.workspace.preference('nativeUpdatePending'))

    def test_adopt_existing_edit_tracks_only_reviewed_backup_diff(self):
        path = self.s.locale / 'blend.txt'
        path.write_bytes(b'value 100\nother 1\n')
        original = b'value 50\nother 1\n'
        plan = self.s.workspace.adopt_plan({'path': path.relative_to(self.s.root).as_posix(), 'original': base64.b64encode(original).decode()})
        self.assertEqual(self.s.plans[plan['id']]['files'], [])
        self.s.commit(plan['id'])
        self.assertEqual(path.read_bytes(), b'value 100\nother 1\n')
        path.write_bytes(b'value 80\nother 2\n')
        report = self.s.workspace.scan()
        self.assertEqual(report['conflicts'], 1)
        self.assertEqual(report['files'][0]['choices'][0]['custom'], '100')
        path.unlink()

    def test_adopt_settings_redacts_credentials_and_preserves_current_fingerprint(self):
        current = (self.s.compose / '.env').read_bytes()
        original = current.replace(b'M2_MAX_LEVEL=120', b'M2_MAX_LEVEL=119').replace(b'test-private-value', b'old-private-secret')
        plan = self.s.workspace.adopt_plan({'path': 'linux-port/docker/.env', 'original': base64.b64encode(original).decode()})
        self.assertNotIn('private', json.dumps(plan))
        self.s.commit(plan['id'])
        self.assertEqual(self.s.workspace.tracked()[0]['expected'], current)
        self.assertEqual(self.s.workspace.scan()['affectedFiles'], 0)

    def test_runtime_drop_check_detects_override_of_only_custom_fields(self):
        from metin2_studio.runtime_checks import compare_groups
        group = self.s.group('mob-base', '8001 drop')
        file = self.s.locale / 'mob_drop_item.txt'
        original = file.read_bytes()
        entry = next(row for row in group['entries'] if row['item'].isdigit())
        entry['prob'] = '123'
        plan = self.s.drop_plan(group)
        desired = self.s.plans[plan['id']]['files'][0][2]
        count, issues = compare_groups(self.s.dt, 'mob_drop_item.txt', original, desired, desired + b'\n# unrelated runtime content\n')
        self.assertGreater(count, 0)
        self.assertEqual(issues, [])
        _, issues = compare_groups(self.s.dt, 'mob_drop_item.txt', original, desired, original)
        self.assertTrue(issues)

    def test_publishing_rebased_work_cannot_silently_replace_prior_custom_intent(self):
        path = self.s.locale / 'blend.txt'
        path.write_bytes(b'scroll 50\npotion 1\n')
        self.s.commit(self.s.plan('Custom scroll', {path:b'scroll 100\npotion 1\n'}, '')['id'])
        ident = self.s.workspace.create_set({'name':'Potion change'})['id']
        with self.s.workspace.connect() as conn:
            conn.execute('INSERT INTO staged VALUES (?,?,?,?,?)',(ident,path.relative_to(self.s.root).as_posix(),path.read_bytes(),b'scroll 100\npotion 2\n','Potion'))
        path.write_bytes(b'scroll 80\npotion 1\n')
        report = self.s.workspace.review_set(ident)
        self.s.workspace.rebase_set({'id':report['id'],'decisions':{}})
        with self.assertRaises(ValueError):
            self.s.workspace.publish_plan(ident)
        self.assertEqual(self.s.workspace.tracked()[0]['custom'],b'scroll 100\npotion 1\n')
        path.unlink()

    def test_new_edit_adopts_unrelated_upstream_values_as_its_correct_original(self):
        path = self.s.locale / 'blend.txt'
        path.write_bytes(b'scroll 50\npotion 1\n')
        self.s.commit(self.s.plan('Scroll', {path:b'scroll 100\npotion 1\n'}, '')['id'])
        path.write_bytes(b'scroll 100\npotion 2\n')
        self.s.commit(self.s.plan('Potion', {path:b'scroll 100\npotion 3\n'}, '')['id'])
        record = self.s.workspace.tracked()[0]
        self.assertEqual(record['original'], b'scroll 50\npotion 2\n')
        self.assertEqual(record['custom'], b'scroll 100\npotion 3\n')
        path.unlink()

    def test_external_native_pending_marker_selects_the_full_stack_path(self):
        marker = self.s.root / '.m2launcher-rebuild-pending'
        marker.write_text('pending')
        try:
            self.assertEqual(self.s.native_pending(), {'ready': True, 'external': True})
            self.assertTrue(self.s.workspace.summary()['preferences']['nativeUpdatePending']['external'])
        finally:
            marker.unlink()
