"""Read-only item references in Studio's installed files and database seed.

Drop paths are followed only through explicit s<pool-id> references. Plain
numeric item IDs never stand for a reward pool, even when the numbers match.
"""
from collections import defaultdict, deque
from pathlib import Path
import re


def drop_route(start, ident, pools):
    """One shortest matching path per group, with cycle-safe traversal."""
    queue = deque([(start, [])])
    visited = set()
    while queue:
        node, path = queue.popleft()
        key = (node['meta']['source'], node['meta']['key'])
        if key in visited:
            continue
        visited.add(key)
        for index, entry in enumerate(node['group'].entries):
            step = {'group': node['meta'], 'entry': index + 1,
                    'item': entry.item, 'count': entry.count, 'parameter': entry.prob}
            if entry.item == ident:
                return path + [step]
            if entry.item.startswith('s'):
                for child in pools.get(entry.item[1:], []):
                    queue.append((child, path + [step]))
    return None


def drop_summary(ident, nodes, pools, items):
    """Count distinct configured targets, not rows, groups or loot rolls."""
    targets = {key: {} for key in ('metins', 'bosses', 'monsters', 'chests', 'pools', 'other')}
    zero_parameter = False
    for node in nodes:
        route = drop_route(node, ident, pools)
        if not route:
            continue
        meta = node['meta']
        if meta['source'].startswith('mob'):
            bucket = {'metin': 'metins', 'boss': 'bosses', 'monster': 'monsters'}.get(meta['category'], 'other')
        else:
            known_chest = meta['category'] != 'pool' and 'chests' in items.get(meta['id'], {}).get('catalogGroups', [])
            bucket = 'chests' if known_chest else 'pools'
        targets[bucket][meta['id']] = {key: meta[key] for key in ('id', 'name', 'level')}
        zero_parameter |= any(float(step['parameter'] or 0) <= 0 for step in route)
    return {'id': ident, 'counts': {key: len(rows) for key, rows in targets.items()},
            'metins': sorted(targets['metins'].values(), key=lambda row: (row['level'] or 0, int(row['id']))),
            'zeroParameter': zero_parameter}


def item_drop_summary(studio, ident):
    """Fast hover lookup. Invalidate the in-memory index when any drop bytes change.

    Only reads the drop editor's sources; no recipe, quest or SQL scans per hover.
    The caller holds Studio's lock, including during cache replacement.
    """
    ident = str(ident)
    numeric = ident.removeprefix('s')
    if not re.fullmatch(r'[1-9][0-9]{0,9}', numeric) or int(numeric) > 4294967295:
        raise ValueError('Enter a valid item or shared reward pool ID.')
    raw_sources = {source: studio.source_raw(source) for source in studio.sources}
    cache = getattr(studio, '_drop_hover_cache', None)
    if cache is None or cache['sources'] != raw_sources:
        metadata = {(row['source'], row['key']): row for row in studio.groups(raw_sources)}
        nodes, pools = [], defaultdict(list)
        for source, (_, filename, _) in studio.sources.items():
            for group in studio.dt.logical_groups(filename, raw_sources[source]):
                meta = metadata.get((source, group.key))
                if meta is None:
                    continue
                node = {'meta': meta, 'group': group}
                nodes.append(node)
                if source.startswith('chest'):
                    pools[meta['id']].append(node)
        cache = {'sources': raw_sources, 'nodes': nodes, 'pools': pools, 'items': {}}
        studio._drop_hover_cache = cache
    if ident not in cache['items']:
        cache['items'][ident] = drop_summary(ident, cache['nodes'], cache['pools'], studio.items)
    return cache['items'][ident]


def item_usage(studio, ident, sql_rows, native=False):
    ident = str(ident)
    if not re.fullmatch(r'[1-9][0-9]{0,9}', ident) or int(ident) > 4294967295:
        raise ValueError('Enter a numeric item ID between 1 and 4294967295.')
    sections = {key: [] for key in ('drops', 'chests', 'pools', 'crafted', 'ingredients', 'shops', 'refining', 'files')}
    scanned, warnings = set(), []

    def relative(path):
        return Path(path).relative_to(studio.root).as_posix()

    def scan(path):
        path = Path(path)
        if not path.is_file():
            return ''
        scanned.add(relative(path))
        return path.read_text('utf-8', errors='replace')

    # Use the same source precedence and engine-aware parser as the drop editor.
    metadata = {(g['source'], g['key']): g for g in studio.groups()}
    nodes, pools = [], defaultdict(list)
    for source, (path, filename, _) in studio.sources.items():
        actual_path = studio.game / 'share-add/special_item_group.moonlight.txt' if source == 'chest-moonlight' and not path.exists() else path
        scanned.add(relative(actual_path))
        for group in studio.dt.logical_groups(filename, studio.source_raw(source)):
            meta = metadata.get((source, group.key))
            if meta is None:
                continue  # Replaced chest definition; not another active source.
            node = {'meta': meta, 'group': group}
            nodes.append(node)
            if source.startswith('chest'):
                pools[meta['id']].append(node)
    for node in nodes:
        route = drop_route(node, ident, pools)
        if not route:
            continue
        meta = node['meta']
        known_chest = meta['category'] != 'pool' and 'chests' in studio.items.get(meta['id'], {}).get('catalogGroups', [])
        bucket = 'drops' if meta['source'].startswith('mob') else 'chests' if known_chest else 'pools'
        actions = [{'kind': 'drop', 'source': meta['source'], 'key': meta['key'], 'label': 'Open drop group'}]
        if len(route) > 1:
            leaf = route[-1]['group']
            actions.append({'kind': 'drop', 'source': leaf['source'], 'key': leaf['key'], 'label': 'Open reward pool'})
        sections[bucket].append({
            'name': meta['name'], 'file': meta['file'].replace('\\', '/'),
            'summary': f"#{meta['id']} · {meta['type']} · " + ('Direct entry' if len(route) == 1 else 'Via ' + ' → '.join('pool #' + step['group']['id'] for step in route[1:])),
            'details': ['First matching route: ' + ' → '.join(f"{step['group']['name']} [entry {step['entry']}]" for step in route),
                        f"Final entry quantity: {route[-1]['count']} · Parameter: {route[-1]['parameter']}"] +
                       (['A zero parameter appears on this route; this is a configuration reference, not a confirmed obtainable drop.'] if any(float(step['parameter'] or 0) <= 0 for step in route) else []),
            'actions': actions,
        })

    # Cube recipes reflect current saved files, rather than a cached index.
    for recipe in studio.recipes():
        scanned.add(recipe['file'])
        for field, bucket in (('rewards', 'crafted'), ('materials', 'ingredients')):
            if not any(row['item'] == ident for row in recipe[field]):
                continue
            sections[bucket].append({
                'name': recipe['name'], 'file': recipe['file'],
                'summary': f"{recipe['npcName']} · Cube recipe · {recipe['fields'].get('percent', '?')}% success · {recipe['fields'].get('gold', '0')} Yang",
                'recipe': recipe, 'details': [],
                'actions': [{'kind': 'recipe', 'source': recipe['source'], 'index': recipe['index'], 'hash': recipe['hash'], 'label': 'Open recipe'}],
            })

    # Database-only systems are explicitly labeled seed references, never live.
    sql_path = studio.compose / 'mariadb/initdb.d/dumps/world.sql'
    sql = scan(sql_path)
    seed_items = {row[0]: row for row in sql_rows(sql, 'item_proto') if len(row) > 15}

    def item_name(value):
        return studio.items.get(value, {}).get('name') or (seed_items[value][2] if value in seed_items else '#' + value)

    def describe_rows(rows):
        return ', '.join(f"{item_name(row['item'])} ×{row['count']} (#{row['item']})" for row in rows)

    window_path = studio.compose / 'mariadb/playerbot/crafting_windows.sql'
    window_sql = scan(window_path)
    window_recipes = defaultdict(list)
    block = re.search(r'INSERT INTO world\.tmp_crafting_window\s*\([^)]*\)\s*VALUES\s*(.*?);', window_sql, re.S)
    if block:
        for window, recipe_id, _ in re.findall(r'\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', block[1]):
            window_recipes[recipe_id].append(window)
    constants_path = studio.locale / 'quest/libs/crafting/crafting_data.lua'
    constants = dict(re.findall(r'(?m)^\s*(CRAFTING_[A-Z_]+)\s*=\s*(\d+)', scan(constants_path)))
    window_names = {value: key.removeprefix('CRAFTING_').replace('_', ' ').title() + ' window' for key, value in constants.items()}
    window_npcs = defaultdict(set)
    # Resolve only literal quest handlers that actually call crafting.open.
    for folder in (studio.locale / 'quest/quest', studio.game / 'quest'):
        if not folder.exists():
            continue
        for path in sorted(folder.rglob('*')):
            if path.suffix not in ('.lua', '.quest') or '_unused' in path.parts:
                continue
            text = scan(path)
            for clause in re.finditer(r'(?ms)^\s*when\s+(.*?)(?=^\s*when\s|\Z)', text):
                npcs = re.findall(r'(?:^|\bor\s+)(\d+)\.chat', clause[1])
                for window in re.findall(r'crafting\.open\(\s*(\w+)\s*\)', clause[1]):
                    if window in constants:
                        window_npcs[constants[window]].update(npcs)
    for row in sql_rows(sql, 'crafting_proto'):
        if len(row) < 9:
            continue
        pieces = row[5].split(',') if row[5] else []
        if len(pieces) % 2 or not all(p.strip().isdigit() for p in pieces):
            warnings.append('A database seed crafting recipe has an unsupported ingredient format.')
            continue
        materials = [{'item': pieces[i].strip(), 'count': pieces[i + 1].strip()} for i in range(0, len(pieces), 2)]
        rewards = [{'item': row[1], 'count': row[2]}]
        windows = []
        for window in window_recipes[row[0]]:
            npcs = window_npcs[window] or ({window} if window in studio.mobs else set())
            windows.append(' / '.join(studio.mobs.get(npc, {}).get('name', '#' + npc) for npc in sorted(npcs)) or window_names.get(window, 'Window #' + window))
        summary = f"{' / '.join(windows) or 'Unassigned in window seed'} · Native crafting #{row[0]} · {row[4]}% success · {row[3]} Yang · Database seed"
        details = ['Ingredients: ' + describe_rows(materials), 'Result: ' + describe_rows(rewards)]
        if not windows:
            details.append('No NPC window assignment was found in the seed; crafting availability is not confirmed.')
        if row[7] != '0':
            details.append('Required character level: ' + row[7])
        if row[6] != '0' or row[8] != '0':
            details.append(f"Recipe/progress requirement: #{row[8]} · Progress {row[6]}")
        base = {'name': item_name(row[1]), 'file': relative(sql_path), 'summary': summary,
                'details': details, 'actions': [], 'seed': True, 'nativeCraft': True}
        if row[1] == ident:
            sections['crafted'].append(base.copy())
        if any(material['item'] == ident for material in materials):
            sections['ingredients'].append(base.copy())
        if row[8] == ident:
            sections['ingredients'].append({**base, 'summary': summary + ' · Recipe/progress requirement'})
    for bucket in ('crafted', 'ingredients'):
        for result in sections[bucket]:
            recipe = result.pop('recipe', None)
            if recipe:
                result['details'] = ['Ingredients: ' + describe_rows(recipe['materials']), 'Result: ' + describe_rows(recipe['rewards'])]

    shops = {row[0]: row for row in sql_rows(sql, 'shop') if len(row) >= 3}
    for row in sql_rows(sql, 'shop_item'):
        if len(row) < 3 or row[1] != ident:
            continue
        shop = shops.get(row[0], [row[0], 'Unknown shop', '0'])
        sections['shops'].append({'name': studio.mobs.get(shop[2], {}).get('name', shop[1]), 'file': relative(sql_path),
                                  'summary': f"Shop #{shop[0]} · Quantity {row[2]} · Database seed", 'details': [], 'actions': [], 'seed': True})
    refinements = {row[0]: row for row in sql_rows(sql, 'refine_proto') if len(row) >= 15}
    for source, item in seed_items.items():
        recipe = refinements.get(item[15])
        if not recipe or item[14] == '0':
            continue
        materials = [{'item': recipe[i], 'count': recipe[i + 1]} for i in range(1, 11, 2) if recipe[i] != '0']
        if source != ident and item[14] != ident and not any(material['item'] == ident for material in materials):
            continue
        role = 'Upgrade source' if source == ident else 'Upgrade result' if item[14] == ident else 'Upgrade ingredient'
        sections['refining'].append({'name': f"{item_name(source)} → {item_name(item[14])}", 'file': relative(sql_path),
                                    'summary': f"{role} · Refine set #{recipe[0]} · {recipe[14]}% base chance · {recipe[11]} Yang · Database seed",
                                    'details': ['Materials: ' + (describe_rows(materials) or 'None listed')], 'actions': [], 'seed': True})

    # Other sources remain literal references: no claim that an arbitrary number
    # is an item reward, nor that an uncompiled quest is active in the game.
    mention_total = 0
    token = re.compile(r'(?<![\w.])' + re.escape(ident) + r'(?![\w.])')
    explicit_item = re.compile(r'(?:\bpc\.(?:give_item2?|count_item|remove_item|give_item2_select)|\bitem_name)\s*\(\s*' + re.escape(ident) + r'\b|\bwhen\s+' + re.escape(ident) + r'\.(?:use|take)\b|\b(?:item_vnum|vnum)\s*=\s*' + re.escape(ident) + r'\b|\b(?:item|reward)\s+' + re.escape(ident) + r'\b')
    eligible_categories = {'Quests', 'Package quests', 'Custom quests', 'Items', 'Shops', 'Build overrides', 'Crafting', 'Drops'}
    structured = {relative(path) for path in studio.recipe_sources().values()} | {m['file'].replace('\\', '/') for m in metadata.values()}
    for entry in sorted(studio.inventory(), key=lambda e: e['id']):
        if entry['category'] not in eligible_categories or entry['id'] in structured:
            continue
        path = studio.safe(studio.root / entry['id'])
        text = scan(path)
        matches = [(index, line.strip()) for index, line in enumerate(text.splitlines(), 1) if token.search(line) and not line.lstrip().startswith(('#', '--', '//'))]
        if int(ident) < 1000:
            matches = [(index, line) for index, line in matches if explicit_item.search(line)]
        if not matches:
            continue
        mention_total += len(matches)
        if len(sections['files']) >= 150:
            continue
        sections['files'].append({'name': path.name, 'file': entry['id'], 'summary': f"{entry['category']} · {len(matches)} literal ID reference(s)",
                                  'details': [f"Line {line}: {code[:240]}" for line, code in matches[:4]], 'line': matches[0][0],
                                  'actions': [{'kind': 'file', 'file': entry['id'], 'line': matches[0][0], 'label': 'Open source'}]})
    if len(sections['files']) == 150:
        warnings.append('File mentions show at most 150 files and four matching lines per file.')
    native_note = 'Native crafting, NPC shops and refinement are database seed references, not a live database query. Crafting window assignments can change in the running world.'
    if native:
        current = studio.native_crafting.catalog()
        if current['available']:
            for key in ('crafted', 'ingredients'):
                sections[key] = [row for row in sections[key] if not row.get('nativeCraft')]
            for recipe in current['recipes']:
                matches = [key for key, rows in [('crafted', recipe['rewards']), ('ingredients', recipe['materials'])]
                           if any(str(entry['item']) == ident for entry in rows)]
                details = ['Ingredients: ' + describe_rows(recipe['materials']), 'Result: ' + describe_rows(recipe['rewards']),
                           'Current database with saved Studio overrides; Apply is separate. NPC access requirements still apply.']
                if recipe['conflicted']:
                    details.append('A customised field conflicts with the server; review crafting conflicts.')
                for key in matches:
                    sections[key].append({'name': recipe['name'], 'file': 'world.crafting_proto / world.crafting_window',
                        'summary': f"{recipe['npcName']} · Native crafting #{recipe['index']} · Window #{recipe['window']} · {recipe['fields']['percent']}% · {recipe['fields']['gold']} Yang",
                        'details': details, 'actions': [], 'nativeCraft': True})
            native_note = 'Native crafting reads the current database with saved Studio overrides; pending changes need Apply. NPC shops and refinement remain database seed references.'
        else:
            warnings.append('Current native crafting could not be read; its references fall back to labelled database seeds. ' + current['error'])
    item = studio.items.get(ident, {'id': ident, 'name': item_name(ident), 'catalogLabel': 'Item ID lookup'})
    return {'item': item, 'sections': sections, 'counts': {key: len(value) for key, value in sections.items()},
            'coverage': {'files': len(scanned), 'mentions': mention_total,
                         'notes': ['Saved files only; unsaved drafts are excluded.',
                                   'Drop routes follow shared pools and Studio chest overrides. One matching route is shown per group; runtime rates, build transformations and native-panel overrides can differ.',
                                   native_note,
                                   'File mentions are literal ID matches, not verified item effects or proof that a quest is compiled or active. Dynamic script-generated references may be missing.'],
                         'warnings': list(dict.fromkeys(warnings))}}
