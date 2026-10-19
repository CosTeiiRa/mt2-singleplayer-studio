"""One installation-bound item/mob snapshot for Studio and add-on exports."""
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import time

from .catalog import item_identity, item_metadata, _usable_name
from .catalogue_client import ClientCatalogue, fingerprint
from .database import query
from .installation import atomic_json
from .item_help import item_description
from .item_icons import icon_path
from .item_effects import bonus_metadata, deployed_dragon_table, enrich_description

ITEM_COLUMNS = ('vnum','name','locale_name','type','subtype','stack','weight','size','antiflag','flag','wearflag',
                'immuneflag','gold','shop_buy_price','refined_vnum','refine_set','magic_pct','specular','socket_pct',
                'addon_type','limittype0','limitvalue0','limittype1','limitvalue1','applytype0','applyvalue0',
                'applytype1','applyvalue1','applytype2','applyvalue2','value0','value1','value2','value3','value4','value5')


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def sql_rows(raw, table):
    """Read every INSERT tuple as data, including quoted commas and escapes."""
    result = []
    pattern = re.compile(r'INSERT\s+INTO\s+`?' + re.escape(table) + r'`?\s+VALUES\s*', re.I)
    for match in pattern.finditer(raw):
        row, cell, quoted, escaped, active = [], [], False, False, False
        for char in raw[match.end():]:
            if escaped:
                cell.append({'n':'\n','r':'\r','t':'\t','0':'\0'}.get(char, char)); escaped = False
            elif quoted and char == '\\':
                escaped = True
            elif char == "'":
                quoted = not quoted
            elif not quoted and char == ';':
                break
            elif not quoted and char == '(':
                row, cell, active = [], [], True
            elif not quoted and active and char in ',)':
                row.append(''.join(cell).strip()); cell = []
                if char == ')':
                    result.append(row); active = False
            elif active:
                cell.append(char)
    return result


def valid_rows(rows, width, required=True):
    if not isinstance(rows, list) or len(rows) > 100000 or required and not rows:
        raise ValueError('Incomplete server catalogue')
    result = {}
    for row in rows:
        if not isinstance(row, list) or len(row) < width or not re.fullmatch(r'[1-9][0-9]{0,9}', str(row[0])):
            raise ValueError('Invalid server catalogue row')
        ident = str(row[0])
        if int(ident) > 4294967295:
            raise ValueError('Server catalogue ID outside supported range')
        if ident in result:
            raise ValueError('Duplicate server catalogue ID')
        result[ident] = [str(value) if value is not None else '0' for value in row[:width]]
        for index in range(3, width):
            int(result[ident][index])
    return result


class Catalogue:
    def __init__(self, root, state, server_query=None):
        self.root, self.state = Path(root).resolve(), Path(state)
        self.compose = self.root / 'linux-port/docker'
        self.client = ClientCatalogue(self.root, self.state)
        self.cache = self.state / 'catalogue/server.json'
        self.server_query = server_query
        self.lock = threading.RLock()
        self.next_server = 0
        self.local_fingerprint = None
        self.pending_fingerprint = None
        self.images_fingerprint = None
        self.snapshot = None
        self.server = None
        self.status = {}
        self.paths = [self.root / name for name in ('VERSION','files/items.json','files/playerbot_names_en.tsv',
                      'files/static/item_icons.json','files/static/icons','linux-port/docker/mariadb/initdb.d/dumps/world.sql',
                      'files/admin_panel.py','linux-port/docker/seban-panel/app.py','linux-port/docker/ENGINE')]
        self.paths += self.client.paths
        try:
            cached = json.loads(self.cache.read_text('utf-8'))
            if isinstance(cached, dict) and cached.get('schema') in (1,2) and cached.get('root') == str(self.root):
                valid_rows(cached['items'], 36); valid_rows(cached['mobs'], 7)
                contents = [cached['items'],cached['mobs']]
                if cached['schema']==2:
                    contents += [cached.get('dragonSoul'),cached.get('bonusMeta')]
                if checksum(contents) == cached.get('digest'):
                    self.server = cached
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def _server(self):
        if self.server_query is None and not (self.compose / 'docker-compose.yml').is_file():
            raise ValueError('No running database adapter for this installation')
        def field(name):
            quoted = '`' + name + '`'
            if name == 'immuneflag':
                return '(' + quoted + '+0)'  # The native database stores this bitmask as a SET.
            return 'CONVERT(' + quoted + ' USING utf8mb4) COLLATE utf8mb4_unicode_ci' if name in ('name','locale_name') else quoted
        fields = ','.join(field(name) for name in ITEM_COLUMNS)
        mob_fields = ','.join(field(name) for name in ('vnum','name','locale_name','rank','type','battle_type','level'))
        statements = ["SELECT JSON_OBJECT('set','catalog-items','row',JSON_ARRAY(" + fields + ")) FROM world.item_proto ORDER BY vnum;",
                      "SELECT JSON_OBJECT('set','catalog-mobs','row',JSON_ARRAY(" + mob_fields + ")) FROM world.mob_proto ORDER BY vnum;"]
        rows = self.server_query(statements) if self.server_query else query(self.compose, statements, timeout=10)
        items, mobs = valid_rows(rows.get('catalog-items'), 36), valid_rows(rows.get('catalog-mobs'), 7)
        metadata = bonus_metadata(self.root)
        if not metadata['formats'] and self.server:
            metadata = self.server.get('bonusMeta') or metadata
        dragon = self.server.get('dragonSoul') if self.server else None
        if self.server_query is None and (self.compose / 'docker-compose.yml').is_file():
            try:
                dragon = deployed_dragon_table(self.compose)
            except (ValueError,OSError,subprocess.TimeoutExpired):
                pass
        result = {'schema':2,'root':str(self.root),'items':list(items.values()),'mobs':list(mobs.values()),
                  'dragonSoul':dragon, 'bonusMeta':metadata,
                  'fetchedAt':time.time(),'version':self._version()}
        result['digest'] = checksum([result['items'],result['mobs'],dragon,metadata])
        return result

    def _version(self):
        try:
            return (self.root / 'VERSION').read_text('utf-8').strip()
        except OSError:
            return ''

    def refresh(self, force=False):
        with self.lock:
            now = time.monotonic()
            before = fingerprint(self.paths)
            images_before = fingerprint([self.client.images])
            if self.pending_fingerprint is not None and before == self.local_fingerprint:
                self.pending_fingerprint = None
                self.status = {**self.status, 'refreshPending':False}
            if not force and self.snapshot and before == self.local_fingerprint and images_before == self.images_fingerprint and now < self.next_server:
                return self.snapshot
            if not force and self.snapshot and before != self.local_fingerprint and before != self.pending_fingerprint:
                self.pending_fingerprint = before
                self.status = {**self.status, 'refreshPending':True}
                return self.snapshot
            server = self.server
            mode = self.status.get('serverMode', 'cached' if server else 'seed')
            if force or now >= self.next_server:
                try:
                    server = self._server(); mode = 'live'
                except (ValueError, OSError, TypeError, KeyError):
                    mode = 'cached' if server else 'seed'
                self.next_server = now + 60
            if (self.snapshot and before == self.local_fingerprint and images_before == self.images_fingerprint
                    and self.status.get('clientMode') == 'current'
                    and (server or {}).get('digest') == (self.server or {}).get('digest')):
                if server is not None and server is not self.server:
                    atomic_json(self.cache, server)
                self.server = server
                self.status = {**self.status, 'serverMode':mode, 'serverFetchedAt':server.get('fetchedAt') if server else None}
                return self.snapshot
            client, client_mode = self.client.load()
            try:
                snapshot = self._build(server, client)
                if before != fingerprint(self.paths):
                    raise ValueError('Installation changed during catalogue refresh')
            except (OSError, ValueError, KeyError, TypeError):
                if self.snapshot is None:
                    raise
                self.status = {**self.status, 'refreshPending':True}
                return self.snapshot
            if server is not None and server is not self.server:
                atomic_json(self.cache, server)
            self.server = server
            self.snapshot = snapshot
            self.local_fingerprint = before
            self.pending_fingerprint = None
            self.images_fingerprint = fingerprint([self.client.images])
            self.status = {'revision':snapshot['revision'],'serverMode':mode,'clientMode':client_mode,
                           'serverFetchedAt':server.get('fetchedAt') if server else None,
                           'cacheFromOlderVersion':bool(server and server.get('version') != self._version()),
                           'refreshPending':False,'items':len(snapshot['items']),'mobs':len(snapshot['mobs'])}
            return snapshot

    def _build(self, server, client):
        def read(name, default=''):
            path = self.root / name
            return path.read_text('utf-8-sig', errors='replace') if path.is_file() else default
        try:
            raw = json.loads(read('files/items.json', '[]'))
        except ValueError:
            raw = []  # A damaged legacy export must not hide the live/client catalogue.
        if not isinstance(raw, list):
            raw = []
        items = {str(row['v']):{'id':str(row['v']),'name':row['n'],'category':row.get('c','item'),'keywords':row.get('k','')}
                 for row in raw if isinstance(row,dict) and 'v' in row and isinstance(row.get('n'),str)}
        english, mob_names = {}, {}
        for line in read('files/playerbot_names_en.tsv').splitlines():
            cells = line.split('\t')
            if len(cells) >= 3 and cells[0] in ('i','m'):
                (english if cells[0] == 'i' else mob_names)[cells[1]] = cells[2]
        seed = read('linux-port/docker/mariadb/initdb.d/dumps/world.sql')
        definitions = {row[0]:row for row in sql_rows(seed, 'item_proto') if len(row) >= 36}
        mob_rows = sql_rows(seed, 'mob_proto')
        if server:
            definitions = valid_rows(server['items'], 36)
            mob_rows = server['mobs']
        for ident, row in definitions.items():
            items.setdefault(ident, {'id':ident,'name':row[2],'category':'item','keywords':''})
        for ident, row in client.get('proto', {}).items():
            items.setdefault(ident, {'id':ident,'name':row.get('name',''),'category':'item','keywords':''})
        try:
            legacy = json.loads(read('files/static/item_icons.json', '{}'))
        except ValueError:
            legacy = {}
        if not isinstance(legacy,dict):
            legacy = {}
        icons = client.get('icons', {})
        metadata = server.get('bonusMeta') if server else None
        metadata = metadata or bonus_metadata(self.root)
        available = {path.name for path in self.client.images.glob('*.png') if path.is_file()}
        static_folder = (self.root / 'files/static/icons').resolve()
        static = {path.name for path in static_folder.glob('*.png') if path.is_file() and path.resolve().is_relative_to(static_folder)}
        for ident, item in items.items():
            row = definitions.get(ident)
            translated = client.get('names', {}).get(ident)
            item.update(item_identity(item, row, translated if _usable_name(translated) else english.get(ident)))
            if _usable_name(translated):
                item['nameSource'] = 'client-english'
            elif row and server and _usable_name(row[2]):
                # Preserve a live custom rename when the client has no translation.
                item['name'], item['nameSource'], item['nameStatus'] = row[2], 'server', 'named'
            elif not _usable_name(english.get(ident)) and _usable_name(client.get('proto', {}).get(ident, {}).get('name')):
                item['name'] = client['proto'][ident]['name']; item['nameSource'] = 'client-proto'; item['nameStatus'] = 'named'
            if row and server:
                item['definitionStatus'] = 'installed-server'
            item.update(item_metadata(item, row))
            item['description'] = item_description(item, row)
            enrich_description(item,row,metadata,server.get('dragonSoul') if server else None,client.get('terms',{}))
            description = client.get('descriptions', {}).get(ident)
            if description:
                item['description']['facts'].append(['Client description', description])
                item['clientDescription'] = description
            if row and server:
                item['description']['facts'] = [[key, 'Present in server catalogue' if key == 'Definition' else value] for key, value in item['description']['facts']]
                item['description']['text'] = item['description']['text'].replace('installed seed', 'server definition')
            exact = f'{int(ident):05d}.png' if ident.isdigit() else ''
            item['iconAvailable'] = bool(icons.get(ident) in available) if ident in icons else legacy.get(ident) in static or exact in static
        mobs = {}
        for row in mob_rows:
            if len(row) >= 7:
                ident, rank, typ = str(row[0]), int(row[3]), int(row[4])
                mobs[ident] = {'id':ident,'name':client.get('mobs',{}).get(ident) or mob_names.get(ident) or row[2],
                               'original':row[2],'category':'metin' if typ == 2 else 'npc' if typ not in (0,2) else 'boss' if rank >= 4 else 'monster','level':int(row[6])}
        mob_icons = {}
        for ident, mob in mobs.items():
            portrait = client.get('mobIcons', {}).get(ident)
            badge = client.get('mobBadges', {}).get(mob['category'])
            picture = portrait or badge
            mob['iconAvailable'] = picture in available
            mob['iconKind'] = 'portrait' if portrait else 'category' if badge else 'unavailable'
            if mob['iconAvailable']:
                mob_icons[ident] = picture
        result = {'items':items,'mobs':mobs,'definitions':definitions,'icons':icons,'legacyIcons':legacy,'mobIcons':mob_icons}
        result['revision'] = checksum(result)
        return result

    def icon(self, ident, kind='item'):
        # Snapshots and content-addressed images stay immutable after publication.
        # Serving cached pixels must not wait for a database connection attempt.
        snapshot = self.snapshot
        if kind == 'mob':
            return self.client.icon_path(snapshot.get('mobIcons', {}).get(ident)) if snapshot else None
        if snapshot and ident in snapshot['icons']:
            return self.client.icon_path(snapshot['icons'][ident])
        return icon_path(self.root, snapshot['legacyIcons'] if snapshot else {}, ident)

    def export(self):
        with self.lock:
            return copy.deepcopy(self.snapshot)
