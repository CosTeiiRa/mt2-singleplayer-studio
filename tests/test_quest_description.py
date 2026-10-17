from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_studio
import test_quest_fields
from quest_description import describe
from server import ACTIVE_CHANGESET


class QuestDescriptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_quest_fields.QuestFieldsTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        test_studio.StudioTests.tearDownClass.__func__(cls)

    def setUp(self):
        test_studio.StudioTests.setUp(self)
        self.token=ACTIVE_CHANGESET.set(None)

    def tearDown(self):
        (self.s.game/'quest/help_story.quest').unlink(missing_ok=True)
        ACTIVE_CHANGESET.reset(self.token)

    def help(self,rel):
        return describe(self.s,(self.s.game/rel).relative_to(self.s.root).as_posix())

    def test_hunt_preview_uses_actual_template_values(self):
        body=dict(id='studio_help_hunt',title='Village hunt',intro='Please help.',npc='9001',returnNpc='9002',target='8001',kills=25,level=10,reward='25040',quantity=2,yang=5000,exp=10000,cooldown=3600)
        self.s.commit(self.s.quest_plan(body)['id'])
        help=self.help('custom-quests/studio_help_hunt.quest');facts=dict(help['facts'])
        self.assertEqual(help['title'],'Village hunt')
        self.assertIn('25 × Metin of Sorrow',facts['Objective'])
        self.assertIn('2 ×',facts['Rewards'])
        self.assertIn('5,000 Yang',facts['Rewards'])
        self.assertIn('1 hour',facts['Repeat'])
        self.assertNotEqual(facts['Start NPC'],facts['Return to'])

    def test_staged_turnin_help_is_scoped_and_does_not_write_game_files(self):
        ident=self.s.workspace.create_set({'name':'Quest help check'})['id'];ACTIVE_CHANGESET.set(ident)
        body=dict(id='studio_help_turnin',title='Material exchange',intro='Trade.',template='exchange',npc='9001',target='8001',requiredItem='30001',requiredCount=3,reward='25040',quantity=1,level=5,yang=0,exp=0,cooldown=0)
        self.s.commit(self.s.quest_plan(body)['id'])
        help=self.help('custom-quests/studio_help_turnin.quest');facts=dict(help['facts'])
        self.assertIn('consumed',facts['Turn in'])
        self.assertEqual(facts['Repeat'],'Once per character')
        self.assertFalse((self.s.game/'custom-quests/studio_help_turnin.quest').exists())
        ACTIVE_CHANGESET.set(None)
        with self.assertRaisesRegex(ValueError,'missing'):self.help('custom-quests/studio_help_turnin.quest')

    def test_biologist_links_objective_items_and_shared_completion_rewards(self):
        source=self.s.game/'quest/collect_quest_lv30.quest';before=source.read_bytes()
        facts=dict(self.help('quest/collect_quest_lv30.quest')['facts'])
        self.assertEqual(facts['Objective'],'10 successful submissions')
        self.assertEqual(facts['Submission success'],'60%')
        self.assertIn('Orc Tooth',facts['Required / quest-drop items'])
        self.assertIn('50109',facts['Completion rewards'])
        self.assertIn('Movement speed +10',facts['Completion rewards'])
        self.assertIn('inactive',facts['Shared waiting time'])
        self.assertEqual(source.read_bytes(),before)
        helper=self.s.game/'quest/m2_biologist.lua'
        helper.write_bytes(helper.read_bytes().replace(b'pc.give_item2(50109)',b'pc.give_item2(25040)'))
        self.assertIn('25040',dict(self.help('quest/collect_quest_lv30.quest')['facts'])['Completion rewards'])

    def test_hunting_explains_alternative_targets_and_percentage_exp(self):
        help=self.help('share/locale/poland/quest/quest/systems/hunting.quest');facts=dict(help['facts'])
        self.assertEqual(facts['Progression'],'79 stages · levels 2–80')
        self.assertIn(' OR ',facts['First stage · choose one'])
        self.assertIn('30% EXP',facts['First-stage rewards'])
        self.assertTrue(any('Later stages' in n for n in help['notes']))

    def test_database_rewards_and_comment_examples_are_not_claimed_as_direct_rewards(self):
        path=self.s.game/'quest/help_story.quest'
        path.write_text('''quest main_quest_lv3 begin
 state start begin
  when 9001.chat."Hello" begin
   -- pc.give_item2(25040, 99)
   say("pc.give_item2(25040, 99)")
   give_reward("main_quest_lv3")
  end
 end
end
''',encoding='utf8')
        help=self.help('quest/help_story.quest')
        self.assertIn('main storyline',help['summary'])
        self.assertNotIn('Recognised grants',dict(help['facts']))
        self.assertTrue(any('database reward table' in n for n in help['notes']))
        with self.assertRaises(ValueError):describe(self.s,'../outside.quest')


if __name__=='__main__':unittest.main()
