"""Regressions for restored quests without opening writes to engine/client code."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import tests.test_studio as test_studio
from metin2_studio.server import ACTIVE_CHANGESET


class QuestSupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_studio.StudioTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        test_studio.StudioTests.tearDownClass.__func__(cls)

    def setUp(self):
        test_studio.StudioTests.setUp(self)
        self.token = ACTIVE_CHANGESET.set(None)

    def tearDown(self):
        ACTIVE_CHANGESET.reset(self.token)

    def body(self):
        return dict(id='studio_restore_test', title='Village supplies', intro='Bring supplies.',
                    template='exchange', npc='9001', target='8001', requiredItem='30001',
                    requiredCount=3, reward='25041', quantity=1, kills=10, level=5,
                    yang=100, exp=20, cooldown=3600)

    def test_existing_lua_data_can_be_reviewed_but_binaries_cannot(self):
        path = self.s.locale / 'quest/libs/crafting/crafting_data.lua'
        info = self.s.file(path.relative_to(self.s.root).as_posix())
        plan = self.s.file_plan({**info, 'text': info['text'] + '\n-- reviewed change\n'})
        self.assertEqual(len(plan['files']), 1)
        for path in (self.s.game / 'bin/game', self.s.root / 'Metin2.exe', self.s.game / 'scripts/m2-render-config'):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'read-only'):
                self.s.plan('Not quest content', {path: b'new binary'}, '')

    def test_environment_keeps_internal_values_and_rejects_expressions(self):
        env = self.s.compose / '.env'
        before = env.read_bytes()
        for after in (before.replace(b'test-private-value', b'changed'),
                      b'M2_MAX_LEVEL=' + bytes([36]) + b'(command)\r\n' + before,
                      before + b'run_extra_code\r\n',
                      before.replace(b'M2_MAX_LEVEL=120', b'M2_MAX_LEVEL=121')):
            with self.subTest(after=after), self.assertRaises(ValueError):
                self.s.plan('Unsafe environment', {env: after}, '')
        self.assertEqual(env.read_bytes(), before)
        self.s.plan('Valid setting', {env: before.replace(b'M2_MAX_LEVEL=120', b'M2_MAX_LEVEL=119')}, '')

    def test_preserved_quest_draft_recovers_to_staged_files(self):
        self.s.workspace.save_draft({'id':'old-quest', 'kind':'quests', 'title':'Village supplies', 'payload':{'quest':self.body()}})
        recovered = self.s.workspace.draft_to_set('old-quest')
        files = self.s.workspace.change_set(recovered['id'])['files']
        self.assertEqual(len(files), 3)
        self.assertTrue(any(row['path'].endswith('studio_restore_test.quest') for row in files))
        self.assertFalse((self.s.game / 'custom-quests/studio_restore_test.quest').exists())

    def test_explicit_later_merge_can_restore_custom_hook_and_keep_game_changes(self):
        dockerfile = self.s.game / 'Dockerfile'
        original = dockerfile.read_bytes()
        self.s.commit(self.s.quest_plan(self.body())['id'])
        dockerfile.write_bytes(original + b'\n# native package update\n')
        report = self.s.workspace.scan()
        plan = self.s.workspace.reconcile_plan({'id':report['id'], 'decisions':{}})
        self.s.commit(plan['id'])
        self.assertIn(b'# SERVER-STUDIO CUSTOM QUESTS', dockerfile.read_bytes())
        self.assertIn(b'# native package update', dockerfile.read_bytes())
