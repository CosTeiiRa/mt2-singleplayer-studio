import tempfile
from pathlib import Path
import unittest

from metin2_studio.item_effects import bonus_metadata, parse_dragon_table, enrich_description

ROOT = Path(__file__).resolve().parents[1]

META = {'engine':'mt2009','points':{'15':4,'44':18,'97':55,'121':71,'17':7},
        'formats':{'4':{'template':'Intelligence +%d'},'18':{'template':'Strong against animals +%d%%'},
                   '55':{'template':'Magic attack +%d'},'71':{'template':'Skill damage +%d%%'},'7':{'template':'Attack Speed +%d%%'}}}
TABLE = b'''Group VnumMapper
{
 1 diamond 11
}
Group BasicApplys
{
 Group diamond
 {
  1 15 16
  2 44 21
 }
}
Group AdditionalApplys
{
 Group diamond
 {
  1 97 16 10
  2 121 16 10
 }
}
Group ApplyNumSettings
{
 Group Default
 {
  #--# GRADE_NORMAL GRADE_LEGENDARY
  basis 1 2
  add_min 0 0
  add_max 0 3
 }
}
Group WeightTables
{
 Group Default
 {
  Group GRADE_NORMAL
  {
   STEP_LOWEST 1 2 3
  }
  Group GRADE_LEGENDARY
  {
   STEP_HIGHEST 30 33 39 45 54 63 72
  }
 }
}
'''


def row(typ):
    return ['110000','internal','name',str(typ),'0']+['0']*31


def entry(ident='110000'):
    return {'id':ident,'description':{'text':'General guide','note':'','facts':[],'source':'guide'}}


class EffectTests(unittest.TestCase):
    def test_rough_stone_uses_one_fixed_point_attribute_and_no_random_bonus(self):
        item = entry(); enrich_description(item,row(29),META,parse_dragon_table(TABLE),{'DRAGON_SOUL_STEP_LEVEL1':'Matt'})
        self.assertEqual(item['description']['effects'][0]['values'],['Intelligence +1'])
        self.assertEqual(len(item['description']['effects']),1)
        self.assertIn(['Quality / strength','Matt · +0'],item['description']['facts'])
        self.assertIn(['Bonus scaling','1%'],item['description']['facts'])
        self.assertEqual(item['description']['source'],'configured')

    def test_quality_and_strength_scale_bonuses_and_random_options_stay_separate(self):
        item = entry('114460'); enrich_description(item,row(29),META,parse_dragon_table(TABLE))
        groups = item['description']['effects']
        self.assertEqual(groups[0]['values'],['Intelligence +12','Strong against animals +16%'])
        self.assertEqual(groups[1]['values'],['Magic attack +12','Skill damage +12%'])
        self.assertIn('0–3 additional bonuses',groups[1]['note'])
        self.assertIn('alternatives',groups[1]['note'])

    def test_missing_or_unsupported_balance_never_guesses_bonuses(self):
        item = entry(); enrich_description(item,row(29),META)
        self.assertEqual(item['description']['effects'],[])
        self.assertIn('No deployed balance',str(item['description']['facts']))
        item = entry('119900'); enrich_description(item,row(29),META,parse_dragon_table(TABLE))
        self.assertEqual(item['description']['effects'],[])
        with self.assertRaises(ValueError): parse_dragon_table(TABLE+b'}')

    def test_weapon_and_armour_values_follow_client_tooltip_fields(self):
        weapon = row(1); weapon[30:36] = ['0','15','19','13','15','63']; weapon[24:26] = ['17','22']
        item = entry('19'); enrich_description(item,weapon,META)
        self.assertEqual(item['description']['effects'][0]['values'],['Attack value: 76–78','Magic attack value: 78–82'])
        self.assertEqual(item['description']['effects'][1]['values'],['Attack Speed +22%'])
        armour = row(2); armour[30:36] = ['10','12','0','0','0','27']
        item = entry('11209'); enrich_description(item,armour,META)
        self.assertEqual(item['description']['effects'][0]['values'],['Defence: 66','Magic defence: 10'])

    def test_metadata_is_read_as_literals_without_executing_installed_python(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-tmp') as temp:
            root = Path(temp); (root/'files').mkdir()
            (root/'files/admin_panel.py').write_text("raise RuntimeError('do not execute')\nAPPLY_TEXTS={4:('flat',{'en':'Intelligence +%d'})}\n",encoding='utf-8')
            (root/'linux-port/docker/seban-panel').mkdir(parents=True)
            (root/'linux-port/docker/seban-panel/app.py').write_text('POINT_TO_APPLY={15:4}',encoding='utf-8')
            (root/'linux-port/docker/ENGINE').write_text('mt2009',encoding='utf-8')
            data = bonus_metadata(root)
            self.assertEqual(data['points'],{'15':4})
            self.assertEqual(data['formats']['4']['template'],'Intelligence +%d')

    def test_unknown_fixed_bonus_keeps_numeric_identity_instead_of_wrong_label(self):
        value = row(10); value[24:26] = ['9999','7']; item = entry('28030')
        enrich_description(item,value,META)
        self.assertEqual(item['description']['effects'][0]['values'],['Attribute #9999: +7'])
