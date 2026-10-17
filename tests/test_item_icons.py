import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from item_icons import item_list_aliases, client_icon_aliases, icon_path

TEST_RUNS=Path(__file__).resolve().parents[1]/'data/test-runs'
TEST_RUNS.mkdir(parents=True,exist_ok=True)


class ItemIconTests(unittest.TestCase):
    def test_explicit_client_aliases_include_ids_missing_from_web_catalog(self):
        aliases=item_list_aliases(b'35000\tETC\ticon/item/30143.tga\n30353 ETC icon/item/Pork.tga\n50942 ETC icon/item/50903.tga\n10 WEAPON d:/ymir work/icon/item/00010.tga\n')
        self.assertEqual(aliases,{'35000':'30143.png','30353':'pork.png','50942':'50903.png'})
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
            cache.write_text(json.dumps({'version':1,'fingerprint':fingerprint,'aliases':{'30353':'pork.png','35000':'absent.png'}}))
            with patch('item_icons.importlib.util.spec_from_file_location') as load:
                self.assertEqual(client_icon_aliases(root,state),{'30353':'Pork.png'})
                load.assert_not_called()
            # A changed client pack must invalidate the derived cache.
            (pack/'gamedata.data').write_bytes(b'changed')
            with patch('item_icons.importlib.util.spec_from_file_location',side_effect=ValueError('unsupported')) as load:
                self.assertEqual(client_icon_aliases(root,state),{})
                load.assert_called_once()

    def test_installations_without_client_assets_keep_static_icon_support(self):
        with tempfile.TemporaryDirectory(dir=TEST_RUNS) as temp:
            self.assertEqual(client_icon_aliases(Path(temp)/'server',Path(temp)/'state'),{})


if __name__=='__main__': unittest.main()
