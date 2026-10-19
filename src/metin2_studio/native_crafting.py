"""Studio-owned configuration patches for the game's existing native crafting.

Saving writes JSON only. Database writes happen exclusively in Apply, after
the game stops, using a guarded transaction. Unedited columns and recipes stay
owned by the game package. No client, quest or engine changes are needed.
"""
import copy
import hashlib
import json
import re
import secrets
import subprocess
import time

COLS = ('vnum', 'item_vnum', 'count', 'price', 'chance', 'recipe', 'req_progress', 'req_level', 'recipe_vnum', 'comment')
CONFIG = 'share-add/studio-crafting.json'
EMPTY = {'version': 1, 'recipes': {}, 'accepted': {}}


def validate_document(data):
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('recipes'), dict) or not isinstance(data.get('accepted', {}), dict):
        raise ValueError('Invalid native crafting configuration.')
    for ident, record in data['recipes'].items():
        if not re.fullmatch(r'[1-9][0-9]{0,9}', ident) or int(ident) > 2147483647:
            raise ValueError('Invalid native recipe ID.')
        for key in ('before', 'after'):
            row = record[key]
            if set(row) != {'proto', 'windows'} or not isinstance(row['windows'], dict):
                raise ValueError('Invalid native recipe snapshot.')
            if any(not re.fullmatch(r'[1-9][0-9]{0,9}', str(w)) or int(w) > 4294967295 or type(n) is not int or not 0 <= n <= 4294967295 for w, n in row['windows'].items()):
                raise ValueError('Invalid native window membership.')
            proto = row['proto']
            if proto is None:
                if row['windows']:
                    raise ValueError('A missing recipe cannot have NPC memberships.')
                continue
            if set(proto) != set(COLS) or proto['vnum'] != int(ident):
                raise ValueError('Invalid native recipe definition.')
            for column in set(COLS) - {'comment', 'recipe'}:
                low, high = (1 if column in ('vnum', 'item_vnum', 'count', 'chance') else 0), (100 if column == 'chance' else 255 if column == 'req_level' else 2147483647)
                if type(proto[column]) is not int or not low <= proto[column] <= high:
                    raise ValueError('Invalid native crafting value: ' + column)
            text = proto['recipe']
            if not isinstance(text, str) or len(text) > 255 or not re.fullmatch(r'[1-9][0-9]*(?:,[1-9][0-9]*)+', text):
                raise ValueError('Native ingredients must contain valid item/count pairs.')
            pieces = text.split(',')
            if len(pieces) % 2 or len(pieces) > 20 or len(set(pieces[::2])) != len(pieces[::2]) or any(int(value) > 2147483647 for value in pieces):
                raise ValueError('Invalid or duplicate native ingredients.')
            if proto['comment'] is not None and (not isinstance(proto['comment'], str) or len(proto['comment']) > 255):
                raise ValueError('Invalid native recipe comment.')
    for ident, accepted in data.get('accepted', {}).items():
        if not ident.isdigit() or not isinstance(accepted, dict) or not isinstance(accepted.get('revision'), str):
            raise ValueError('Invalid native crafting conflict choices.')
        for key, value in accepted.items():
            if key != 'revision' and key != 'row' and key not in {'proto.' + c for c in COLS} and not re.fullmatch(r'windows\.[1-9][0-9]*', key):
                raise ValueError('Invalid native crafting conflict field.')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def snapshot(rows):
    result = {}
    for row in rows.get('proto', []):
        proto = dict(zip(COLS, row))
        result[str(row[0])] = {'proto': proto, 'windows': {}}
    for window, recipe, order in rows.get('windows', []):
        result.setdefault(str(recipe), {'proto': None, 'windows': {}})['windows'][str(window)] = int(order)
    return result


def empty_row():
    return {'proto': None, 'windows': {}}


def operations(record):
    if not record:
        return {}
    before, after = record['before'], record['after']
    result = {}
    if before['proto'] is None or after['proto'] is None:
        if before['proto'] != after['proto']:
            result['row'] = [before['proto'], after['proto']]
    else:
        result.update({'proto.' + key: [before['proto'][key], after['proto'][key]]
                       for key in COLS if before['proto'][key] != after['proto'][key]})
    result.update({'windows.' + key: [before['windows'].get(key), after['windows'].get(key)]
                   for key in before['windows'].keys() | after['windows'].keys()
                   if before['windows'].get(key) != after['windows'].get(key)})
    return result


def get_value(row, key):
    if key == 'row':
        return row['proto']
    group, field = key.split('.')
    return (row[group] or {}).get(field)


def set_value(row, key, value):
    if key == 'row':
        row['proto'] = copy.deepcopy(value)
        return
    group, field = key.split('.')
    if group == 'proto' and row['proto'] is None:
        raise ValueError('A customised native recipe was deleted externally. Restore it or accept the server version in the crafting conflict review.')
    if value is None and group == 'windows':
        row[group].pop(field, None)
    else:
        row[group][field] = value


def edited_record(previous, displayed, desired, live):
    """Don't adopt unrelated package changes as new Studio customisations."""
    if displayed['proto'] is None or (previous and previous['before']['proto'] is None):
        return {'before': copy.deepcopy(previous['before'] if previous else empty_row()), 'after': copy.deepcopy(desired)}
    record = {'before': copy.deepcopy(live), 'after': copy.deepcopy(live)}
    old = operations(previous)
    edits = operations({'before': displayed, 'after': desired})
    for key, (before, after) in old.items():
        set_value(record['before'], key, before)
        set_value(record['after'], key, after)
    for key, (before, after) in edits.items():
        if key not in old:
            set_value(record['before'], key, before)
        set_value(record['after'], key, after)
    return record


def transition(previous, wanted, live):
    """Three-way merge only the fields Studio actually changed."""
    targets, conflicts = {}, []
    ids = previous.get('recipes', {}).keys() | wanted.get('recipes', {}).keys()
    for ident in sorted(ids, key=int):
        old = operations(previous.get('recipes', {}).get(ident))
        new = operations(wanted.get('recipes', {}).get(ident))
        current = live.get(ident, empty_row())
        target = copy.deepcopy(current)
        accepted = wanted.get('accepted', {}).get(ident, {})
        old_accepted = previous.get('accepted', {}).get(ident, {})
        for key in sorted(old.keys() | new.keys(), key=lambda k: (k != 'row', k)):
            before = old[key][1] if key in old else new[key][0]
            after = new[key][1] if key in new else old[key][0]
            if key in accepted and accepted.get('revision') != old_accepted.get('revision'):
                before = accepted[key]
                if key not in new:
                    after = accepted[key]
            observed = get_value(current, key)
            if observed != before and observed != after:
                conflicts.append({'recipe': ident, 'field': key, 'expected': before, 'server': observed, 'studio': after})
            if key == 'row' and after is None and set(current['windows']) - set(old_key.split('.')[1] for old_key in old if old_key.startswith('windows.')):
                conflicts.append({'recipe': ident, 'field': 'row', 'expected': before, 'server': observed, 'studio': after,
                                  'reason': 'Other windows now use this Studio-created recipe. Remove those links before deleting its definition.'})
            try:
                set_value(target, key, after)
            except ValueError:
                conflicts.append({'recipe': ident, 'field': key, 'expected': before, 'server': observed, 'studio': after,
                                  'reason': 'The recipe definition is missing from the server.'})
        if target != current:
            targets[ident] = target
    return targets, conflicts


class NativeCrafting:
    def __init__(self, studio):
        self.studio = studio
        self.path = studio.game / CONFIG
        self.cached = None
        self.cached_at = 0

    def config(self):
        raw = self.studio.read(self.path)
        if raw is None:
            return copy.deepcopy(EMPTY)
        try:
            data = json.loads(raw)
            validate_document(data)
            if data['version'] != 1 or not isinstance(data['recipes'], dict) or not isinstance(data.get('accepted', {}), dict):
                raise ValueError()
            for ident, record in data['recipes'].items():
                if not re.fullmatch(r'[1-9][0-9]{0,9}', ident):
                    raise ValueError()
                for key in ('before', 'after'):
                    row = record[key]
                    if set(row) != {'proto', 'windows'} or not isinstance(row['windows'], dict):
                        raise ValueError()
                    if row['proto'] is not None and set(row['proto']) != set(COLS):
                        raise ValueError()
                    if row['proto'] is not None and row['proto']['vnum'] != int(ident):
                        raise ValueError()
                    if any(not str(w).isdigit() or not isinstance(n, int) or n < 0 for w, n in row['windows'].items()):
                        raise ValueError()
            return data
        except (ValueError, KeyError, TypeError):
            raise ValueError('Native crafting configuration is invalid. Restore its saved backup before applying.') from None

    def live(self, fresh=False):
        if not fresh and self.cached is not None and time.time() - self.cached_at < 15:
            return copy.deepcopy(self.cached)
        rows = self.studio.economy.query([
            "SELECT JSON_OBJECT('set','engine','row',JSON_ARRAY(TABLE_NAME,ENGINE)) FROM information_schema.TABLES WHERE TABLE_SCHEMA='world' AND TABLE_NAME IN ('crafting_proto','crafting_window','crafting_window_name');",
            "SELECT JSON_OBJECT('set','proto','row',JSON_ARRAY(" + ','.join('`' + c + '`' for c in COLS) + ")) FROM world.crafting_proto ORDER BY vnum;",
            "SELECT JSON_OBJECT('set','windows','row',JSON_ARRAY(window_id,recipe_id,sort_order)) FROM world.crafting_window ORDER BY window_id,sort_order,recipe_id;",
            "SELECT JSON_OBJECT('set','names','row',JSON_ARRAY(window_id,name)) FROM world.crafting_window_name ORDER BY window_id;"
        ])
        if dict(rows.get('engine', [])) != {name: 'InnoDB' for name in ('crafting_proto', 'crafting_window', 'crafting_window_name')}:
            raise ValueError('Native crafting needs the existing InnoDB crafting tables. No database changes were made.')
        result = {'rows': snapshot(rows), 'names': dict((str(w), name) for w, name in rows.get('names', []))}
        self.cached, self.cached_at = result, time.time()
        return copy.deepcopy(result)

    def applied(self):
        return self.studio.workspace.preference('nativeCraftingApplied', copy.deepcopy(EMPTY))

    def view(self, fresh=False):
        live = self.live(fresh)
        config = self.config()
        targets, conflicts = transition(self.applied(), config, live['rows'])
        effective = copy.deepcopy(live['rows'])
        effective.update(targets)
        return live, config, effective, conflicts

    def catalog(self, fresh=False):
        from metin2_studio.crafting_access import discover_native
        routes = discover_native(self.studio)
        try:
            live, config, effective, conflicts = self.view(fresh)
        except ValueError as error:
            return {'available': False, 'error': str(error), 'recipes': [], 'npcs': routes, 'conflicts': []}
        recipes = []
        for ident, row in effective.items():
            proto = row['proto']
            if proto is None:
                continue
            for window in row['windows']:
                npcs = [r for r in routes if r['window'] == window]
                if not npcs:
                    continue
                values = proto['recipe'].split(',')
                materials = [{'item': values[i], 'count': values[i + 1]} for i in range(0, len(values) - 1, 2)]
                recipes.append({'system': 'native', 'source': 'native', 'index': int(ident), 'window': window,
                    'name': self.studio.items.get(str(proto['item_vnum']), {}).get('name', 'Item #' + str(proto['item_vnum'])),
                    'npcName': ', '.join(r['name'] for r in npcs), 'npcIds': [r['id'] for r in npcs], 'npcSupported': True,
                    'fields': {'npc': npcs[0]['id'], 'percent': str(proto['chance']), 'gold': str(proto['price'])},
                    'materials': materials, 'rewards': [{'item': str(proto['item_vnum']), 'count': str(proto['count'])}],
                    'requirements': {key: proto[key] for key in ('req_progress', 'req_level', 'recipe_vnum')},
                    'windows': list(row['windows']), 'sharedWith': [r['name'] for r in routes if r['window'] in row['windows'] and r['window'] != window],
                    'hash': fingerprint(row), 'configHash': fingerprint(config), 'file': self.path.relative_to(self.studio.root).as_posix(),
                    'custom': ident in config['recipes'] and config['recipes'][ident]['before'] != row,
                    'conflicted': any(c['recipe'] == ident for c in conflicts)})
        return {'available': True, 'npcs': routes, 'recipes': recipes, 'configHash': fingerprint(config), 'conflicts': conflicts,
                'nextId': max([99999] + [int(i) for i in effective]) + 1,
                'note': 'Native NPC menus and their access requirements are retained. Shared windows and shared recipe definitions affect every listed NPC.'}

    def plan(self, body, remove=False):
        from metin2_studio.crafting_access import discover_native
        from metin2_studio.server import number
        live, config, effective, conflicts = self.view(True)
        if body.get('configHash') != fingerprint(config):
            raise ValueError('Saved native crafts changed. Refresh before saving.')
        ident = str(body.get('index', ''))
        new = bool(body.get('new'))
        if new:
            ident = str(max([99999] + [int(i) for i in effective]) + 1)
            row = empty_row()
        else:
            row = effective.get(ident)
            if row is None or body.get('hash') != fingerprint(row):
                raise ValueError('This native recipe changed. Reopen it before saving.')
            if any(c['recipe'] == ident for c in conflicts):
                raise ValueError('Review the server changes for this recipe before editing it.')
        after = copy.deepcopy(row)
        window = str(body.get('window', ''))
        routes = discover_native(self.studio)
        npc = str(body.get('fields', {}).get('npc', ''))
        selected = next((r for r in routes if r['id'] == npc and (not window or r['window'] == window)), None)
        if selected is None:
            raise ValueError('Choose an NPC with an existing native crafting menu.')
        window = selected['window']
        if remove:
            if window not in after['windows']:
                raise ValueError('This recipe is not in that NPC window.')
            del after['windows'][window]
            existing = config['recipes'].get(ident)
            if not after['windows'] and existing and existing['before']['proto'] is None:
                after['proto'] = None
        else:
            materials, rewards = body.get('materials', []), body.get('rewards', [])
            if not 1 <= len(materials) <= 10 or len(rewards) != 1:
                raise ValueError('Native crafting needs 1–10 ingredients and exactly one reward.')
            seen, pairs = set(), []
            for material in materials:
                item = str(material.get('item', ''))
                if item not in self.studio.items or item == '1' or item in seen:
                    raise ValueError('Choose distinct ingredient items from the installed catalog.')
                seen.add(item)
                pairs.extend([item, number(material.get('count', 1), 1, 2147483647, True)])
            reward = str(rewards[0].get('item', ''))
            if reward not in self.studio.items or reward == '1':
                raise ValueError('Choose a reward item from the installed catalog.')
            proto = copy.deepcopy(after['proto']) if after['proto'] else dict.fromkeys(COLS, 0)
            proto.update(vnum=int(ident), item_vnum=int(reward), count=int(number(rewards[0].get('count', 1), 1, 2147483647, True)),
                         price=int(number(body['fields'].get('gold', 0), 0, 2147483647, True)),
                         chance=int(number(body['fields'].get('percent', 100), 1, 100, True)), recipe=','.join(pairs))
            if len(proto['recipe']) > 255:
                raise ValueError('The ingredient list exceeds the native 255-character limit.')
            req = body.get('requirements', {})
            for key in ('req_progress', 'req_level', 'recipe_vnum'):
                proto[key] = int(number(req.get(key, proto.get(key, 0)), 0, 255 if key == 'req_level' else 2147483647, True))
            if new:
                proto['comment'] = None
            after['proto'] = proto
            old_window = str(body.get('originalWindow', body.get('window', '')))
            if not new and old_window != window:
                after['windows'].pop(old_window, None)
            if window not in after['windows']:
                after['windows'][window] = max([0] + [r['windows'].get(window, 0) for r in effective.values()]) + 1
        previous = config['recipes'].get(ident)
        record = edited_record(previous, row, after, live['rows'].get(ident, empty_row()))
        config['recipes'][ident] = record
        if not operations(record):
            del config['recipes'][ident]
        title = ('Remove native recipe from NPC: ' if remove else 'Create native craft: ' if new else 'Edit native craft: ') + self.studio.items.get(str((after['proto'] or {}).get('item_vnum')), {}).get('name', ident)
        plan = self.save_plan(config, title)
        plan['summary'] = self.describe_changes(row, after)
        if remove:
            plan['confirmLabel'] = 'Remove from NPC'
        return plan

    def describe_changes(self, before, after):
        labels = {'item_vnum': 'Reward item', 'count': 'Reward quantity', 'price': 'Yang cost', 'chance': 'Success chance %',
                  'recipe': 'Ingredients', 'req_progress': 'Required learning progress', 'req_level': 'Minimum level', 'recipe_vnum': 'Learning progress key'}
        def display(key, value):
            if value is None:
                return 'Not present'
            if key == 'item_vnum':
                return self.studio.items.get(str(value), {}).get('name', 'Item') + ' · #' + str(value)
            if key == 'recipe':
                pieces = value.split(',')
                return ', '.join(self.studio.items.get(pieces[i], {}).get('name', '#' + pieces[i]) + ' × ' + pieces[i + 1] for i in range(0, len(pieces), 2))
            return str(value)
        result = []
        for key, label in labels.items():
            old, new = (before['proto'] or {}).get(key), (after['proto'] or {}).get(key)
            if old != new:
                result.append({'field': label, 'before': display(key, old), 'after': display(key, new)})
        if before['windows'] != after['windows']:
            result.append({'field': 'NPC windows', 'before': ', '.join(before['windows']) or 'None', 'after': ', '.join(after['windows']) or 'None'})
        return result

    def save_plan(self, config, title, metadata=None):
        validate_document(config)
        raw = (json.dumps(config, indent=2, ensure_ascii=False) + '\n').encode() if config['recipes'] or config.get('accepted') else None
        return self.studio.plan(title, {self.path: raw},
            'Saves a Studio crafting configuration and backup. Apply checks only customised database fields, applies them in a guarded transaction while the game is stopped, then restarts. Existing NPC menus and player progress are retained. Shared recipes affect all listed windows.', metadata=metadata)

    def resolve(self, body):
        live, config, _, conflicts = self.view(True)
        signature = fingerprint({'live': live, 'config': config})
        if signature != body.get('signature'):
            raise ValueError('Server crafting changed during review. Refresh the conflict list.')
        choices = body.get('choices', {})
        by_id = {}
        for conflict in conflicts:
            key = conflict['recipe'] + ':' + conflict['field']
            if conflict.get('reason') or choices.get(key) not in ('studio', 'server'):
                raise ValueError('Choose a version for each conflicting field. Missing recipe definitions or new external links need manual recovery first.')
            by_id.setdefault(conflict['recipe'], []).append(conflict)
        for ident, group in by_id.items():
            record = config['recipes'].get(ident)
            if record is None:
                # Reverting a previous customisation can itself meet an update.
                record = copy.deepcopy(self.applied()['recipes'][ident])
                record['after'] = copy.deepcopy(record['before'])
                record['before'] = copy.deepcopy(live['rows'].get(ident, empty_row()))
                config['recipes'][ident] = record
            accepted = config.setdefault('accepted', {}).setdefault(ident, {})
            accepted['revision'] = secrets.token_hex(12)
            for conflict in group:
                key, observed = conflict['field'], conflict['server']
                accepted[key] = observed
                set_value(record['before'], key, observed)
                set_value(record['after'], key, observed if choices[ident + ':' + key] == 'server' else conflict['studio'])
        return self.save_plan(config, 'Resolve customised native crafting changes', metadata={'historyCategory': 'reconciliation'})

    def review(self):
        live, config, _, conflicts = self.view(True)
        return {'conflicts': conflicts, 'signature': fingerprint({'live': live, 'config': config})}

    def pending(self):
        config, applied = self.config(), self.applied()
        return fingerprint(config) != fingerprint(applied)

    def preflight(self):
        if not self.config()['recipes'] and not self.applied()['recipes']:
            return
        _, _, _, conflicts = self.view(True)
        if conflicts:
            raise ValueError('A game update or external edit affected customised native crafts. Review native crafting conflicts before Apply.')

    def apply(self):
        config, previous = self.config(), self.applied()
        if not config['recipes'] and not previous['recipes']:
            return 0
        live = self.live(True)
        targets, conflicts = transition(previous, config, live['rows'])
        if conflicts:
            raise ValueError('Native crafting changed after review. No native crafting rows were written; reopen the conflict review.')
        if targets:
            validate_document({'version': 1, 'recipes': {ident: {'before': row, 'after': row} for ident, row in targets.items()}, 'accepted': {}})
            self.execute(transaction_sql(live['rows'], targets))
            self.cached = None
            verified = self.live(True)['rows']
            if any(verified.get(ident, empty_row()) != row for ident, row in targets.items()):
                raise ValueError('Native crafting database verification failed. Game remains stopped; inspect the saved configuration and backups.')
        # Track DB deployment separately from game restart: if restart fails,
        # another Apply must compare against what actually reached the DB.
        self.studio.workspace.set_preference('nativeCraftingApplied', config)
        return len(targets)

    def execute(self, sql):
        try:
            run = subprocess.run(['docker', 'compose', 'exec', '-T', 'mariadb', 'sh', '-c',
                                  'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb -uroot --default-character-set=utf8mb4 -N -B --raw'],
                                 input=sql, cwd=self.studio.compose, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError('Native crafting transaction could not be confirmed. The game remains stopped. Retry Apply to inspect the actual database state.') from None
        if run.returncode:
            raise ValueError('Native crafting transaction was rejected. No partial transaction is kept. The game remains stopped; refresh crafting and review conflicts.')


def literal(value):
    if value is None:
        return 'NULL'
    if isinstance(value, int):
        return str(value)
    return "CONVERT(0x" + str(value).encode('utf-8').hex() + " USING utf8mb4)" if value else "''"


def transaction_sql(live, targets):
    sql = ["USE world;", "SET SESSION innodb_lock_wait_timeout=10;", "CREATE TEMPORARY TABLE studio_crafting_guard (ok INT NOT NULL CHECK(ok=1)) ENGINE=InnoDB;",
           "INSERT INTO studio_crafting_guard VALUES (IF(GET_LOCK('server_studio_crafting',10)=1,1,0));", 'START TRANSACTION;']
    # Lock and guard every affected row before writing any recipe. Range locks
    # protect newly allocated IDs and newly added membership rows too.
    for ident in sorted(targets, key=int):
        ident = str(int(ident))
        before = live.get(ident, empty_row())
        sql += [f'SELECT vnum FROM world.crafting_proto WHERE vnum={ident} FOR UPDATE;',
                f'SELECT window_id FROM world.crafting_window WHERE recipe_id={ident} FOR UPDATE;']
        proto = before['proto']
        condition = f'(SELECT COUNT(*) FROM world.crafting_proto WHERE vnum={ident})=0' if proto is None else \
            f'EXISTS(SELECT 1 FROM world.crafting_proto WHERE vnum={ident} AND ' + ' AND '.join('`' + col + '` <=> ' + literal(proto[col]) for col in COLS) + ')'
        condition += f" AND (SELECT COUNT(*) FROM world.crafting_window WHERE recipe_id={ident})={len(before['windows'])}"
        for window, order in before['windows'].items():
            condition += f' AND EXISTS(SELECT 1 FROM world.crafting_window WHERE recipe_id={ident} AND window_id={int(window)} AND sort_order={int(order)})'
        sql.append('INSERT INTO studio_crafting_guard VALUES (IF(' + condition + ',1,0));')
    for ident, after in targets.items():
        ident = str(int(ident))
        before = live.get(ident, empty_row())
        if after['proto'] != before['proto']:
            if after['proto'] is None:
                sql.append(f'DELETE FROM world.crafting_proto WHERE vnum={ident};')
            elif before['proto'] is None:
                sql.append('INSERT INTO world.crafting_proto (' + ','.join('`' + c + '`' for c in COLS) + ') VALUES (' + ','.join(literal(after['proto'][c]) for c in COLS) + ');')
            else:
                fields = [c for c in COLS if after['proto'][c] != before['proto'][c]]
                sql.append('UPDATE world.crafting_proto SET ' + ','.join('`' + c + '`=' + literal(after['proto'][c]) for c in fields) + f' WHERE vnum={ident};')
        for window in before['windows'].keys() | after['windows'].keys():
            if before['windows'].get(window) == after['windows'].get(window):
                continue
            if window not in after['windows']:
                sql.append(f'DELETE FROM world.crafting_window WHERE recipe_id={ident} AND window_id={int(window)};')
            else:
                sql.append(f'INSERT INTO world.crafting_window (window_id,recipe_id,sort_order) VALUES ({int(window)},{ident},{int(after["windows"][window])}) ON DUPLICATE KEY UPDATE sort_order=VALUES(sort_order);')
    sql += ['COMMIT;', "SELECT RELEASE_LOCK('server_studio_crafting');"]
    return '\n'.join(sql)
