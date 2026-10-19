"""Read configured spawn zones from the user's installation, without executing it."""
from __future__ import annotations

import ast
import json
import math
import re
from pathlib import Path


def _text(path):
    return path.read_bytes().decode('utf-8-sig', errors='replace')


def _literal_maps(panel):
    result = {}
    try:
        tree = ast.parse(_text(panel / 'app.py'))
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


def _groups(path):
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
            groups[current] = leader or (members[0] if members else None)
    return groups


class WorldData:
    def __init__(self, server_root):
        self.root = Path(server_root).resolve()
        self.locale = self.root / 'linux-port' / 'docker' / 'game' / 'share' / 'locale' / 'poland'
        self.panel = self.root / 'linux-port' / 'docker' / 'seban-panel'
        self.maps_root = self.locale / 'map'
        self.metadata = _literal_maps(self.panel)
        self.groups = _groups(self.locale / 'group.txt')
        self.names = {}
        names_file = self.panel / 'static' / 'mob_names_en.json'
        if names_file.is_file():
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
        for filename, category in [('boss.txt', 'boss'), ('stone.txt', 'metin')]:
            path = folder / filename
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
                    if spawn_type not in ('m', 's', 'g', 'ga', 'gd'):
                        omitted.append('%s:%d: unsupported spawn type %s' % (filename, number, spawn_type))
                        continue
                    mob = self.groups.get(vnum) if spawn_type.startswith('g') else vnum
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
                except (ValueError, IndexError, OverflowError):
                    omitted.append('%s:%d: malformed configured row' % (filename, number))
        images = self.metadata.get('MAP_IMAGE_FILES', {})
        image = images.get(ident)
        image_path = self.panel / 'static' / 'maps' / str(image) if image else None
        has_image = bool(image_path and image_path.is_file() and image_path.resolve().is_relative_to((self.panel / 'static' / 'maps').resolve()))
        result = {'id': ident, 'name': self.metadata.get('MAP_NAMES', {}).get(ident, directory.replace('metin2_map_', '').replace('_', ' ').title()),
                  'directory': directory, 'width': width or 1024, 'height': height or 1024,
                  'base_x': bx, 'base_y': by, 'regions': regions,
                  'image_url': '/api/map-image?map=%s' % ident if has_image else None,
                  'source': {'path': folder.relative_to(self.root).as_posix(), 'kind': 'installed-configuration'},
                  'coverage': {'live': False, 'intervals': 'base configured intervals; server overrides are not applied',
                               'scope': 'boss.txt and stone.txt; quest-spawned and dynamic dungeon encounters are excluded',
                               'omitted': omitted, 'bounds_verified': bool(width and height)}}
        self._cache[ident] = result
        return result

    def image_path(self, ident):
        m = self.map(ident)
        if not m['image_url']:
            return None
        image = self.metadata['MAP_IMAGE_FILES'].get(int(ident))
        return self.panel / 'static' / 'maps' / image

    def catalog(self):
        items = []
        for ident in self.directories:
            m = self.map(ident)
            if m['regions']:
                items.append({k: m[k] for k in ('id', 'name', 'width', 'height')})
                items[-1].update(boss_count=sum(r['type'] == 'boss' for r in m['regions']),
                                 stone_count=sum(r['type'] == 'metin' for r in m['regions']), region='Configured world')
        return {'maps': items, 'source': {'kind': 'installed-configuration', 'path': str(self.maps_root)},
                'coverage': {'live': False, 'scope': 'Configured boss and Metin zones; no live presence or precise timers'}}

    def runtime_data(self):
        return {self.directories[i]: self.map(i) for i in self.directories if self.map(i)['regions']}
