"""Read configured spawn zones from the user's installation, without executing it."""
from __future__ import annotations

import ast
import json
import hashlib
from functools import lru_cache
import math
import re
from pathlib import Path

from metin2_studio.game_maps import references, navigation_png, directory_label


def _text(path):
    return path.read_bytes().decode('utf-8-sig', errors='replace')


@lru_cache(maxsize=16)
def _panel_metadata(filename, modified, size):
    result = {}
    try:
        tree = ast.parse(_text(Path(filename)))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in ('MAP_NAMES', 'MAP_IMAGE_FILES'):
                        try:
                            result[target.id] = ast.literal_eval(node.value)
                        except (ValueError, TypeError):
                            pass
    except (OSError, SyntaxError):
        pass
    return result


def _literal_maps(panel):
    path = panel / 'app.py'
    try:
        stat = path.stat()
        return _panel_metadata(str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return {}


@lru_cache(maxsize=256)
def _attribute_digest(filename, modified, size):
    return hashlib.sha256(Path(filename).read_bytes()).digest()


def _same_attributes(path):
    try:
        stat = path.stat()
        return _attribute_digest(str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def _groups(path, all_members=False):
    groups, current, leader, members = {}, None, None, []
    if not path.is_file():
        return groups
    for line in _text(path).splitlines():
        parts = line.split('//', 1)[0].split()
        if not parts:
            continue
        if parts[0].lower() == 'group':
            current, leader, members = None, None, []
        elif parts[0].lower() == 'vnum' and len(parts) > 1 and parts[1].isdigit():
            current = int(parts[1])
        elif parts[0].lower() == 'leader' and parts[-1].isdigit():
            leader = int(parts[-1])
        elif parts[0].isdigit() and len(parts) >= 3 and parts[-1].isdigit():
            members.append(int(parts[-1]))
        elif parts[0] == '}' and current is not None:
            groups[current] = list(dict.fromkeys(([leader] if leader else []) + members)) if all_members else leader or (members[0] if members else None)
    return groups


def _mining_ids(locale):
    """Resolve mining targets from installed quest handlers, without running Lua."""
    path = locale / 'quest' / 'quest' / 'systems' / 'mining.quest'
    if not path.is_file():
        return set()
    source = re.sub(r'--\[\[.*?\]\]|--[^\n]*', '', _text(path), flags=re.S)
    result = set()
    for triggers, body in re.findall(r'\bwhen\s+(.*?)\bbegin\b(.*?)(?=\bwhen\b|\Z)', source, re.S):
        if re.search(r'\bpc\s*\.\s*mining\s*\(', body):
            result.update(int(ident) for ident in re.findall(r'\b(\d+)\s*\.\s*click\b', triggers))
    return result


class WorldData:
    def __init__(self, server_root, mobs=None, include_monsters=False, map_names=None, map_images=None, image_resolver=None):
        self.root = Path(server_root).resolve()
        self.locale = self.root / 'linux-port' / 'docker' / 'game' / 'share' / 'locale' / 'poland'
        self.panel = self.root / 'linux-port' / 'docker' / 'seban-panel'
        self.maps_root = self.locale / 'map'
        self.metadata = _literal_maps(self.panel)
        self.english, self.navigation = references(self.root) if include_monsters else ({}, {})
        self.client_names, self.client_images = map_names or {}, map_images or {}
        self.image_resolver = image_resolver
        self._images = {}
        self.groups = _groups(self.locale / 'group.txt')
        self.group_members = _groups(self.locale / 'group.txt', all_members=True)
        self.random_groups = {}
        group_group = self.locale / 'group_group.txt'
        if group_group.is_file():
            current = None
            for line in _text(group_group).splitlines():
                parts = line.split('//', 1)[0].split()
                if parts and parts[0].lower() == 'group':
                    current = None
                elif len(parts) >= 2 and parts[0].lower() == 'vnum' and parts[1].isdigit():
                    current = int(parts[1])
                    self.random_groups[current] = []
                elif current is not None and len(parts) >= 3 and all(p.isdigit() for p in parts[:3]) and int(parts[2]) > 0:
                    self.random_groups[current].append(int(parts[1]))
        self.mobs = mobs or {}
        self.include_monsters = include_monsters
        self.mining_ids = _mining_ids(self.locale) if include_monsters else set()
        self.names = {}
        names_file = self.panel / 'static' / 'mob_names_en.json'
        if mobs is not None:
            self.names = {str(ident): row['name'] for ident, row in mobs.items()}
        elif names_file.is_file():
            self.names = json.loads(_text(names_file))
        self.directories = {}
        index = self.maps_root / 'index'
        if index.is_file():
            for line in _text(index).splitlines():
                parts = line.split('//', 1)[0].split()
                if len(parts) >= 2 and parts[0].isdigit() and re.fullmatch(r'[\w-]+', parts[1]):
                    self.directories[int(parts[0])] = parts[1]
        self._cache = {}

    def map(self, ident):
        ident = int(ident)
        if ident in self._cache:
            return self._cache[ident]
        if ident not in self.directories:
            raise ValueError('This map is not present in the selected installation.')
        directory = self.directories[ident]
        folder = self.maps_root / directory
        width, height, bx, by = 0, 0, 0, 0
        setting = folder / 'Setting.txt'
        if setting.is_file():
            for line in _text(setting).splitlines():
                p = line.split()
                if len(p) >= 3 and p[0] == 'MapSize':
                    width, height = int(p[1]) * 256, int(p[2]) * 256
                elif len(p) >= 3 and p[0] == 'BasePosition':
                    bx, by = int(p[1]), int(p[2])
        regions, omitted = [], []
        sources = [(folder / 'boss.txt', 'boss'), (folder / 'stone.txt', 'metin')]
        if self.include_monsters:
            sources += [(folder / 'regen.txt', 'monster'), (folder / 'npc.txt', 'npc'),
                        (self.root / 'linux-port' / 'docker' / 'game' / 'ore_veins' / (directory + '.txt'), 'ore')]
        seen = set()
        for path, category in sources:
            filename = path.name
            if not path.is_file():
                continue
            for number, line in enumerate(_text(path).splitlines(), 1):
                p = line.split('//', 1)[0].split()
                if not p or p[0].startswith('#'):
                    continue
                try:
                    if len(p) < 11:
                        raise ValueError()
                    spawn_type, vnum = p[0].lower(), int(p[10])
                    if spawn_type not in ('m', 's', 'g', 'ga', 'gd') and not (self.include_monsters and spawn_type == 'r'):
                        omitted.append('%s:%d: unsupported spawn type %s' % (filename, number, spawn_type))
                        continue
                    mob = self.groups.get(vnum) if spawn_type.startswith('g') else vnum
                    random_members = []
                    if spawn_type == 'r':
                        candidates = self.random_groups.get(vnum, [])
                        if not candidates or any(not self.group_members.get(group) for group in candidates):
                            omitted.append('%s:%d: unresolved random group %s' % (filename, number, vnum))
                            continue
                        random_members = list(dict.fromkeys(member for group in candidates for member in self.group_members[group]))
                        mob = random_members[0]
                    if mob is None:
                        omitted.append('%s:%d: unresolved group %s' % (filename, number, vnum))
                        continue
                    x, y, rx, ry = [float(p[i]) for i in (1, 2, 3, 4)]
                    if not all(math.isfinite(v) and v >= 0 for v in (x, y, rx, ry)):
                        raise ValueError()
                    name = self.names.get(str(mob), 'Mob %s' % mob)
                    if isinstance(name, list):
                        name = name[1] if len(name) > 1 else name[0]
                    if isinstance(name, dict):
                        name = name.get('name', 'Mob %s' % mob)
                    interval_valid = bool(re.fullmatch(r'\d+[smh](?:-\d+[smh])?', p[7]))
                    regions.append({'id': '%s-%s-%s' % (ident, filename, number), 'name': name,
                                    'type': category, 'x': x, 'y': y, 'width': rx * 2, 'height': ry * 2,
                                    'respawn': p[7] if interval_valid else 'Unverified: ' + p[7], 'raw_interval': p[7], 'interval_valid': interval_valid,
                                    'count': int(p[9]), 'group_id': vnum if spawn_type.startswith('g') else None,
                                    'mob_id': mob, 'source': path.relative_to(self.root).as_posix(), 'line': number})
                    if self.include_monsters:
                        base = regions.pop()
                        members = random_members or (self.group_members.get(vnum, []) if spawn_type.startswith('g') else [mob])
                        for member in members:
                            metadata = self.mobs.get(str(member), {})
                            kind = 'ore' if member in self.mining_ids or category == 'ore' else metadata.get('category', category)
                            signature = (member, x, y, rx, ry, p[7], int(p[9]))
                            if category == 'ore' and signature in seen:
                                continue
                            seen.add(signature)
                            regions.append({**base, 'id': base['id'] + '-' + str(member), 'mob_id': member,
                                            'name': metadata.get('name', self.names.get(str(member), 'Mob %s' % member)),
                                            'level': metadata.get('level'), 'type': kind,
                                            'group_spawn': spawn_type.startswith('g') or spawn_type == 'r',
                                            'random_group': spawn_type == 'r'})
                except (ValueError, IndexError, OverflowError):
                    omitted.append('%s:%d: malformed configured row' % (filename, number))
        images = self.metadata.get('MAP_IMAGE_FILES', {})
        image = images.get(ident)
        image_path = self.panel / 'static' / 'maps' / str(image) if image else None
        if not (image_path and image_path.is_file() and image_path.resolve().is_relative_to((self.panel / 'static' / 'maps').resolve())):
            image_path = None
        source = 'game-dashboard' if image_path else None
        client = self.image_resolver(self.client_images.get(directory.lower())) if self.image_resolver else None
        if client and client.is_file():
            image_path, source = client, 'client-atlas'
        elif self.include_monsters and (not image_path or re.search(r'dungeon|tower|catacomb', directory, re.I)):
            # Some dungeon terrain textures are nearly black. Reuse the game's
            # walkability drawing instead; copies must have identical attributes.
            layout = self.navigation.get(ident)
            if not layout:
                signature = _same_attributes(folder / 'server_attr')
                if signature:
                    layout = next((value for other, value in self.navigation.items()
                                   if other in self.directories and _same_attributes(self.maps_root / self.directories[other] / 'server_attr') == signature), None)
            layout = navigation_png(layout)
            if layout:
                image_path, source = layout, 'game-navigation'
        self._images[ident] = image_path
        original = self.metadata.get('MAP_NAMES', {}).get(ident, directory_label(directory))
        translated = self.client_names.get(directory.lower()) or self.english.get(ident)
        label = translated or (directory_label(directory) if self.include_monsters and re.search(r'[ąćęłńóśźż]|^(?:Loch|Grota) ', original, re.I) else original)
        result = {'id': ident, 'name': label, 'original_name': original,
                  'name_source': 'client-en' if directory.lower() in self.client_names else 'game-en' if ident in self.english else 'directory' if label != original else 'configured',
                  'image_source': source,
                  'directory': directory, 'width': width or 1024, 'height': height or 1024,
                  'base_x': bx, 'base_y': by, 'regions': regions,
                  'image_url': '/api/map-image?map=%s' % ident if image_path else None,
                  'source': {'path': folder.relative_to(self.root).as_posix(), 'kind': 'installed-configuration'},
                  'coverage': {'live': False, 'intervals': 'base configured intervals; server overrides are not applied',
                               'scope': ('boss.txt, stone.txt, regen.txt, npc.txt and ore_veins build additions' if self.include_monsters else 'boss.txt and stone.txt') + '; quest-spawned and dynamic dungeon encounters are excluded',
                               'omitted': omitted, 'bounds_verified': bool(width and height)}}
        self._cache[ident] = result
        return result

    def image_path(self, ident):
        self.map(ident)
        value = self._images.get(int(ident))
        return value if isinstance(value, Path) else None

    def image_data(self, ident):
        self.map(ident)
        value = self._images.get(int(ident))
        if isinstance(value, bytes):
            return value, 'image/png'
        if not value or not value.is_file():
            return None, None
        return value.read_bytes(), {'.webp':'image/webp', '.jpg':'image/jpeg', '.jpeg':'image/jpeg'}.get(value.suffix.lower(), 'image/png')

    def catalog(self):
        items = []
        for ident in self.directories:
            m = self.map(ident)
            if m['regions']:
                items.append({k: m[k] for k in ('id', 'name', 'width', 'height')})
                items[-1].update(boss_count=sum(r['type'] == 'boss' for r in m['regions']),
                                 stone_count=sum(r['type'] == 'metin' for r in m['regions']), region='Configured world')
        return {'maps': items, 'source': {'kind': 'installed-configuration', 'path': str(self.maps_root)},
                'coverage': {'live': False, 'scope': ('Configured creatures and mining deposits' if self.include_monsters else 'Configured boss and Metin zones') + '; no live presence or precise timers'}}

    def runtime_data(self):
        if self.include_monsters:
            return WorldData(self.root, self.mobs).runtime_data()
        return {self.directories[i]: self.map(i) for i in self.directories if self.map(i)['regions']}
