from pathlib import Path
import json
import sys
import unittest

import tests.test_studio as test_studio
from metin2_studio.server import ACTIVE_CHANGESET
from metin2_studio.quest_templates import library
from metin2_studio.quest_support import quest_name


class QuestMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_studio.StudioTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        test_studio.StudioTests.tearDownClass.__func__(cls)

    def setUp(self):
        test_studio.StudioTests.setUp(self)
        self.token = ACTIVE_CHANGESET.set(None)
        self.source = self.s.game / 'quest/menu_story.quest'
        self.source.parent.mkdir(parents=True, exist_ok=True)
        self.raw = b'quest original_story begin\n state start begin\n  when 9001.chat."Hello" begin\n   pc.setqf("count", 20)\n  end\n end\nend\n'
        self.source.write_bytes(self.raw)
        self.rel = self.source.relative_to(self.s.root).as_posix()

    def tearDown(self):
        self.source.unlink(missing_ok=True)
        ACTIVE_CHANGESET.reset(self.token)

    def review(self, path=None):
        path = path or self.source
        current = self.s.file(path.relative_to(self.s.root).as_posix())
        return self.s.file_plan({**current, 'text': current['text'].replace('20', '30')})

    def test_native_review_preserves_source_and_registers_exact_build_input(self):
        plan = self.review()
        self.assertEqual(self.source.read_bytes(), self.raw)
        pending = {path.relative_to(self.s.game).as_posix(): raw for path, _, raw in self.s.plans[plan['id']]['files']}
        self.assertEqual(len(pending), 4)
        self.assertIn('quest/menu_story.quest', pending)
        self.assertIn(b'quest/menu_story.quest', pending['custom-quests/studio-source-list.txt'])
        dockerfile = pending['Dockerfile'].decode()
        copy = next(line for line in dockerfile.splitlines() if line.startswith('COPY ["quest/menu_story.quest"'))
        self.assertEqual(json.loads(copy[5:])[0], 'quest/menu_story.quest')
        self.assertEqual(json.loads(copy[5:])[1], '/studio-edited/original_story.quest')
        self.assertIn('object/state/$quest_name', dockerfile)
        self.assertIn('-name "original_story.*"', dockerfile)
        self.assertLess(dockerfile.index('# SERVER-STUDIO EDITED QUEST CLEANUP'), dockerfile.index('COPY --from=quests'))
        self.assertIn('find object -type f', dockerfile)
        self.assertIn(b'!quest/menu_story.quest', pending['.dockerignore'])
        self.assertEqual(quest_name(pending['quest/menu_story.quest']), 'original_story')

    def test_native_staleness_and_identity_changes_are_rejected(self):
        current = self.s.file(self.rel)
        with self.assertRaisesRegex(ValueError, 'File changed'):
            self.s.file_plan({**current, 'hash':'old', 'text':current['text'].replace('20','30')})
        with self.assertRaisesRegex(ValueError, 'existing quest name'):
            self.s.file_plan({**current, 'text':current['text'].replace('original_story','another_story')})

    def test_source_copies_group_and_registered_copy_takes_precedence(self):
        other = self.s.locale / 'quest/quest/menu_copy.quest'
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_bytes(self.raw)
        try:
            row = next(row for row in library(self.s) if row['questName']=='original_story')
            self.assertEqual(row['id'], self.rel)
            self.assertEqual(len(row['otherSources']), 1)
            self.s.commit(self.review(other)['id'])
            row = next(row for row in library(self.s) if row['questName']=='original_story')
            self.assertEqual(row['id'], other.relative_to(self.s.root).as_posix())
            self.assertTrue(row['compileRegistered'])
            with self.assertRaisesRegex(ValueError, 'already has an edited source'):
                self.review()
        finally:
            other.unlink()

    def test_native_source_custom_diffs_can_be_explicitly_merged_after_update(self):
        self.s.commit(self.review()['id'])
        tracked = next(row for row in self.s.workspace.tracked() if row['path']==self.rel)
        self.assertEqual(tracked['original'], self.raw)
        self.source.write_bytes(self.raw.replace(b'20',b'25') + b'\n-- unrelated upstream update\n')
        report = self.s.workspace.scan()
        decisions = {choice['id']:'keep' for row in report['files'] for choice in row['choices']}
        self.s.commit(self.s.workspace.reconcile_plan({'id':report['id'],'decisions':decisions})['id'])
        self.assertIn(b'count", 30', self.source.read_bytes())
        self.assertIn(b'-- unrelated upstream update', self.source.read_bytes())

    def test_new_staged_quest_is_visible_only_in_its_working_set(self):
        ident = self.s.workspace.create_set({'name':'New adventure'})['id']
        ACTIVE_CHANGESET.set(ident)
        body = dict(id='studio_menu_adventure',title='A staged quest',intro='Hello.',npc='9001',target='8001',reward='25041',quantity=1,kills=10,level=5,yang=100,exp=20)
        self.s.commit(self.s.quest_plan(body)['id'])
        row = next(row for row in library(self.s) if row['questName']==body['id'])
        self.assertTrue(row['staged'])
        self.assertEqual(row['editMode'], 'builder')
        ACTIVE_CHANGESET.set(None)
        self.assertFalse(any(row['questName']==body['id'] for row in library(self.s)))
