"""Read-only discovery and carefully scoped plans for Studio's guided editors."""
from collections import Counter, defaultdict
import copy
import re
import unicodedata

from item_usage import item_drop_summary


def folded(value):
    return ''.join(char for char in unicodedata.normalize('NFKD', str(value)).casefold() if not unicodedata.combining(char))


def drop_index(studio):
    item_drop_summary(studio, '25041')  # Reuse the cycle-safe, byte-invalidated index.
    cache = studio._drop_hover_cache
    groups, targets = [], defaultdict(dict)
    for node in cache['nodes']:
        items, pools, visited, pending = set(), set(), set(), [node]
        while pending:
            current = pending.pop()
            key = current['meta']['source'], current['meta']['key']
            if key in visited:
                continue
            visited.add(key)
            for entry in current['group'].entries:
                if entry.item.startswith('s'):
                    pools.add(entry.item[1:])
                    pending.extend(cache['pools'].get(entry.item[1:], []))
                else:
                    items.add(entry.item)
        meta = node['meta']
        groups.append({**meta, 'contains': sorted(items), 'pools': sorted(pools)})
        if meta['source'].startswith('mob') or 'chests' in studio.items.get(meta['id'], {}).get('catalogGroups', []):
            for ident in pools:
                targets[ident][('mob' if meta['source'].startswith('mob') else 'item', meta['id'])] = {key: meta[key] for key in ('id', 'name', 'level', 'category')}
    return {'groups': groups, 'pools': [{'id': ident, 'targets': list(rows.values()), 'count': len(rows)} for ident, rows in targets.items()]}


def combined_drops(studio, ident, kind='mob'):
    index = drop_index(studio)
    cache = studio._drop_hover_cache
    roots = [node for node in cache['nodes'] if node['meta']['id'] == str(ident) and node['meta']['source'].startswith('mob' if kind == 'mob' else 'chest')]
    if not roots:
        raise ValueError('No configured drop groups were found for this target.')
    rows, warnings = [], []
    def visit(node, path, seen):
        marker = node['meta']['source'], node['meta']['key']
        if marker in seen or len(path) > 24:
            warnings.append('A cyclic or overly deep pool path was omitted.')
            return
        for number, entry in enumerate(node['group'].entries, 1):
            if len(rows) >= 3000:
                warnings.append('The preview is limited to 3,000 configured paths.')
                return
            step = {'source': node['meta']['source'], 'key': node['meta']['key'], 'name': node['meta']['name'], 'entry': number, 'item': entry.item, 'count': entry.count, 'parameter': entry.prob, 'type': node['meta']['type']}
            chain = path + [step]
            if entry.item.startswith('s'):
                children = cache['pools'].get(entry.item[1:], [])
                if not children:
                    warnings.append('Unresolved shared pool ' + entry.item)
                for child in children:
                    visit(child, chain, seen | {marker})
            else:
                rows.append({'item': entry.item, 'name': studio.items.get(entry.item, {}).get('name', '#' + entry.item), 'count': entry.count, 'parameter': entry.prob, 'source': node['meta']['source'] if not path else path[0]['source'], 'path': chain})
    for root in roots:
        visit(root, [], set())
    duplicates = Counter(row['item'] for row in rows)
    return {'target': roots[0]['meta'], 'groups': [node['meta'] for node in roots], 'rows': rows, 'distinctItems': len(duplicates),
            'repeatedItems': [{'id': ident, 'name': studio.items.get(ident, {}).get('name', '#' + ident), 'paths': count} for ident, count in duplicates.items() if count > 1],
            'warnings': list(dict.fromkeys(warnings)), 'scope': 'Configured sources covered by Studio, including base/add-on groups and explicit shared pools. Runtime panel overrides, global rates, level penalties and other quest/engine sources may change actual drops. Path parameters are not a final drop probability.'}


def bulk_drop_plan(studio, values):
    ident, field, value = str(values.get('item', '')), str(values.get('field', 'prob')), str(values.get('value', ''))
    if ident not in studio.items or field not in ('prob', 'count') or not re.fullmatch(r'\d+(?:\.\d+)?', value):
        raise ValueError('Choose a physical item, count/base parameter and valid numeric value.')
    selected = values.get('groups', [])
    if not isinstance(selected, list) or not 1 <= len(selected) <= 100:
        raise ValueError('Select between one and 100 drop groups.')
    raw_files, changed, skipped, visited = {}, [], [], set()
    known_pools = {row['key'] for row in studio.groups() if row['source'].startswith('chest')}
    for selection in selected:
        source, key = str(selection.get('source', '')), str(selection.get('key', ''))
        if source not in studio.sources or (source, key) in visited:
            continue
        visited.add((source, key))
        path, filename, _ = studio.sources[source]
        raw = raw_files.get(path, studio.source_raw(source))
        group = next((row for row in studio.dt.logical_groups(filename, raw) if row.key == key), None)
        if not group:
            raise ValueError('A selected group no longer exists. Refresh the drop catalog.')
        matches = [entry for entry in group.entries if entry.item == ident]
        if not matches:
            skipped.append(key + ': no direct entry; shared-pool contents were not changed')
            continue
        group = copy.deepcopy(group)
        count = 0
        for entry in group.entries:
            if entry.item == ident and getattr(entry, field) != value:
                setattr(entry, field, value)
                count += 1
        if not count:
            continue
        problems = studio.dt.check_group(group, lambda item: str(item) in studio.items, lambda mob: str(mob) in studio.mobs, known_pools)
        if problems:
            raise ValueError('\n'.join(studio.dt.describe(problem, 'en') for problem in problems))
        override = studio.dt.apply_change(filename, None, 'edit', key, group)
        raw_files[path] = studio.dt.merge(filename, raw, studio.dt.render_override(override))
        changed.append(key + ' (' + str(count) + ' direct entries)')
    hint = 'Only matching direct entries are edited. Shared pools and absent rewards are left unchanged. Targets: ' + ', '.join(changed)
    if skipped:
        hint += '. Skipped: ' + '; '.join(skipped)
    return studio.plan('Bulk drop edit: ' + studio.items[ident]['name'], raw_files, hint)


def search(studio, query, content=False):
    query = folded(query).strip()
    if not 2 <= len(query) <= 120:
        return {'results': [], 'truncated': False}
    words = query.split()
    matches = lambda text: all(word in folded(text) for word in words)
    results = []
    for item in studio.items.values():
        if matches(item['id'] + ' ' + item['name'] + ' ' + item.get('catalogLabel', '')):
            results.append({'kind': 'item', 'id': item['id'], 'name': item['name'], 'detail': item.get('catalogLabel', '')})
            if len(results) >= 40:
                break
    for mob in studio.mobs.values():
        if matches(mob['id'] + ' ' + mob['name']):
            results.append({'kind': 'target', 'id': mob['id'], 'name': mob['name'], 'detail': mob['category'] + ' · level ' + str(mob['level'])})
            if len(results) >= 65:
                break
    for recipe in studio.recipes():
        if matches(recipe['name'] + ' ' + recipe['npcName'] + ' ' + ' '.join(entry['item'] for entry in recipe['materials'] + recipe['rewards'])):
            results.append({'kind': 'recipe', 'source': recipe['source'], 'index': recipe['index'], 'name': recipe['name'], 'detail': recipe['npcName']})
            if len(results) >= 90:
                break
    for schema in studio.settings_schema.values():
        if matches(schema['key'] + ' ' + schema['label'] + ' ' + schema['group']):
            results.append({'kind': 'setting', 'id': schema['key'], 'name': schema['label'], 'detail': schema['group']})
    files = studio.inventory()
    for file in files:
        if matches(file['name'] + ' ' + file['id'] + ' ' + file['category']):
            results.append({'kind': 'file', 'id': file['id'], 'name': file['name'], 'detail': file['category']})
            if len(results) >= 120:
                break
    if content:
        for file in files:
            path = studio.safe(studio.root / file['id'])
            raw = studio.read(path)
            if raw is None:
                continue
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                text = raw.decode('latin1')
            for line, text_line in enumerate(text.splitlines(), 1):
                if matches(text_line):
                    results.append({'kind': 'file', 'id': file['id'], 'name': file['name'], 'line': line, 'detail': text_line.strip()[:220]})
                    break
            if len(results) >= 160:
                break
    return {'results': results[:160], 'truncated': len(results) >= 160, 'scope': 'Installed catalog and current editor source view. File contents are searched only when selected.'}


FISH_COLUMNS = ['Legacy label', 'Item ID', 'Dead item ID', 'Grilled item ID', 'Weight table 1', 'Weight table 2', 'Weight table 3', 'Weight table 4', 'Difficulty', 'Time type', 'Minimum length parameter', 'Maximum length parameter', 'Extra length parameter'] + ['USED' + str(index) + ' (raw outcome code)' for index in range(10)]
SPAWN_COLUMNS = ['Spawn type', 'X', 'Y', 'X range', 'Y range', 'Z section', 'Direction', 'Respawn interval', 'Spawn percentage', 'Maximum count', 'Mob or group ID']


def table_schema(file_id):
    name = file_id.replace('\\', '/').split('/')[-1]
    if name == 'fishing.txt':
        return {'kind': 'fishing', 'columns': FISH_COLUMNS, 'readonly': [0], 'references': [1, 2, 3], 'notes': 'Item IDs resolve to catalog names. The legacy label bytes are preserved. Weight-table selection, time types and USED outcome codes retain the installed format; no final catch probability is inferred.'}
    if '/map/' in file_id.replace('\\', '/') and name in ('regen', 'npc', 'boss', 'stone', 'regen.txt', 'npc.txt', 'boss.txt', 'stone.txt'):
        return {'kind': 'spawns', 'columns': SPAWN_COLUMNS, 'readonly': [], 'references': [10], 'notes': 'Spawn coordinates and parameters are the installed map format. The final ID may identify a group rather than a single monster; unresolved group IDs are preserved.'}
    return None


def table_view(studio, file):
    schema = table_schema(file['id'])
    if not schema:
        return None
    raw = studio.read(studio.safe(studio.root / file['id']))
    rows = []
    for line, content in enumerate(raw.splitlines(keepends=True), 1):
        code = content.split(b'#', 1)[0]
        tokens = list(re.finditer(rb'[^\s]+', code))
        if not tokens:
            continue
        valid = len(tokens) == len(schema['columns'])
        values = []
        for index, token in enumerate(tokens):
            value = token.group().decode('ascii', 'replace')
            if schema['kind'] == 'fishing' and index == 0:
                ident = tokens[1].group().decode('ascii', 'replace') if len(tokens) > 1 else ''
                value = studio.items.get(ident, {}).get('name', 'Legacy label (preserved)')
            values.append(value)
        ident = values[1] if schema['kind'] == 'fishing' and len(values) > 1 else values[-1]
        catalog = studio.items if schema['kind'] == 'fishing' else studio.mobs
        rows.append({'line': line, 'values': values, 'valid': valid, 'name': catalog.get(ident, {}).get('name', '#' + ident)})
    return {'schema': schema, 'rows': rows, 'hash': file['hash'], 'id': file['id']}


def table_plan(studio, values):
    file = studio.file(str(values.get('id', '')))
    schema = table_schema(file['id'])
    if not schema or values.get('hash') != file['hash']:
        raise ValueError('The table changed or is not supported. Reopen it before editing.')
    path = studio.safe(studio.root / file['id'])
    raw = studio.read(path)
    lines = raw.splitlines(keepends=True)
    edits = values.get('edits', [])
    if not isinstance(edits, list) or not 1 <= len(edits) <= 500:
        raise ValueError('Review between one and 500 table field edits at a time.')
    by_line = defaultdict(dict)
    for edit in edits:
        line, column = int(edit.get('line', 0)), int(edit.get('column', -1))
        value = str(edit.get('value', ''))
        if not 1 <= line <= len(lines) or not 0 <= column < len(schema['columns']) or column in schema['readonly']:
            raise ValueError('A table edit references a read-only or missing field.')
        if schema['kind'] == 'spawns' and column == 0:
            if not re.fullmatch('[A-Za-z]{1,2}', value):
                raise ValueError('Use a valid installed spawn type token.')
        elif schema['kind'] == 'spawns' and column == 7:
            if not re.fullmatch(r'[0-9]{1,7}[smh]?', value):
                raise ValueError('Respawn intervals use a number with optional s, m or h.')
        elif not re.fullmatch(r'-?[0-9]{1,10}', value):
            raise ValueError('Table parameters must be whole numbers without spaces.')
        if schema['kind'] == 'fishing' and not 0 <= int(value) <= 2147483647:
            raise ValueError('Fishing parameters must be non-negative 32-bit values.')
        if schema['kind'] == 'spawns' and column == 8 and not 0 <= int(value) <= 100:
            raise ValueError('Spawn percentage must be between 0 and 100.')
        if schema['kind'] == 'spawns' and column == 9 and not 0 <= int(value) <= 10000:
            raise ValueError('Spawn count must be between 0 and 10,000.')
        if schema['kind'] == 'fishing' and column in (1, 2, 3) and value != '0' and value not in studio.items:
            raise ValueError('Choose a known catalog item ID, or 0 for no item.')
        by_line[line][column] = value.encode('ascii')
    for line, changes in by_line.items():
        original = lines[line-1]
        code = original.split(b'#', 1)[0]
        tokens = list(re.finditer(rb'[^\s]+', code))
        if len(tokens) != len(schema['columns']):
            raise ValueError('This row has an unsupported field count. Use the advanced editor for it.')
        out, position = [], 0
        for column, value in sorted(changes.items()):
            token = tokens[column]
            out.extend((original[position:token.start()], value))
            position = token.end()
        lines[line-1] = b''.join(out) + original[position:]
    return studio.plan('Update guided table: ' + path.name, {path: b''.join(lines)}, 'Only selected table tokens are changed. Original labels, comments, delimiters and line endings are preserved. Engine-specific behaviour still needs a successful build and in-game verification.')
