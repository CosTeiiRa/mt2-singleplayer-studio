"""Read installed client names and icon pixels into a private, derived cache."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import zlib

from .installation import atomic_json


def fingerprint(paths):
    result = []
    for path in paths:
        path = Path(path)
        try:
            stat = path.stat()
            result.append([str(path.resolve()), stat.st_size, stat.st_mtime_ns])
        except OSError:
            result.append([str(path.resolve()), None, None])
    return result


def asset_key(value):
    value = value.replace('\\', '/').lower().strip()
    if value.startswith('d:/ymir work/'):
        value = value[len('d:/ymir work/'):]
    if ':' in value or '..' in value.split('/'):
        return ''
    return value.lstrip('/')


def text_table(raw, description=False):
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1250', errors='replace')
    result = {}
    for line in text.splitlines():
        cells = line.split('\t')
        if len(cells) >= 2 and re.fullmatch(r'[1-9][0-9]{0,9}', cells[0]):
            value = (cells[-1] if description and len(cells) > 2 else cells[1]).strip().strip('"')
            if value:
                result[cells[0]] = value[:12000 if description else 256]
    return result


def png_pixels(raw):
    """Decode the installed client's true-colour/RLE TGA icons with no dependency."""
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        return raw
    if len(raw) < 18:
        raise ValueError('Incomplete icon')
    ident, cmap, kind = raw[:3]
    width, height, bits, flags = struct.unpack_from('<HHBB', raw, 12)
    if cmap or kind not in (2, 10) or bits not in (24, 32) or not (0 < width <= 1024 and 0 < height <= 1024):
        raise ValueError('Unsupported client icon format')
    stride, offset, pixels = bits // 8, 18 + ident, bytearray()
    count = width * height
    while len(pixels) < count * stride:
        if kind == 2:
            pixels.extend(raw[offset:offset + count * stride])
            break
        if offset >= len(raw):
            raise ValueError('Incomplete RLE icon')
        header = raw[offset]; offset += 1
        length = (header & 127) + 1
        size = stride if header & 128 else length * stride
        value = raw[offset:offset + size]; offset += size
        if len(value) != size:
            raise ValueError('Incomplete RLE pixels')
        pixels.extend(value * length if header & 128 else value)
    if len(pixels) != count * stride:
        raise ValueError('Invalid icon pixel count')
    scan = bytearray()
    for y in range(height):
        scan.append(0)
        source_y = y if flags & 32 else height - y - 1
        for x in range(width):
            source_x = width - x - 1 if flags & 16 else x
            start = (source_y * width + source_x) * stride
            blue, green, red = pixels[start:start + 3]
            scan.extend((red, green, blue, pixels[start + 3] if stride == 4 else 255))
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(scan)) + chunk(b'IEND', b'')


class ClientCatalogue:
    def __init__(self, root, state):
        self.root, self.state = Path(root), Path(state)
        self.folder = self.state / 'catalogue'
        self.images = self.folder / 'icons'
        self.cache = self.folder / 'client.json'
        pack = self.root.parent / 'Klient/pack'
        self.reader = self.root / 'files/client_protos.py'
        self.paths = [self.reader] + [pack / (name + suffix) for name in ('gamedata', 'locale', 'icon') for suffix in ('.index', '.data')]

    def load(self):
        before = fingerprint(self.paths)
        try:
            cached = json.loads(self.cache.read_text('utf-8'))
            if (not isinstance(cached, dict) or cached.get('schema') != 1 or cached.get('root') != str(self.root.resolve())
                    or any(not isinstance(cached.get(key), dict) for key in ('names','descriptions','mobs','proto','icons'))
                    or any(value is not None and (not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{64}\.png',value)) for value in cached['icons'].values())
                    or any(not isinstance(value,str) for key in ('names','descriptions','mobs') for value in cached[key].values())
                    or any(not isinstance(value,dict) or not isinstance(value.get('name'),str) for value in cached['proto'].values())):
                cached = None
        except (OSError, ValueError):
            cached = None
        if cached and cached.get('fingerprint') == before and all(self.icon_path(name) for name in set(cached.get('icons', {}).values()) if name):
            return cached, 'current'
        try:
            if any(value[1] is None for value in before):
                raise ValueError('Client packs are unavailable')
            spec = importlib.util.spec_from_file_location('studio_catalogue_reader', self.reader)
            reader = importlib.util.module_from_spec(spec)
            exec(compile(self.reader.read_bytes(), str(self.reader), 'exec'), reader.__dict__)
            packs = {}
            for index in range(1, len(self.paths), 2):
                _, entries = reader.read_pack(self.paths[index].read_bytes(), self.paths[index + 1].read_bytes())
                packs[self.paths[index].stem] = {asset_key(entry.key()): entry for entry in entries}
            game, locale, assets = packs['gamedata'], packs['locale'], packs['icon']
            def entry(entries, name):
                value = entries.get(name)
                return reader.entry_data(value) if value is not None else b''
            names = text_table(entry(locale, 'locale/en/item_names.txt'))
            descriptions = text_table(entry(locale, 'locale/en/itemdesc.txt'), True)
            mobs = text_table(entry(locale, 'locale/en/mob_names.txt'))
            rows = reader.decode_rows(reader.read_item_proto(entry(game, 'gamedata/item_proto')), reader.ITEM_STRUCT, reader.ITEM_NAMES)
            aliases = {}
            for line in entry(game, 'gamedata/item_list.txt').decode('utf-8-sig', errors='replace').splitlines():
                match = re.match(r'^\s*(\d{1,10})\s+\S+\s+(.+?\.(?:tga|dds|png))(?=\s|$)', line, re.I)
                if match:
                    aliases[match[1]] = asset_key(match[2])
            self.images.mkdir(parents=True, exist_ok=True)
            converted = {}
            def image(path):
                if path not in converted:
                    try:
                        raw = png_pixels(entry(assets, path))
                        name = hashlib.sha256(raw).hexdigest() + '.png'
                        target = self.images / name
                        if not target.is_file():
                            temporary = target.with_suffix('.tmp')
                            temporary.write_bytes(raw); temporary.replace(target)
                        converted[path] = name
                    except (ValueError, OSError, struct.error):
                        converted[path] = None
                return converted[path]
            icons, original_names, proto = {}, {}, {}
            for row in rows:
                ident = str(row['vnum'])
                original = row['name'].split(b'\0', 1)[0]
                original_names[ident] = original
                proto[ident] = {'range': int(row.get('vnum_range', 0)),
                                'name': row['locale_name'].split(b'\0', 1)[0].decode('utf-8', errors='replace')}
                path = aliases.get(ident, 'icon/item/' + f'{int(ident):05d}.tga')
                if ident in aliases or path in assets:
                    icons[ident] = image(path)
            for ident, path in aliases.items():
                if ident not in icons:
                    icons[ident] = image(path)
            by_name = {}
            for ident, original in original_names.items():
                if original and original.lower() not in (b'noname', b'none', b'unnamed') and icons.get(ident):
                    by_name.setdefault(original, set()).add(icons[ident])
            for ident, original in original_names.items():
                candidates = by_name.get(original, set())
                if ident not in icons and len(candidates) == 1:
                    icons[ident] = next(iter(candidates))
            if before != fingerprint(self.paths):
                raise ValueError('Client files changed while reading')
            result = {'schema': 1, 'root': str(self.root.resolve()), 'fingerprint': before,
                      'names': names, 'descriptions': descriptions, 'mobs': mobs, 'proto': proto, 'icons': icons}
            atomic_json(self.cache, result)
            return result, 'current'
        except Exception:
            return cached or {}, 'cached' if cached else 'unavailable'

    def icon_path(self, name):
        if not isinstance(name, str) or not re.fullmatch(r'[a-f0-9]{64}\.png', name):
            return None
        path = self.images / name
        return path if path.is_file() and path.resolve().is_relative_to(self.images.resolve()) else None
