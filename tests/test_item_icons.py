import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from metin2_studio.item_icons import item_list_aliases, client_icon_aliases, icon_path, shared_name_aliases
from metin2_studio.catalog import item_identity

TEST_RUNS=Path(__file__).resolve().parents[1]/'data/test-runs'
TEST_RUNS.mkdir(parents=True,exist_ok=True)


class ItemIconTests(unittest.TestCase):
    def test_explicit_client_aliases_include_ids_missing_from_web_catalog(self):
        aliases=item_list_aliases(b'35000\tETC\ticon/item/30143.tga\n30353 ETC icon/item/Pork.tga\n50942 ETC icon/item/50903.tga\n10 WEAPON d:/ymir work/icon/item/00010.tga\n')
        self.assertEqual(aliases,{'35000':'30143.png','30353':'pork.png','50942':'50903.png','10':'00010.png'})
        invalid=item_list_aliases(b'1 ETC ../../secrets.png\n2 ETC icon/item/../../outside.png\nx ETC icon/item/123.png\n')
        # Basenames can only resolve inside the local icon directory; no outside paths survive.
        self.assertNotIn('1',invalid)
        self.assertTrue(all('/' not in name and '\\' not in name for name in invalid.values()))

    def test_exact_id_icons_do_not_require_a_catalog_entry_or_guess_nearby_ids(self):
        with tempfile.TemporaryDirectory(dir=TEST_RUNS) as temp:
            root=Path(temp);folder=root/'files/static/icons';folder.mkdir(parents=True)
            (folder/'00010.png').write_bytes(b'png')
            (folder/'Pork.png').write_bytes(b'png')
            self.assertEqual(icon_path(root,{'30353':'Pork.png'},'30353'),folder/'Pork.png')
            self.assertEqual(icon_path(root,{},'10'),folder/'00010.png')
            self.assertIsNone(icon_path(root,{},'11'))
            self.assertIsNone(icon_path(root,{'12':'../../secret.png'},'12'))
            self.assertIsNone(icon_path(root,{},'../../secret'))

    def test_derived_alias_cache_is_bound_to_installed_sources_and_preserves_case(self):
        with tempfile.TemporaryDirectory(dir=TEST_RUNS) as temp:
            parent=Path(temp);root=parent/'Serwer';state=parent/'studio';state.mkdir()
            icons=root/'files/static/icons';icons.mkdir(parents=True)
            (icons/'Pork.png').write_bytes(b'png')
            reader=root/'files/client_protos.py';reader.write_text('# fixture')
            pack=parent/'Klient/pack';pack.mkdir(parents=True)
            (pack/'gamedata.index').write_bytes(b'index');(pack/'gamedata.data').write_bytes(b'data')
            inputs=(reader,pack/'gamedata.index',pack/'gamedata.data',icons)
            fingerprint=[[str(p.resolve()),p.stat().st_size,p.stat().st_mtime_ns] for p in inputs]
            cache=state/'item-icon-aliases.json'
            cache.write_text(json.dumps({'version':2,'fingerprint':fingerprint,'aliases':{'30353':'pork.png','35000':'absent.png'}}))
            with patch('metin2_studio.item_icons.importlib.util.spec_from_file_location') as load:
                self.assertEqual(client_icon_aliases(root,state),{'30353':'Pork.png','35000':None})
                load.assert_not_called()
            # A changed client pack must invalidate the derived cache.
            (pack/'gamedata.data').write_bytes(b'changed')
            with patch('metin2_studio.item_icons.importlib.util.spec_from_file_location',side_effect=ValueError('unsupported')) as load:
                self.assertEqual(client_icon_aliases(root,state),{})
                load.assert_called_once()

    def test_installations_without_client_assets_keep_static_icon_support(self):
        with tempfile.TemporaryDirectory(dir=TEST_RUNS) as temp:
            self.assertEqual(client_icon_aliases(Path(temp)/'server',Path(temp)/'state'),{})

    def test_old_cache_rebuilds_from_sources_without_writing_game_bytecode(self):
        with tempfile.TemporaryDirectory(dir=TEST_RUNS) as temp:
            parent=Path(temp);root=parent/'Serwer';state=parent/'studio';state.mkdir()
            icons=root/'files/static/icons';icons.mkdir(parents=True)
            (icons/'00100.png').write_bytes(b'png')
            pack=parent/'Klient/pack';pack.mkdir(parents=True)
            for suffix in ('index','data'):
                (pack/('gamedata.'+suffix)).write_bytes(b'fixture')
            reader=root/'files/client_protos.py'
            reader.write_text("""class Entry:
    def __init__(self, path): self.path=path
    def key(self): return self.path
def read_pack(index, data):
    return None, [Entry('gamedata/item_list.txt'), Entry('gamedata/item_proto')]
def entry_data(entry): return b'100 ETC icon/item/00100.tga'
ITEM_STRUCT=ITEM_NAMES=None
def read_item_proto(data): return data
def decode_rows(data, layout, fields):
    return [{'vnum':100,'name':b'shared'}, {'vnum':123,'name':b'shared'}]
""",encoding='utf-8')
            cache=state/'item-icon-aliases.json'
            cache.write_text(json.dumps({'version':1,'aliases':{'123':'wrong.png'}}),encoding='utf-8')
            self.assertEqual(client_icon_aliases(root,state),{'100':'00100.png','123':'00100.png'})
            self.assertEqual(json.loads(cache.read_text('utf-8'))['version'],2)
            self.assertFalse((reader.parent/'__pycache__').exists())
            reader.write_text(reader.read_text('utf-8')+"\ndef read_item_proto(data): raise ValueError('other format')\n",encoding='utf-8')
            self.assertEqual(client_icon_aliases(root,state),{'100':'00100.png'})

    def test_original_proto_name_recovers_only_unambiguous_missing_aliases(self):
        rows=[{'vnum':100,'name':b'original-name\0'}, {'vnum':123,'name':b'original-name\0padding'},
              {'vnum':124,'name':b'different-name\0'}, {'vnum':125,'name':b'original-name\0'}]
        result=shared_name_aliases(rows,{'100':'shared.png','125':'missing.png'},{'shared.png':'Shared.png'})
        self.assertEqual(result,{'123':'Shared.png'})
        ambiguous=rows+[{'vnum':200,'name':b'original-name\0'}]
        self.assertEqual(shared_name_aliases(ambiguous,{'100':'a.png','200':'b.png'}, {'a.png':'a.png','b.png':'b.png'}),{})

    def test_empty_and_placeholder_proto_names_do_not_assign_unrelated_icons(self):
        rows=[{'vnum':10,'name':b'NoName\0'}, {'vnum':11,'name':b'NoName\0'},
              {'vnum':20,'name':b'\0'}, {'vnum':21,'name':b'\0'}]
        self.assertEqual(shared_name_aliases(rows,{'10':'a.png','20':'b.png'}, {'a.png':'a.png','b.png':'b.png'}),{})

    def test_explicit_missing_client_asset_never_borrows_an_old_exact_id_icon(self):
        with tempfile.TemporaryDirectory(dir=TEST_RUNS) as temp:
            root=Path(temp);folder=root/'files/static/icons';folder.mkdir(parents=True)
            (folder/'00010.png').write_bytes(b'old catalogue icon')
            self.assertIsNone(icon_path(root,{'10':None},'10'))
            self.assertEqual(icon_path(root,{},'10'),folder/'00010.png')


class ItemIdentityTests(unittest.TestCase):
    def test_installed_english_names_replace_stale_and_placeholder_catalogue_names(self):
        row=['30315','internal','Chleb']
        record=item_identity({'id':'30315','name':'NoNAme'},row,'Bread')
        self.assertEqual(record['name'],'Bread')
        self.assertEqual(record['catalogName'],'NoNAme')
        self.assertEqual(record['original'],'Chleb')
        self.assertEqual(record['nameSource'],'installed-english')
        self.assertEqual(record['definitionStatus'],'installed-seed')
        self.assertEqual(item_identity({'id':'25041','name':'Magic Stone'},['25041','','Scroll'],'Blessing Scroll')['name'],'Blessing Scroll')

    def test_unknown_names_are_labelled_without_inventing_a_translation(self):
        unknown=item_identity({'id':'30528','name':'NoNAme'},['30528','','NoNAme'])
        self.assertEqual(unknown['name'],'Unnamed item #30528')
        self.assertEqual(unknown['nameStatus'],'unnamed')
        garbled=item_identity({'id':'53507','name':'\u00b3\u00ec\u00b0\u00a2 \u00ba\u00b8\u00b0\u00fc\u00c7\u00d4'})
        self.assertEqual(garbled['nameStatus'],'unnamed')
        self.assertEqual(garbled['definitionStatus'],'catalogue-only')

    def test_missing_translations_preserve_usable_catalogue_and_seed_names(self):
        self.assertEqual(item_identity({'id':'10','name':'Sword'},['10','','Miecz'],'NoNAme')['name'],'Sword')
        self.assertEqual(item_identity({'id':'10','name':'NoNAme'},['10','','Miecz'])['name'],'Miecz')
        self.assertEqual(item_identity({'id':'999','name':'Unbekanntes Schwert'})['name'],'Unbekanntes Schwert')


if __name__=='__main__': unittest.main()
