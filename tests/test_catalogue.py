"""Live, offline and client-update catalogue behaviour using synthetic data."""
import copy
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from metin2_studio.catalogue import Catalogue
from metin2_studio.catalogue_client import ClientCatalogue, png_pixels

ROOT = Path(__file__).resolve().parents[1]


def item(ident, name='Server item', typ=1):
    row = [str(ident), 'internal', name] + ['0'] * 33
    row[3] = str(typ)
    return row


def fixture(base):
    root = base / 'game/Serwer'; state = base / 'state'
    files = root / 'files'; files.mkdir(parents=True)
    (root / 'VERSION').write_text('fixture-1', encoding='utf-8')
    (files / 'items.json').write_text(json.dumps([{'v':10,'n':'Old sword','c':'weapon'},{'v':99,'n':'Archived','c':'weapon'}]), encoding='utf-8')
    (files / 'playerbot_names_en.tsv').write_text('i\t10\tExported sword\nm\t691\tExported boss\n', encoding='utf-8')
    (files / 'static/icons').mkdir(parents=True)
    (files / 'static/item_icons.json').write_text('{}', encoding='utf-8')
    seed = root / 'linux-port/docker/mariadb/initdb.d/dumps/world.sql'; seed.parent.mkdir(parents=True)
    seed.write_text('INSERT INTO `item_proto` VALUES '+','.join('('+','.join("'"+value+"'" for value in row)+')' for row in [item(10),item(20)])+";\nINSERT INTO `mob_proto` VALUES (691,'original','Seed boss',4,0,0,50);", encoding='utf-8')
    return root, state


def packs(root):
    folder = root.parent / 'Klient/pack'; folder.mkdir(parents=True)
    reader = root / 'files/client_protos.py'
    reader.write_text('''import json
class Entry:
    def __init__(self, path, data): self.path,self.data=path,data
    def key(self): return self.path
def read_pack(index, data): return None,[Entry(k,bytes.fromhex(v)) for k,v in json.loads(data).items()]
def entry_data(entry): return entry.data
ITEM_STRUCT=ITEM_NAMES=None
def read_item_proto(data): return data
def decode_rows(data, layout, names):
    rows=json.loads(data)
    for row in rows:
        row['name']=row['name'].encode();row['locale_name']=row['locale_name'].encode()
    return rows
''', encoding='utf-8')
    tga = bytes([0,0,2])+bytes(9)+struct.pack('<HHBB',1,1,32,32)+bytes([0,0,255,255])
    data = {'gamedata':{'gamedata/item_list.txt':b'10 ETC d:/ymir work/icon/item/00010.tga\n11 ETC icon/item/missing.tga\n',
                        'gamedata/item_proto':json.dumps([{'vnum':ident,'vnum_range':0,'name':'shared','locale_name':'Proto sword'} for ident in (10,11,12)]).encode()},
            'locale':{'locale/en/item_names.txt':b'VNUM\tNAME\n10\tClient sword\n',
                      'locale/en/itemdesc.txt':b'10\tClient sword\tA description from the client.\n',
                      'locale/en/mob_names.txt':b'691\tClient boss\n'},
            'icon':{'icon/item/00010.tga':tga}}
    def write(name):
        (folder / (name+'.index')).write_bytes(b'fixture')
        (folder / (name+'.data')).write_text(json.dumps({key:value.hex() for key,value in data[name].items()}), encoding='utf-8')
    for name in data:
        write(name)
    return data, write


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        (ROOT / '.test-tmp').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.test-tmp'); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root, self.state = fixture(self.base)
        self.rows = {'catalog-items':[item(10,'Live sword',3),item(30,'Custom live item')],
                     'catalog-mobs':[['691','original','Live boss','4','0','0','80']]}
        self.online = True
    def query(self, statements):
        self.assertTrue(all(statement.startswith('SELECT ') for statement in statements))
        self.assertIn('(`immuneflag`+0)',statements[0])
        self.assertIn('CONVERT(`name` USING utf8mb4)',statements[0])
        self.assertIn('`rank`',statements[1])
        if not self.online:
            raise ValueError('Offline')
        return copy.deepcopy(self.rows)
    def service(self):
        return Catalogue(self.root,self.state,server_query=self.query)

    def test_live_definitions_and_client_display_data_feed_one_snapshot(self):
        packs(self.root)
        service = self.service(); snapshot = service.refresh(force=True)
        self.assertEqual(snapshot['items']['10']['name'],'Client sword')
        self.assertEqual(snapshot['items']['10']['catalogKind'],'recovery-potion')
        self.assertEqual(snapshot['items']['30']['name'],'Custom live item')
        self.assertEqual(snapshot['items']['30']['definitionStatus'],'installed-server')
        self.assertNotIn('20',snapshot['definitions'])
        self.assertEqual(snapshot['items']['99']['definitionStatus'],'catalogue-only')
        self.assertEqual(snapshot['mobs']['691']['name'],'Client boss')
        self.assertEqual(snapshot['mobs']['691']['level'],80)
        self.assertEqual(snapshot['items']['10']['clientDescription'],'A description from the client.')
        self.assertTrue(service.icon('12').is_file())
        self.assertIsNone(service.icon('11'))
        self.assertEqual(service.status['serverMode'],'live')

    def test_offline_restart_retains_latest_definitions_including_custom_ids(self):
        first = self.service(); current = first.refresh(force=True)
        self.online = False
        offline = self.service(); cached = offline.refresh(force=True)
        self.assertEqual(cached['revision'],current['revision'])
        self.assertEqual(cached['definitions']['30'][2],'Custom live item')
        self.assertEqual(offline.status['serverMode'],'cached')
        self.rows['catalog-items'][1][2] = 'Changed live item'
        self.online = True
        recovered = offline.refresh(force=True)
        self.assertEqual(recovered['items']['30']['name'],'Changed live item')
        self.assertNotEqual(recovered['revision'],cached['revision'])
        self.assertEqual(offline.status['serverMode'],'live')

    def test_first_offline_start_uses_seed_and_retries_automatically(self):
        self.online = False; service = self.service()
        self.assertEqual(service.refresh(force=True)['items']['10']['name'],'Exported sword')
        self.assertEqual(service.status['serverMode'],'seed')
        self.online = True; service.next_server = 0
        self.assertIn('30',service.refresh()['definitions'])
        self.assertEqual(service.status['serverMode'],'live')

    def test_incomplete_live_response_does_not_replace_good_cache(self):
        service = self.service(); current = service.refresh(force=True)
        old = service.cache.read_bytes()
        self.rows['catalog-items'] = []
        self.assertEqual(service.refresh(force=True)['revision'],current['revision'])
        self.assertEqual(service.cache.read_bytes(),old)
        self.assertEqual(service.status['serverMode'],'cached')

    def test_cache_is_bound_to_installation_and_validated(self):
        service = self.service(); service.refresh(force=True)
        cached = json.loads(service.cache.read_text('utf-8')); cached['root'] = 'another installation'
        service.cache.write_text(json.dumps(cached),encoding='utf-8')
        self.online = False
        self.assertEqual(self.service().refresh(force=True)['items']['10']['name'],'Exported sword')
        cached['root'] = str(self.root.resolve()); cached['items'][0][2] = 'Tampered'
        service.cache.write_text(json.dumps(cached),encoding='utf-8')
        self.assertEqual(self.service().refresh(force=True)['items']['10']['name'],'Exported sword')

    def test_local_updates_wait_for_stable_files_then_refresh_without_restart(self):
        data,write = packs(self.root)
        service = self.service(); before = service.refresh(force=True)
        data['locale']['locale/en/item_names.txt'] = b'10\tUpdated client sword\n'; write('locale')
        self.assertEqual(service.refresh()['revision'],before['revision'])
        self.assertTrue(service.status['refreshPending'])
        after = service.refresh()
        self.assertEqual(after['items']['10']['name'],'Updated client sword')
        self.assertNotEqual(after['revision'],before['revision'])
        self.assertFalse(service.status['refreshPending'])

    def test_client_pack_failure_keeps_cached_names_and_icons(self):
        packs(self.root); service = self.service(); before = service.refresh(force=True)
        (self.root.parent / 'Klient/pack/locale.data').write_bytes(b'incomplete update')
        after = service.refresh(force=True)
        self.assertEqual(after['items']['10']['name'],'Client sword')
        self.assertTrue(service.icon('10').is_file())
        self.assertEqual(service.status['clientMode'],'cached')

    def test_client_image_cache_repairs_deleted_generated_image(self):
        packs(self.root); client = ClientCatalogue(self.root,self.state)
        data,_ = client.load(); path = client.icon_path(data['icons']['10']); path.unlink()
        rebuilt,mode = client.load()
        self.assertEqual(mode,'current'); self.assertTrue(client.icon_path(rebuilt['icons']['10']).is_file())
        self.assertFalse((self.root / 'files/__pycache__').exists())

    def test_export_is_an_isolated_copy_of_the_same_snapshot(self):
        service = self.service(); service.refresh(force=True)
        result = service.export(); result['items']['10']['name'] = 'external mutation'
        self.assertNotEqual(service.snapshot['items']['10']['name'],'external mutation')

    def test_addon_export_uses_same_names_properties_and_revision(self):
        from metin2_studio.addons.knowledge import build_index
        packs(self.root)
        service = self.service()
        class Source:
            def refresh_catalog(inner, force=False):
                data = service.refresh(force=force)
                inner.items,inner.mobs = data['items'],data['mobs']
            def recipe_sources(inner): return {}
            def recipes(inner): return []
            def groups(inner, raw): return []
        studio = Source(); studio.root = self.root; studio.catalogue = service; studio.sources = {}
        with patch('metin2_studio.crafting_access.discover_native',return_value=[]):
            exported = build_index(studio)
        self.assertEqual(exported['items']['10']['name'],studio.items['10']['name'])
        self.assertEqual(exported['items']['10']['description'],studio.items['10']['description'])
        self.assertEqual(exported['items']['30']['name'],'Custom live item')
        self.assertEqual(exported['meta']['catalogue_revision'],service.snapshot['revision'])
        self.assertEqual(exported['items']['10']['iconAvailable'],studio.items['10']['iconAvailable'])

    def test_atlas_reads_shared_mob_names_instead_of_stale_export(self):
        from metin2_studio.addons.map_data import WorldData
        panel = self.root / 'linux-port/docker/seban-panel/static'; panel.mkdir(parents=True)
        (panel / 'mob_names_en.json').write_text('{"691":"Old exported boss"}',encoding='utf-8')
        data = WorldData(self.root,mobs={'691':{'name':'Current boss'}})
        self.assertEqual(data.names['691'],'Current boss')

    def test_corrupted_cache_and_legacy_exports_do_not_hide_live_client_data(self):
        packs(self.root); service = self.service(); service.refresh(force=True)
        (self.root / 'files/items.json').write_text('{broken',encoding='utf-8')
        (self.root / 'files/static/item_icons.json').write_text('[]',encoding='utf-8')
        service.cache.write_text('[]',encoding='utf-8')
        service.client.cache.write_text('[]',encoding='utf-8')
        repaired = self.service(); data = repaired.refresh(force=True)
        self.assertEqual(repaired.status['serverMode'],'live')
        self.assertEqual(data['items']['10']['name'],'Client sword')
        self.assertTrue(repaired.icon('10').is_file())

    def test_older_version_cache_is_labelled_and_deleted_icons_rebuild_on_refresh(self):
        packs(self.root); service = self.service(); service.refresh(force=True)
        service.icon('10').unlink(); service.refresh()
        self.assertTrue(service.icon('10').is_file())
        (self.root / 'VERSION').write_text('fixture-2',encoding='utf-8'); self.online = False
        restarted = self.service(); restarted.refresh(force=True)
        self.assertTrue(restarted.status['cacheFromOlderVersion'])
        self.assertEqual(restarted.status['serverMode'],'cached')

    def test_deployed_effect_snapshot_survives_offline_restart(self):
        from tests.test_item_effects import TABLE,META
        from metin2_studio.item_effects import parse_dragon_table
        self.rows['catalog-items'].append(item(110000,'Dragon Stone',29))
        service = self.service()
        service.server = {'dragonSoul':parse_dragon_table(TABLE),'bonusMeta':META}
        before = service.refresh(force=True)
        self.assertEqual(before['items']['110000']['description']['effects'][0]['values'],['Intelligence +1'])
        self.online = False; restarted = self.service(); after = restarted.refresh(force=True)
        self.assertEqual(after['items']['110000']['description'],before['items']['110000']['description'])
        self.assertEqual(restarted.status['serverMode'],'cached')


class ImageTests(unittest.TestCase):
    def test_tga_rle_and_orientation_decode_to_expected_png_pixels(self):
        # Bottom-origin BGR: bottom blue, top red; output must be top-origin RGBA.
        header = bytes([0,0,10])+bytes(9)+struct.pack('<HHBB',1,2,24,0)
        raw = png_pixels(header+bytes([1,255,0,0,0,0,255]))
        self.assertEqual(raw[:8],b'\x89PNG\r\n\x1a\n')
        offset,compressed = 8,b''
        while offset < len(raw):
            size = struct.unpack_from('>I',raw,offset)[0]; tag = raw[offset+4:offset+8]
            if tag == b'IDAT': compressed += raw[offset+8:offset+8+size]
            offset += size+12
        self.assertEqual(zlib.decompress(compressed),bytes([0,255,0,0,255,0,0,0,255,255]))
        with self.assertRaises(ValueError): png_pixels(header+b'\xff')
        with self.assertRaises(ValueError): png_pixels(bytes(18))
