"""Read installed English map labels and navigation drawings as data only."""
import ast
import base64
from functools import lru_cache
from pathlib import Path
import re
import struct


def _value(node):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'P' and len(node.args) == 2:
        return ast.literal_eval(node.args[1])
    if isinstance(node, ast.Dict):
        return {_value(k): _value(v) for k, v in zip(node.keys, node.values)}
    return ast.literal_eval(node)


@lru_cache(maxsize=8)
def _read(sources):
    names, tiles = {}, {}
    for filename, modified, size in sources:
        try:
            tree = ast.parse(Path(filename).read_text('utf-8-sig'))
            for node in tree.body:
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in ('EVENT_MAPS', 'MAP_NAMES', 'PLAYERBOT_MAP_TILES'):
                        try:
                            value = _value(node.value)
                            if target.id == 'EVENT_MAPS':
                                names.update({int(row[0]): row[2] for row in value if len(row) >= 3 and isinstance(row[2], str) and row[2]})
                            elif target.id == 'MAP_NAMES':
                                names.update({int(k): v for k, v in value.items() if isinstance(v, str) and v})
                            else:
                                tiles.update({int(k): v for k, v in value.items() if isinstance(v, str) and len(v) < 8_000_000})
                        except (ValueError, TypeError, KeyError, IndexError):
                            continue
                    # Follow only literal tile-to-tile aliases; never execute source.
                    elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == 'PLAYERBOT_MAP_TILES':
                        value = node.value
                        if isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name) and value.value.id == 'PLAYERBOT_MAP_TILES':
                            try:
                                tiles[ast.literal_eval(target.slice)] = tiles[ast.literal_eval(value.slice)]
                            except (ValueError, TypeError, KeyError):
                                pass
        except (OSError, SyntaxError, UnicodeError):
            continue
    return names, tiles


def references(root):
    sources = []
    for name in ('files/admin_panel.py', 'files/editsql/modules.py'):
        path = Path(root) / name
        try:
            stat = path.stat()
            sources.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            pass
    return _read(tuple(sources))


def navigation_png(value):
    try:
        raw = base64.b64decode(value, validate=True)
        if len(raw) < 33 or not raw.startswith(b'\x89PNG\r\n\x1a\n') or raw[12:16] != b'IHDR':
            return None
        width, height = struct.unpack_from('>II', raw, 16)
        return raw if 0 < width <= 4096 and 0 < height <= 4096 else None
    except (ValueError, TypeError):
        return None


def directory_label(directory):
    value = re.sub(r'^metin2_map_', '', directory, flags=re.I).replace('_', ' ')
    value = re.sub(r'(?<=[a-z])(dungeon|tower|catacomb)', r' \1', value, flags=re.I)
    return re.sub(r'(?<=[a-z])(?=\d)', ' ', value, flags=re.I).title()


def client_map_names(locale, script):
    labels = {}
    for line in locale.decode('utf-8-sig', errors='replace').splitlines():
        cells = line.split('\t')
        if len(cells) >= 2 and cells[0].startswith('MAP_') and cells[1].strip():
            labels[cells[0]] = cells[1].strip().strip('"')[:256]
    block = re.search(r'MINIMAP_ZONE_NAME_DICT\s*=\s*\{(.*?)\n\}', script.decode('utf-8-sig', errors='replace'), re.S)
    if not block:
        return {}
    result = {}
    for directory, token in re.findall(r'["\']([\w/ -]+)["\']\s*:\s*(MAP_\w+)', block[1]):
        if token in labels:
            result[directory.lower().split('/')[-1]] = labels[token]
    return result
