from pathlib import Path
import shutil
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1])]
import test_studio
from server import DEFAULT_ROOT, ACTIVE_CHANGESET
from quest_fields import analyse, plan


class QuestFieldsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_studio.StudioTests.setUpClass.__func__(cls)
        for rel in ('quest/collect_quest_lv30.quest', 'quest/collect_quest_lv40.quest',
                    'quest/collect_herb_lv7.quest', 'quest/m2_biologist.lua',
                    'share/locale/poland/quest/quest/systems/hunting.quest',
                    'share/locale/poland/quest/libs/other/hunting_data.lua'):
            target=cls.s.game/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(DEFAULT_ROOT/'linux-port/docker/game'/rel,target)
            cls.initial[target]=target.read_bytes()

    @classmethod
    def tearDownClass(cls):
        test_studio.StudioTests.tearDownClass.__func__(cls)

    def setUp(self):
        test_studio.StudioTests.setUp(self)
        self.token=ACTIVE_CHANGESET.set(None)

    def tearDown(self):
        (self.s.game/'quest/guided_example.quest').unlink(missing_ok=True)
        ACTIVE_CHANGESET.reset(self.token)

    def model(self,rel='quest/collect_quest_lv30.quest'):
        return analyse(self.s,(self.s.game/rel).relative_to(self.s.root).as_posix()).public()

    def review(self,model,values):
        reviewed=plan(self.s,{**model,'values':values})
        return {p:raw for p,_,raw in self.s.plans[reviewed['id']]['files']}

    def field(self,m,label):
        return next(f for f in m['fields'] if f['label']==label)

    def test_linked_items_requirements_cooldowns_and_unrelated_bytes(self):
        path=self.s.game/'quest/guided_example.quest'
        raw=b'''-- pc.give_item2(30001, 99)\r\nquest guided_example begin\r\n state start begin\r\n  when 601.kill begin\r\n   if pc.count_item(30001) < 3 then return end\r\n   pc.remove_item("30001", 3)\r\n   pc.give_item2(25040, 1)\r\n   pc.change_gold(500)\r\n   pc.give_exp2(1000)\r\n   if pc.getqf("kill_count") >= 10 then\r\n    pc.setqf("next_time", get_time()+60*60)\r\n   end\r\n   say("pc.remove_item(30001, 3) - caf\xe9")\r\n   local unrelated=30001\r\n  end\r\n end\r\nend\r\n'''
        path.write_bytes(raw)
        m=self.model('quest/guided_example.quest')
        changes=self.review(m,{self.field(m,'Required / quest-drop item')['key']:'30002',
                               self.field(m,'Required & consumed quantity · #30001')['key']:'5',
                               self.field(m,'Cooldown (seconds)')['key']:'7200',
                               self.field(m,'Kill counter threshold · kill_count >=')['key']:'25'})
        expected=raw.replace(b'count_item(30001) < 3',b'count_item(30002) < 5').replace(b'remove_item("30001", 3)',b'remove_item("30002", 5)').replace(b'>= 10 then',b'>= 25 then').replace(b'get_time()+60*60',b'get_time()+7200')
        self.assertEqual(changes[path],expected)
        self.assertEqual(path.read_bytes(),raw)
        self.assertIn(self.s.game/'custom-quests/studio-source-list.txt',changes)

    def test_biologist_count_and_completion_reward_are_exact_patches(self):
        m=self.model()
        chest=next(f for f in m['fields'] if f['kind']=='item' and f['value']=='50109')
        quantity=next(f for f in m['fields'] if f['label']=='Granted quantity · #50109')
        changes=self.review(m,{self.field(m,'Successful submissions required')['key']:'20',chest['key']:'25040',quantity['key']:'2'})
        source=changes[self.s.game/'quest/collect_quest_lv30.quest']
        self.assertIn(b'collect_count")< 19',source)
        self.assertIn(b'20-pc.getqf("collect_count")',source)
        helper=changes[self.s.game/'quest/m2_biologist.lua']
        original=self.initial[self.s.game/'quest/m2_biologist.lua']
        self.assertEqual(helper,original.replace(b'pc.give_item2(50109)',b'pc.give_item2(25040, 2)'))
        self.assertEqual((self.s.game/'quest/collect_quest_lv40.quest').read_bytes(),self.initial[self.s.game/'quest/collect_quest_lv40.quest'])

    def test_shared_cooldown_requires_custom_and_preserves_environment(self):
        m=self.model()
        wait=self.field(m,'Biologist wait (hours) · shared')
        self.assertTrue(wait['disabled'])
        with self.assertRaisesRegex(ValueError,'requires custom'):
            self.review(m,{wait['key']:'12'})
        env=self.s.compose/'.env'
        env.write_bytes(env.read_bytes().replace(b'M2_DIFFICULTY=easy',b'M2_DIFFICULTY=custom'))
        m=self.model();wait=self.field(m,'Biologist wait (hours) · shared')
        pending=self.review(m,{wait['key']:'12'})
        self.assertEqual(list(pending),[env])
        self.assertIn(b'M2_DB_PASSWORD=test-private-value',pending[env])
        self.assertIn(b'M2_BIOLOGIST_WAIT_HOURS=12',pending[env])

    def test_hunting_has_real_percentage_exp_and_individual_options(self):
        m=self.model('share/locale/poland/quest/quest/systems/hunting.quest')
        fields=[f for f in m['fields'] if f['group']=='Hunt 4 · Level 5']
        xp=next(f for f in fields if f['label']=='EXP reward (% of stage level)')
        kills=next(f for f in fields if f['label']=='Kills · option 1')
        source=self.s.locale/'quest/libs/other/hunting_data.lua'
        pending=self.review(m,{xp['key']:'35',kills['key']:'50'})
        self.assertEqual(list(pending),[source])
        old=source.read_bytes()
        self.assertEqual(pending[source],old.replace(b'{reqLvl = 5,\tmobData={{173, 10}, {174, 10}},\t\tgold=500,\txp=20',b'{reqLvl = 5,\tmobData={{173, 50}, {174, 10}},\t\tgold=500,\txp=35'))
        symbolic=next(f for f in m['fields'] if f['value']=='primary_armor')
        self.assertIn(b'item={11200, 1}',self.review(m,{symbolic['key']:'11200'})[source])

    def test_dynamic_values_comments_and_long_strings_are_not_fields(self):
        path=self.s.game/'quest/guided_example.quest'
        path.write_text('''quest guided_example begin
 state start begin
  when login begin
   --[=[ pc.give_item2(25040, 1) ]=]
   say([[pc.give_item2(25040, 1)]])
   pc.give_item2(reward_id, number(1, 5))
   pc.setqf("next", get_time()+number(10, 20))
   pc.give_exp2(1000 * pc.get_level())
  end
 end
end
''',encoding='utf8')
        m=self.model('quest/guided_example.quest')
        self.assertEqual(m['fields'],[])
        self.assertTrue(any('calculated cooldowns' in n for n in m['notes']))

    def test_stale_shared_dependency_and_invalid_inputs_are_rejected(self):
        m=self.model()
        field=self.field(m,'Successful submissions required')
        for value in ('0','-1','nan','1; os.execute("bad")','1.5'):
            with self.assertRaises(ValueError): self.review(m,{field['key']:value})
        item=next(f for f in m['fields'] if f['kind']=='item')
        with self.assertRaisesRegex(ValueError,'known item'):self.review(m,{item['key']:'999999999'})
        helper=self.s.game/'quest/m2_biologist.lua'
        helper.write_bytes(helper.read_bytes()+b'\n-- new package\n')
        with self.assertRaisesRegex(ValueError,'shared dependency changed'):self.review(m,{field['key']:'20'})

    def test_guided_draft_recovers_multiple_original_dependencies_into_set(self):
        m=self.model();field=self.field(m,'Successful submissions required')
        self.s.workspace.save_draft({'id':'direct:native:example','kind':'quests','title':'Research','payload':{'quest':{'native':True,'model':m,'values':{field['key']:'15'}}}})
        source=self.s.game/'quest/collect_quest_lv30.quest'
        source.write_bytes(source.read_bytes()+b'\n-- upstream addition\n')
        recovered=self.s.workspace.draft_to_set('direct:native:example')
        self.assertTrue(recovered)
        self.assertIn(b'-- upstream addition',source.read_bytes())
        with self.s.workspace.connect() as conn:
            staged=conn.execute('SELECT original,content FROM staged WHERE path=?',(m['id'],)).fetchone()
        self.assertEqual(staged['original'],self.initial[source])
        self.assertIn(b'collect_count")< 14',staged['content'])


if __name__=='__main__': unittest.main()
