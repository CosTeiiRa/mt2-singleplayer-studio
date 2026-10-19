# -*- coding: utf-8 -*-
"""Original Pocket Wiki navigation/search model; Python 2.7 compatible."""
try:
    text_type = unicode
    char_type = unichr
except NameError:
    text_type = str
    char_type = chr
try:
    import unicodedata as _normalizer
except ImportError:
    _normalizer = None
_fold_table = {}
for _letters, _plain in ((u'\u00e0\u00e1\u00e2\u00e3\u00e4\u00e5\u0105', 'a'),
                         (u'\u00e8\u00e9\u00ea\u00eb\u0119', 'e'), (u'\u00ec\u00ed\u00ee\u00ef\u0131', 'i'),
                         (u'\u00f2\u00f3\u00f4\u00f5\u00f6', 'o'), (u'\u00f9\u00fa\u00fb\u00fc', 'u'),
                         (u'\u00e7\u0107', 'c'), (u'\u015b\u015f', 's'), (u'\u017a\u017c', 'z'),
                         (u'\u0144\u00f1', 'n'), (u'\u011f', 'g'), (u'\u0142', 'l')):
    for _letter in _letters:
        _fold_table[ord(_letter)] = text_type(_plain)
_fold_table[0x307] = None


def text(value):
    if isinstance(value, text_type):
        return value
    if isinstance(value, bytes):
        if text_type is not str:
            return u''.join(char_type(number) for number in bytearray(value))
        try:
            return value.decode('utf-8')
        except (UnicodeError, LookupError):
            try:
                return value.decode('cp1252', 'replace')
            except LookupError:
                return u''.join(char_type(number) for number in bytearray(value))
    return text_type(value)


def fold(value):
    value = text(value).lower()
    if _normalizer:
        value = ''.join(char for char in _normalizer.normalize('NFKD', value) if not _normalizer.combining(char))
    return value.translate(_fold_table)


PROVENANCE = {'database-seed': 'Installed database seed', 'current-database': 'Database snapshot',
              'installed-configuration': 'Saved configuration'}


class Model(object):
    def __init__(self, data, state=None, resolver=None):
        if data.get('schema_version') != 1:
            raise ValueError('Unsupported Pocket Wiki index')
        self.data, self.resolver = data, resolver
        self.names, self.search_rows = {}, []
        self.state = state if isinstance(state, dict) else {}
        self.query, self.category = '', 'All'
        self.back, self.forward, self.current = [], [], None
        self.attempts = 1
        self.state['bookmarks'] = self._valid_pages(self.state.get('bookmarks', []))[:100]
        self.state['recent'] = self._valid_pages(self.state.get('recent', []))[:40]
        self.parents = {}
        for ident, record in data['upgrades'].items():
            self.parents.setdefault(record['to'], []).append(ident)
        for ident, record in data['items'].items():
            name = self.name(ident)
            aliases = record.get('aliases', '')
            self.search_rows.append(('item', ident, name, fold(text(name) + ' ' + text(record['name']) + ' ' + text(aliases) + ' ' + ident)))
        for ident, record in data['recipes'].items():
            title = self.recipe_name(ident)
            npc_names = ' '.join(text(data['npcs'].get(npc, {}).get('name', npc)) for npc in record['npcs'])
            self.search_rows.append(('recipe', ident, title, fold(text(title) + ' ' + npc_names + ' ' + ident)))
        for ident, record in data['upgrades'].items():
            title = text(self.name(ident)) + ' > ' + text(self.name(record['to']))
            self.search_rows.append(('upgrade', ident, title, fold(title + ' ' + ident)))
        for ident, record in data['npcs'].items():
            self.search_rows.append(('npc', ident, record['name'], fold(record['name'] + ' ' + ident)))
        for ident, record in data['origins'].items():
            self.search_rows.append(('origin', ident, record['name'], fold(record['name'] + ' ' + record['kind'])))
        self.search_rows.sort(key=lambda row: (fold(row[2]), row[0], row[1]))
        last = self.state.get('last')
        if self.valid(last):
            self.current = list(last)
        self.query = text(self.state.get('query', ''))[:120]
        if self.state.get('category') in ('All', 'Items', 'Crafts', 'Upgrades', 'NPCs', 'Bookmarks', 'History'):
            self.category = self.state['category']

    def valid(self, page):
        tables = {'item': 'items', 'recipe': 'recipes', 'upgrade': 'upgrades', 'npc': 'npcs', 'origin': 'origins'}
        return isinstance(page, (list, tuple)) and len(page) == 2 and page[0] in tables and page[1] in self.data[tables[page[0]]]

    def _valid_pages(self, pages):
        if not isinstance(pages, list):
            return []
        result = []
        for page in pages:
            if self.valid(page) and list(page) not in result:
                result.append(list(page))
        return result

    def name(self, ident):
        ident = str(ident)
        if ident not in self.names:
            value = None
            if self.resolver:
                try:
                    value = self.resolver(int(ident))
                except Exception:
                    pass
            self.names[ident] = value or self.data['items'].get(ident, {}).get('name', 'Item #' + ident)
        return self.names[ident]

    def recipe_name(self, ident):
        recipe = self.data['recipes'][ident]
        return ' + '.join(text(self.name(row['item'])) for row in recipe['outputs']) + ' [' + recipe['system'] + ']'

    def search(self, query=None, category=None, offset=0, limit=30):
        if query is not None:
            self.query = text(query)[:120]
        if category is not None:
            self.category = category
        words = fold(self.query).split()
        kind = {'Items': 'item', 'Crafts': 'recipe', 'Upgrades': 'upgrade', 'NPCs': 'npc'}.get(self.category)
        selected = self.state.get('bookmarks' if self.category == 'Bookmarks' else 'recent', [])
        rows = [row for row in self.search_rows if (not kind or row[0] == kind)
                and (self.category not in ('Bookmarks', 'History') or [row[0], row[1]] in selected)
                and (self.query == row[1] or all(word in row[3] for word in words))]
        if self.category == 'History':
            rows.sort(key=lambda row: selected.index([row[0], row[1]]))
        offset, limit = max(0, int(offset)), min(100, max(1, int(limit)))
        return rows[offset:offset + limit], len(rows)

    def navigate(self, kind, ident):
        page = [kind, str(ident)]
        if not self.valid(page):
            return False
        if self.current and self.current != page:
            self.back.append(self.current)
            self.back = self.back[-40:]
            self.forward = []
        self.current = page
        recent = [row for row in self.state['recent'] if row != page]
        self.state['recent'] = [page] + recent[:39]
        return True

    def travel(self, direction):
        source, target = (self.back, self.forward) if direction < 0 else (self.forward, self.back)
        if source:
            if self.current:
                target.append(self.current)
            self.current = source.pop()
            return True
        return False

    def bookmark(self):
        if self.current:
            pages = self.state['bookmarks']
            if self.current in pages:
                pages.remove(self.current)
            else:
                pages.insert(0, list(self.current))
                del pages[100:]

    def persist(self):
        self.state.update(last=self.current, query=self.query, category=self.category)
        return self.state

    def page(self, page=None, attempts=None):
        page = page or self.current
        if not self.valid(page):
            return 'Pocket Wiki', [{'text': 'Search an item, craft, upgrade or NPC to begin.'}]
        count = min(9999, max(1, int(attempts or self.attempts)))
        kind, ident = page
        rows = []

        def line(value, link=None):
            rows.append({'text': text(value), 'link': link})

        def item_line(row, prefix=''):
            line(prefix + text(self.name(row['item'])) + ' x' + str(row['count'] * count), ['item', row['item']])

        if kind == 'item':
            record = self.data['items'][ident]
            title = self.name(ident)
            line(record['category'] + ' | #' + ident)
            description = record.get('description', '')
            if isinstance(description, dict):
                line(description.get('text', ''))
                for fact in description.get('facts', []):
                    line(text(fact[0]) + ': ' + text(fact[1]))
                if description.get('source'):
                    line('Description: ' + str(description['source']))
                if description.get('note'):
                    line(description['note'])
            else:
                line(description)
            line('CRAFTED BY')
            for recipe in self.data['crafted'].get(ident, []):
                line(self.recipe_name(recipe), ['recipe', recipe])
            if ident in self.data['upgrades'] or ident in self.parents:
                line('UPGRADE CHAIN')
                visited, pending = set(), [ident]
                while pending and len(visited) < 64:
                    current = pending.pop(0)
                    if current in visited:
                        continue
                    visited.add(current)
                    upgrade = self.data['upgrades'].get(current)
                    if upgrade:
                        line(text(self.name(current)) + ' > ' + text(self.name(upgrade['to'])), ['upgrade', current])
                        pending.append(upgrade['to'])
                    pending.extend(self.parents.get(current, []))
            line('OBTAINED FROM | configured sources')
            for origin in self.data['obtained'].get(ident, []):
                source = self.data['origins'][origin]
                line(source['kind'] + ': ' + source['name'], ['origin', origin])
            line('USED FOR')
            for target_kind, target in self.data['uses'].get(ident, []):
                name = self.recipe_name(target) if target_kind == 'recipe' else text(self.name(target)) + ' upgrade'
                line(name, [target_kind, target])
            line('Missing references do not establish that an item has no other sources or uses.')
        elif kind in ('recipe', 'upgrade'):
            record = self.data['recipes' if kind == 'recipe' else 'upgrades'][ident]
            title = self.recipe_name(ident) if kind == 'recipe' else text(self.name(ident)) + ' upgrade'
            line(PROVENANCE.get(record['provenance'], record['provenance']))
            line('%d attempt(s) | %s Yang | %s%% base chance per attempt' % (count, record['cost'] * count, record['chance']))
            line('Success, failure protection and modifiers depend on game rules.')
            line('MATERIALS')
            if kind == 'upgrade':
                item_line({'item': ident, 'count': 1}, 'Equipment: ')
            for material in record['materials']:
                item_line(material)
            line('OUTPUT PER SUCCESSFUL ATTEMPT')
            outputs = record['outputs'] if kind == 'recipe' else [{'item': record['to'], 'count': 1}]
            for output in outputs:
                line(text(self.name(output['item'])) + ' x' + str(output['count']), ['item', output['item']])
            if kind == 'recipe':
                line('CRAFTING NPC')
                for npc in record['npcs']:
                    line(self.data['npcs'].get(npc, {}).get('name', 'NPC #' + npc), ['npc', npc])
                for requirement in record['requirements']:
                    line(requirement)
        elif kind == 'npc':
            title = self.data['npcs'][ident]['name']
            line('RECIPES | NPC entry conditions apply')
            for key, record in sorted(self.data['recipes'].items()):
                if ident in record['npcs']:
                    line(self.recipe_name(key), ['recipe', key])
        else:
            record = self.data['origins'][ident]
            title = record['name']
            line(record['kind'])
            line(PROVENANCE.get(record['provenance'], record['provenance']))
            line('Configured relationship; effective availability can depend on runtime rules.')
            for key, sources in sorted(self.data['obtained'].items()):
                if ident in sources:
                    line(self.name(key), ['item', key])
        return text(title), rows
