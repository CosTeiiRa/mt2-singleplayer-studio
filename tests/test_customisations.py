import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from merge_custom import merge, rebase_original, minimal_numeric_edit
from workspace import Workspace, EnvMerge


class ThreeWayTests(unittest.TestCase):
    def test_scroll_100_custom_80_update_requires_only_that_choice(self):
        base = b'scroll 25041 1 50\nmaterial 30010 1 5\n'
        ours = b'scroll 25041 1 100\nmaterial 30010 1 5\n'
        incoming = b'scroll 25041 1 80\nmaterial 30010 1 25\nnew 30027 1 15\n'
        result = merge(base, ours, incoming)
        self.assertEqual(len(result.choices), 1)
        choice = result.choices[0]
        self.assertTrue(choice.conflict)
        self.assertEqual((choice.base, choice.custom, choice.incoming), (b'50', b'100', b'80'))
        with self.assertRaises(ValueError):
            result.resolve()
        self.assertEqual(result.resolve({choice.ident: 'keep'}), b'scroll 25041 1 100\nmaterial 30010 1 25\nnew 30027 1 15\n')
        self.assertEqual(result.resolve({choice.ident: 'update'}), incoming)

    def test_unrelated_fields_on_same_row_merge_without_conflict(self):
        result = merge(b'1\t25041\t1\t50\r\n', b'1\t25041\t1\t100\r\n', b'1\t25041\t2\t50\r\n')
        self.assertFalse(any(piece.conflict for piece in result.choices))
        self.assertEqual(result.resolve(), b'1\t25041\t2\t100\r\n')

    def test_update_already_contains_custom_value_needs_no_review(self):
        result = merge(b'1 50\n2 10\n', b'1 100\n2 10\n', b'1 100\n2 80\n')
        self.assertEqual(result.choices, [])
        self.assertEqual(result.resolve(), b'1 100\n2 80\n')

    def test_new_files_deletions_and_colliding_insertions_are_conservative(self):
        self.assertEqual(merge(None, b'quest', None).resolve(), b'quest')
        conflict = merge(None, b'our quest', b'new package quest')
        self.assertTrue(conflict.choices[0].conflict)
        self.assertEqual(conflict.resolve({conflict.choices[0].ident: 'update'}), b'new package quest')
        deletion = merge(b'old\n', None, b'updated\n')
        self.assertTrue(deletion.choices[0].conflict)
        self.assertIsNone(deletion.resolve({deletion.choices[0].ident: 'keep'}))
        self.assertEqual(merge(b'old\n', None, b'old\n').resolve(), None)
        inserts = merge(b'a\nc\n', b'a\nours\nc\n', b'a\nupdate\nc\n')
        self.assertTrue(any(piece.conflict for piece in inserts.choices))

    def test_rebase_keeps_intent_even_when_upstream_happens_to_equal_custom(self):
        base, ours = b'x 50\ny 1\n', b'x 100\ny 1\n'
        self.assertEqual(rebase_original(base, ours, b'x 80\ny 2\n'), b'x 80\ny 2\n')
        self.assertEqual(rebase_original(base, ours, b'x 100\ny 2\n'), b'x 50\ny 2\n')
        rebased = rebase_original(base, ours, b'x 100\ny 2\n')
        future = merge(rebased, b'x 100\ny 2\n', b'x 90\ny 3\n')
        self.assertTrue(any(piece.conflict for piece in future.choices))

    def test_renderer_comments_and_spacing_are_not_custom_overrides(self):
        base = b'Group old_name\r\n{\r\n\tMob 8001\r\n\tType drop\r\n\t1 25041 1 50 #--# old label\r\n}\r\n'
        rendered = b'Group studio_8001\n{\n Mob 8001\n Type drop\n 1\t25041\t1\t100 #--# new label\n}\n'
        minimal = minimal_numeric_edit(base, rendered)
        self.assertEqual(minimal, base.replace(b'1 50 #', b'1 100 #'))
        self.assertEqual(len(merge(base, minimal, base.replace(b'1 50 #', b'1 80 #')).choices), 1)

    def test_byte_and_unicode_preservation(self):
        base = b'#\xa1\xb2\r\nitem 1 50\r\nend\r\n'
        ours, upstream = base.replace(b'50', b'100'), base.replace(b'end', b'new\r\nend')
        self.assertEqual(merge(base, ours, upstream).resolve(), upstream.replace(b'50', b'100'))

    def test_independent_custom_choices_keep_unrelated_update(self):
        base = b'a 1\nb 2\nc 3\n'
        result = merge(base, b'a 10\nb 20\nc 3\n', b'a 11\nb 22\nc 30\n')
        conflicts = [piece for piece in result.choices if piece.conflict]
        self.assertEqual(len(conflicts), 2)
        choices = {piece.ident: 'keep' if piece.custom == b'10' else 'update' for piece in conflicts}
        self.assertEqual(result.resolve(choices), b'a 10\nb 22\nc 30\n')

    def test_env_only_exposes_allowlisted_keys_and_preserves_credentials(self):
        before = b'\xef\xbb\xbfSECRET=private\r\nM2_DIFFICULTY=easy\r\nOTHER=1\r\n'
        ours = before.replace(b'easy', b'custom')
        incoming = before.replace(b'private', b'new-password').replace(b'easy', b'hard').replace(b'OTHER=1', b'OTHER=2')
        result = EnvMerge(before, ours, incoming, {'M2_DIFFICULTY': {}}, 'env')
        self.assertEqual(len(result.choices), 1)
        self.assertEqual(result.choices[0].context, 'M2_DIFFICULTY')
        self.assertNotIn('password', repr(result.choices))
        self.assertEqual(result.resolve({result.choices[0].ident: 'keep'}), incoming.replace(b'hard', b'custom'))


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.test_runs = Path(__file__).resolve().parents[1] / 'data' / 'test-runs'
        self.test_runs.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.test_runs)
        self.root = Path(self.temp.name) / 'game'
        self.root.mkdir()
        self.state = Path(self.temp.name) / 'state'
        self.state.mkdir()
        self.studio = SimpleNamespace(root=self.root, state=self.state, settings_schema={'M2_DIFFICULTY': {}})
        self.studio.safe = lambda path: Path(path).resolve() if Path(path).resolve().is_relative_to(self.root) else self.fail('Unsafe path')
        self.workspace = Workspace(self.studio)

    def tearDown(self):
        assert Path(self.temp.name).resolve().is_relative_to(self.test_runs.resolve())
        self.temp.cleanup()

    def test_drafts_survive_reopening_and_never_write_game_files(self):
        value = {'id': 'drops:8001', 'kind': 'drops', 'title': 'Metin', 'payload': {'prob': '100'}}
        self.workspace.save_draft(value)
        reopened = Workspace(self.studio)
        self.assertEqual(reopened.drafts('drops:8001')['payload'], {'prob': '100'})
        self.assertEqual(list(self.root.iterdir()), [])
        reopened.remove_draft('drops:8001')
        self.assertEqual(reopened.drafts(), [])

    def test_two_edits_in_one_changeset_use_overlay_and_retain_original(self):
        path = self.root / 'table.txt'
        path.write_bytes(b'a 1\nb 2\n')
        ident = self.workspace.create_set({'name': 'Scroll economy'})['id']
        self.workspace.stage({'changeset': ident, 'title': 'First edit', 'files': [(path, b'a 1\nb 2\n', b'a 10\nb 2\n')]})
        self.assertEqual(self.workspace.read(path, ident), b'a 10\nb 2\n')
        self.workspace.stage({'changeset': ident, 'title': 'Second edit', 'files': [(path, b'a 10\nb 2\n', b'a 10\nb 20\n')]})
        self.assertEqual(path.read_bytes(), b'a 1\nb 2\n')
        with self.workspace.connect() as conn:
            row = conn.execute('SELECT * FROM staged').fetchone()
        self.assertEqual(row['original'], b'a 1\nb 2\n')
        self.assertEqual(row['content'], b'a 10\nb 20\n')
        with self.assertRaisesRegex(ValueError, 'changed since review'):
            self.workspace.stage({'changeset': ident, 'title': 'Stale', 'files': [(path, b'a 1\nb 2\n', b'bad')]})

    def test_scan_only_reports_affected_custom_values_and_stale_review_rejected(self):
        path = self.root / 'table.txt'
        base, ours = b'a 50\nb 1\n', b'a 100\nb 1\n'
        path.write_bytes(ours)
        self.workspace.record_commit([(path, base, ours)], 'Custom scroll', 'backup')
        self.assertEqual(self.workspace.scan()['files'], [])
        path.write_bytes(b'a 100\nb 99\n')
        self.assertEqual(self.workspace.scan()['files'], [])
        path.write_bytes(b'a 80\nb 99\n')
        report = self.workspace.scan()
        self.assertEqual(report['affectedFiles'], 1)
        choice = report['files'][0]['choices'][0]
        self.assertEqual(choice['custom'], '100')
        self.assertEqual(choice['incoming'], '80')
        _, changes, rebased = self.workspace.reconciliation({'id': report['id'], 'decisions': {choice['id']: 'keep'}})
        self.assertEqual(changes[path], b'a 100\nb 99\n')
        self.assertEqual(rebased['table.txt'][0], b'a 80\nb 99\n')
        self.assertEqual(rebased['table.txt'][1], b'a 100\nb 99\n')
        path.write_bytes(b'a 70\nb 99\n')
        with self.assertRaisesRegex(ValueError, 'changed since this review'):
            self.workspace.reconciliation({'id': report['id'], 'decisions': {choice['id']: 'keep'}})

    def test_accepting_upstream_can_remove_custom_intent_without_file_rewrite(self):
        path = self.root / 'table.txt'
        base, ours, incoming = b'x 50\n', b'x 100\n', b'x 80\n'
        path.write_bytes(ours)
        self.workspace.record_commit([(path, base, ours)], 'Change', 'backup')
        path.write_bytes(incoming)
        report = self.workspace.scan()
        choice = report['files'][0]['choices'][0]
        _, changes, rebased = self.workspace.reconciliation({'id': report['id'], 'decisions': {choice['id']: 'update'}})
        self.assertEqual(changes, {})
        self.workspace.record_commit([], 'Accept update', 'backup2', {'reconciled': rebased})
        self.assertEqual(self.workspace.tracked(), [])

    def test_deferred_merge_survives_restart_and_can_be_chosen_later(self):
        path = self.root / 'table.txt'
        base, custom, incoming = b'a 50\nb 1\n', b'a 100\nb 1\n', b'a 80\nb 99\n'
        path.write_bytes(incoming)
        self.workspace.record_commit([], 'Update first', 'archive', {'deferred': {'table.txt': (base, custom, incoming, 'old-version')}})
        self.workspace = Workspace(self.studio)
        self.assertEqual(self.workspace.deferred_paths(), {'table.txt'})
        self.assertEqual(self.workspace.tracked(active_only=True), [])
        self.assertEqual(self.workspace.scan(include_deferred=False)['affectedFiles'], 0)
        report = self.workspace.scan()
        self.assertEqual(report['priority'], 'merge')
        self.assertTrue(report['files'][0]['deferred'])
        # Default conflict decision leaves the game value in place.
        self.assertEqual(self.workspace.reconciliation({'id': report['id']})[1], {})
        choice = report['files'][0]['choices'][0]
        _, changes, rebased = self.workspace.reconciliation({'id': report['id'], 'decisions': {choice['id']: 'keep'}})
        self.assertEqual(path.read_bytes(), incoming)  # Preview is read only.
        self.assertEqual(changes[path], b'a 100\nb 99\n')
        path.write_bytes(changes[path])
        self.workspace.record_commit([(path, incoming, changes[path])], 'Chosen merge', 'merge-backup', {'reconciled': rebased})
        self.assertEqual(self.workspace.deferred_paths(), set())
        self.assertEqual(self.workspace.tracked()[0]['original'], incoming)
        self.assertEqual(self.workspace.scan()['affectedFiles'], 0)

    def test_deferral_keeps_all_three_versions_without_writing_game_files(self):
        path = self.root / 'table.txt'
        base, custom, incoming = b'x 50\n', b'x 100\n', b'x 80\n'
        path.write_bytes(custom)
        self.workspace.record_commit([(path, base, custom)], 'Custom', 'backup')
        path.write_bytes(incoming)
        self.studio.plan = lambda title, changes, hint, **kwargs: {'title': title, 'changes': changes, **kwargs}
        report = self.workspace.scan()
        plan = self.workspace.defer_plan({'id': report['id']})
        self.assertEqual(plan['changes'], {})
        self.assertEqual(path.read_bytes(), incoming)
        self.workspace.record_commit([], plan['title'], 'deferred', plan['metadata'])
        record = self.workspace.tracked()[0]
        self.assertEqual((record['original'], record['custom'], record['expected']), (base, custom, incoming))
        self.assertEqual(self.workspace.scan(include_deferred=False)['affectedFiles'], 0)
        with self.assertRaisesRegex(ValueError, 'tracking changed'):
            self.workspace.reconciliation({'id': report['id']})

    def test_unsupported_draft_types_and_other_installation_are_rejected(self):
        with self.assertRaises(ValueError):
            self.workspace.save_draft({'id': 'a', 'kind': 'credentials', 'payload': {}})
        other = SimpleNamespace(root=self.root / 'other', state=self.state)
        with self.assertRaisesRegex(ValueError, 'another installation'):
            Workspace(other)
