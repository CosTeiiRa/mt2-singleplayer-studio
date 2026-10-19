"""Structured, world-local reference data. Never deploys or edits game data.

Only explicit relationships are exported. Configuration and database seeds
retain their provenance; they are not assertions about effective engine rules.
"""
from __future__ import annotations

from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
import re

SCHEMA = 1
MAX_BYTES = 24 * 1024 * 1024


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('ascii')


def checksum(value):
    return hashlib.sha256(encoded(value)).hexdigest()


from metin2_studio.catalogue import sql_rows
from metin2_studio.catalogue_client import fingerprint


def positive(value):
    text = str(value)
    return bool(re.fullmatch(r'[1-9][0-9]{0,9}', text)) and int(text) <= 4294967295


def quantity(value, minimum=0):
    number = int(str(value))
    if not minimum <= number <= 2147483647:
        raise ValueError('Reference quantity outside supported range.')
    return number


def pairs(text):
    pieces = str(text).split(',') if text else []
    if len(pieces) % 2 or any(not positive(value) for value in pieces):
        raise ValueError('Unrecognised crafting ingredient format.')
    return [{'item': str(pieces[i]), 'count': quantity(pieces[i + 1], 1)} for i in range(0, len(pieces), 2)]


def build_index(studio):
    """Build on demand, outside any active change set, from saved bytes/live rows.

    The caller serializes review/apply with Studio mutations. Captured bytes
    are hashed; repeated builds allow the manager to reject stale reviews.
    """
    context = getattr(studio, 'active_context', None)
    token = context.set(None) if context else None
    try:
        return _build(studio)
    finally:
        if context:
            context.reset(token)


def _build(studio):
    if getattr(studio, 'catalogue', None) is not None:
        studio.refresh_catalog(force=True)
    studio = copy.copy(studio)
    studio._crafting_access = None
    studio._native_crafting_access = None
    root = Path(studio.root)
    game = root / 'linux-port/docker/game'
    compose = game.parent
    sources, captured, warnings = {}, {}, []

    def read(path):
        path = Path(path)
        if path in captured:
            return captured[path]
        raw = path.read_bytes() if path.is_file() else b''
        captured[path] = raw
        sources[path.relative_to(root).as_posix()] = hashlib.sha256(raw).hexdigest()
        return raw

    # Existing readers use this local immutable view, never drafts or staged data.
    studio.read = lambda path: read(path) if Path(path).is_file() else None

    version = read(root / 'VERSION').decode('utf-8-sig', 'replace').strip()
    sql = read(compose / 'mariadb/initdb.d/dumps/world.sql').decode('utf-8-sig', 'replace')
    definitions = {row[0]: row for row in sql_rows(sql, 'item_proto') if len(row) > 15}
    parser_raw = read(root / 'files/drop_tables.py')
    if getattr(studio, 'drop_parser_sha', hashlib.sha256(parser_raw).hexdigest()) != hashlib.sha256(parser_raw).hexdigest():
        raise ValueError('The installed drop parser changed. Restart Studio before generating reference data.')
    read(game / 'Dockerfile')
    catalogue_service = getattr(studio, 'catalogue', None)
    catalogue_snapshot = None
    if catalogue_service is not None:
        catalogue_snapshot = catalogue_service.export()
        definitions = catalogue_snapshot['definitions']
        studio.items = catalogue_snapshot['items']
        studio.mobs = catalogue_snapshot['mobs']
    else:
        # Synthetic/export-only callers already supply their item and mob snapshot.
        studio.items = copy.deepcopy(studio.items)
        studio.mobs = copy.deepcopy(studio.mobs)
    items = {}
    for ident, item in studio.items.items():
        if positive(ident):
            items[str(ident)] = {'id': str(ident), 'name': str(item['name']),
                                'category': str(item.get('catalogLabel', item.get('category', 'Item'))),
                                'description': item.get('description', ''),
                                'level': item.get('requiredLevel'), 'aliases': ' '.join(str(item.get(key) or '') for key in ('keywords', 'catalogName', 'original')),
                                'iconAvailable': item.get('iconAvailable'), 'nameSource': item.get('nameSource')}
    recipes, upgrades, origins, npcs = {}, {}, {}, {}
    created, used, obtained = defaultdict(list), defaultdict(list), defaultdict(list)

    def ensure(ident):
        ident = str(ident)
        if positive(ident) and ident not in items:
            row = definitions.get(ident)
            items[ident] = {'id': ident, 'name': row[2] if row else 'Item #' + ident,
                            'category': 'Item', 'description': '', 'level': None, 'aliases': ''}

    def npc(ident):
        ident = str(ident)
        if positive(ident):
            npcs[ident] = {'id': ident, 'name': studio.mobs.get(ident, {}).get('name', 'NPC #' + ident)}

    def add_recipe(record):
        record['materials'] = [{'item': str(row['item']), 'count': quantity(row['count'], 1)} for row in record['materials']]
        record['outputs'] = [{'item': str(row['item']), 'count': quantity(row['count'], 1)} for row in record['outputs']]
        if any(not positive(row['item']) for row in record['materials'] + record['outputs']):
            raise ValueError('Invalid reference item id.')
        record['cost'] = quantity(record['cost'])
        chance = float(record['chance'])
        if not 0 <= chance <= 100:
            raise ValueError('Invalid base crafting chance.')
        record['chance'] = chance
        recipes[record['id']] = record
        for ident in record['npcs']:
            npc(ident)
        for row in record['materials'] + record['outputs']:
            ensure(row['item'])
        for row in record['materials']:
            used[row['item']].append(['recipe', record['id']])
        for row in record['outputs']:
            created[row['item']].append(record['id'])

    # Cube APIs already parse the installed format and retain table precedence.
    for path in studio.recipe_sources().values():
        read(path)
    for row in studio.recipes():
        try:
            fields = row['fields']
            ident = 'cube:' + row['source'] + ':' + str(row['index'])
            add_recipe({'id': ident, 'system': 'Cube', 'materials': row['materials'], 'outputs': row['rewards'],
                        'cost': fields.get('gold', '0'), 'chance': fields.get('percent', '100'),
                        'npcs': [fields['npc']] if positive(fields.get('npc', '')) else [],
                        'requirements': ['NPC menu availability unconfirmed'] if not row.get('npcSupported') else ['NPC entry conditions apply'],
                        'provenance': 'installed-configuration'})
        except (ValueError, KeyError, TypeError):
            warnings.append('An unsupported Cube recipe was omitted.')

    # Use current database rows directly: catalog() also overlays pending edits.
    from metin2_studio.crafting_access import discover_native
    routes = discover_native(studio)
    windows = defaultdict(list)
    for route in routes:
        windows[str(route['window'])].append(str(route['id']))
        for path in route.get('evidence', []):
            read(root / path)
    native_kind = 'current-database'
    try:
        native = studio.native_crafting.live(fresh=True)['rows']
    except (ValueError, OSError, AttributeError):
        native_kind = 'database-seed'
        native = {}
        for row in sql_rows(sql, 'crafting_proto'):
            if len(row) < 9:
                continue
            native[row[0]] = {'proto': dict(zip(('vnum', 'item_vnum', 'count', 'price', 'chance', 'recipe', 'req_progress', 'req_level', 'recipe_vnum'), row)), 'windows': {}}
        assignments = read(compose / 'mariadb/playerbot/crafting_windows.sql').decode('utf-8', 'replace')
        match = re.search(r'INSERT INTO world\.tmp_crafting_window\s*\([^)]*\)\s*VALUES\s*(.*?);', assignments, re.S)
        if match:
            for window, recipe, order in re.findall(r'\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', match[1]):
                if recipe in native:
                    native[recipe]['windows'][window] = int(order)
        warnings.append('Native crafting uses database seeds because a current database snapshot was unavailable.')
    sources['native-crafting:' + native_kind] = checksum(native)
    for ident, row in native.items():
        proto = row.get('proto')
        if not proto:
            continue
        try:
            assignments = sorted({npc_id for window in row['windows'] for npc_id in windows[window]})
            requirements = ['Level ' + str(proto['req_level'])] if int(proto['req_level']) else []
            if int(proto['req_progress']) or int(proto['recipe_vnum']):
                requirements.append('Recipe/progress requirement: item #%s, progress %s' % (proto['recipe_vnum'], proto['req_progress']))
            requirements.append('NPC entry conditions apply' if assignments else 'NPC menu availability unconfirmed')
            add_recipe({'id': 'native:' + str(ident), 'system': 'Native', 'materials': pairs(proto['recipe']),
                        'outputs': [{'item': str(proto['item_vnum']), 'count': proto['count']}],
                        'cost': proto['price'], 'chance': proto['chance'], 'npcs': assignments,
                        'requirements': requirements, 'provenance': native_kind})
        except (ValueError, KeyError, TypeError):
            warnings.append('An unsupported native recipe was omitted.')

    refine_sets = {row[0]: row for row in sql_rows(sql, 'refine_proto') if len(row) >= 15}
    for ident, row in definitions.items():
        definition = refine_sets.get(row[15])
        if row[14] in ('0', ident) or not definition or not positive(row[14]):
            continue
        try:
            materials = [{'item': definition[i], 'count': quantity(definition[i + 1], 1)} for i in range(1, 11, 2) if definition[i] != '0']
            record = {'id': ident, 'from': ident, 'to': row[14], 'materials': materials,
                      'cost': quantity(definition[11]), 'chance': float(definition[14]), 'provenance': 'database-seed'}
            if not 0 <= record['chance'] <= 100:
                raise ValueError()
            upgrades[ident] = record
            for value in [ident, row[14]] + [material['item'] for material in materials]:
                ensure(value)
            used[ident].append(['upgrade', ident])
            for material in materials:
                used[material['item']].append(['upgrade', ident])
        except (ValueError, TypeError):
            warnings.append('An unsupported upgrade definition was omitted.')

    shops = {row[0]: row for row in sql_rows(sql, 'shop') if len(row) >= 3}
    for row in sql_rows(sql, 'shop_item'):
        if len(row) < 3 or row[0] not in shops or not positive(row[1]):
            continue
        shop = shops[row[0]]
        key = 'shop:' + row[0]
        npc(shop[2])
        origins[key] = {'id': key, 'name': studio.mobs.get(shop[2], {}).get('name', shop[1]),
                        'kind': 'NPC shop', 'npc': shop[2], 'provenance': 'database-seed'}
        ensure(row[1])
        obtained[row[1]].append(key)

    # Preserve Studio's replacement precedence and resolve explicit shared pools.
    raw_sources = {}
    for source, (path, filename, _) in studio.sources.items():
        actual = game / 'share-add/special_item_group.moonlight.txt' if source == 'chest-moonlight' and not path.exists() else path
        raw_sources[source] = read(actual)
    meta = {(row['source'], row['key']): row for row in studio.groups(raw_sources)}
    groups, pools = [], defaultdict(list)
    for source, (_, filename, _) in studio.sources.items():
        for group in studio.dt.logical_groups(filename, raw_sources[source]):
            if (source, group.key) in meta:
                node = (source, group, meta[source, group.key])
                groups.append(node)
                if source.startswith('chest'):
                    pools[meta[source, group.key]['id']].append(node)
    for source, group, info in groups:
        # A shared reward table is not necessarily a physical chest.
        known_chest = 'chests' in studio.items.get(info['id'], {}).get('catalogGroups', []) and info['category'] != 'pool'
        kind = 'Monster' if source.startswith('mob') else 'Chest' if known_chest else 'Reward table'
        key = 'drop:' + source + ':' + group.key
        origins[key] = {'id': key, 'name': info['name'], 'kind': kind, 'entity': info['id'],
                        'provenance': 'installed-configuration'}
        pending, seen, found = [(source, group)], set(), set()
        while pending:
            src, current = pending.pop()
            marker = (src, current.key)
            if marker in seen:
                continue
            seen.add(marker)
            if len(seen) > 1024:
                warnings.append('An overly large shared reward graph was truncated.')
                break
            for entry in current.entries:
                try:
                    active = float(entry.prob) > 0 and float(entry.count) > 0
                except ValueError:
                    active = False
                if not active:
                    continue
                if entry.item.startswith('s'):
                    pending.extend((child[0], child[1]) for child in pools.get(entry.item[1:], []))
                elif positive(entry.item):
                    found.add(entry.item)
        for ident in sorted(found):
            ensure(ident)
            obtained[ident].append(key)

    # The exporter deliberately does not imply complete engine/drop coverage.
    warnings.extend(['Upgrade and shop references use the installed database seed.',
                     'Saved configuration can differ from deployed tables and runtime overrides.',
                     'Dynamic quests, engine drops and additional build-time drop transformations are outside coverage.'])
    index = {'schema_version': SCHEMA, 'items': items, 'recipes': recipes, 'upgrades': upgrades,
             'origins': origins, 'npcs': npcs,
             'crafted': {key: sorted(set(value)) for key, value in created.items()},
             'uses': {key: sorted({tuple(row) for row in value}) for key, value in used.items()},
             'obtained': {key: sorted(set(value)) for key, value in obtained.items()},
             'meta': {'server_version': version, 'source_hashes': sources, 'native_crafting': native_kind,
                      'warnings': sorted(set(warnings)), 'scope': 'Local reference data; base chances per attempt'}}
    if catalogue_snapshot is not None:
        index['meta']['catalogue_revision'] = catalogue_snapshot['revision']
        if catalogue_service.local_fingerprint != fingerprint(catalogue_service.paths):
            raise ValueError('Catalogue sources changed during reference generation. Review again.')
    index['meta']['snapshot'] = checksum(index)
    for path, raw in captured.items():
        if (path.read_bytes() if path.is_file() else b'') != raw:
            raise ValueError('Reference sources changed during snapshot generation. Review again.')
    if len(encoded(index)) > MAX_BYTES:
        raise ValueError('Pocket Wiki reference index exceeds 24 MiB.')
    return index
