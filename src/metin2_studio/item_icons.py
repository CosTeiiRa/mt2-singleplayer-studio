"""Resolve existing local PNGs using the client's explicit item icon aliases.

Only the package's shipped pack reader is used, read-only. Its gamedata pack
contains item_list.txt; no client pack or game configuration is ever rewritten.
The small derived mapping is cached in Studio's own state directory.
"""
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re


def item_list_aliases(raw):
    result = {}
    for line in raw.decode('utf-8-sig', errors='replace').splitlines():
        match = re.match(r'^\s*(\d{1,10})\s+\S+\s+(.+?\.(?:tga|dds|png))(?=\s|$)', line, re.I)
        if not match:
            continue
        ident, path = match.group(1), match.group(2).replace('\\', '/').lower()
        if '..' in PurePosixPath(path).parts:
            continue
        if '/icon/item/' not in '/' + path:
            continue
        name = PurePosixPath(path).name
        if re.fullmatch(r'[a-z0-9_-]+\.(?:tga|dds|png)', name):
            result[ident] = PurePosixPath(name).stem + '.png'
    return result


def shared_name_aliases(rows, aliases, filenames):
    """Match exact original proto names only when they identify one known icon.

    The client uses original-name matching for items absent from item_list.txt.
    Ambiguous names, empty names and explicit missing assets are left unresolved.
    """
    images = {}
    for row in rows:
        name = row.get('name', b'').split(b'\0', 1)[0]
        if not name or name.lower() in (b'noname', b'none', b'unnamed'):
            continue
        ident = str(row['vnum'])
        image = aliases.get(ident, f'{int(ident):05d}.png')
        if image.lower() in filenames:
            images.setdefault(name, set()).add(filenames[image.lower()])
    result = {}
    for row in rows:
        ident = str(row['vnum'])
        if ident in aliases or f'{int(ident):05d}.png' in filenames:
            continue
        name = row.get('name', b'').split(b'\0', 1)[0]
        candidates = images.get(name, set())
        if len(candidates) == 1:
            result[ident] = next(iter(candidates))
    return result


def client_icon_aliases(root, state):
    root, state = Path(root), Path(state)
    reader = root / 'files/client_protos.py'
    pack = root.parent / 'Klient/pack'
    folder = root / 'files/static/icons'
    inputs = (reader, pack / 'gamedata.index', pack / 'gamedata.data', folder)
    try:
        fingerprint = [[str(p.resolve()), p.stat().st_size, p.stat().st_mtime_ns] for p in inputs]
        cache = state / 'item-icon-aliases.json'
        try:
            previous = json.loads(cache.read_text('utf-8'))
        except (OSError, ValueError):
            previous = {}
        files = {p.name.lower(): p.name for p in folder.glob('*.png') if p.is_file()}
        if previous.get('version') == 2 and previous.get('fingerprint') == fingerprint and isinstance(previous.get('aliases'), dict):
            aliases = previous['aliases']
        else:
            spec = importlib.util.spec_from_file_location('studio_item_icon_pack_reader', reader)
            module = importlib.util.module_from_spec(spec)
            exec(compile(reader.read_bytes(), str(reader), 'exec'), module.__dict__)
            _, entries = module.read_pack(inputs[1].read_bytes(), inputs[2].read_bytes())
            entry = next((e for e in entries if e.key() == 'gamedata/item_list.txt'), None)
            aliases = item_list_aliases(module.entry_data(entry)) if entry else {}
            proto = next((e for e in entries if e.key() == 'gamedata/item_proto'), None)
            if proto is not None and all(hasattr(module, name) for name in ('read_item_proto', 'decode_rows', 'ITEM_STRUCT', 'ITEM_NAMES')):
                try:
                    rows = module.decode_rows(module.read_item_proto(module.entry_data(proto)), module.ITEM_STRUCT, module.ITEM_NAMES)
                    aliases.update(shared_name_aliases(rows, aliases, files))
                except Exception:
                    # Optional proto formats vary; retain the explicit item_list aliases.
                    pass
            state.mkdir(parents=True, exist_ok=True)
            temporary = cache.with_suffix('.tmp')
            temporary.write_text(json.dumps({'version': 2, 'fingerprint': fingerprint, 'aliases': aliases}), encoding='utf-8')
            temporary.replace(cache)
        # Use the actual filename casing on both Windows and case-sensitive hosts.
        return {str(ident): files.get(name.lower()) for ident, name in aliases.items()
                if re.fullmatch(r'\d{1,10}', str(ident)) and isinstance(name, str)
                and Path(name).name == name and re.fullmatch(r'[a-zA-Z0-9_-]+\.png', name)}
    except Exception:
        # Older packages may not ship the reader or use a supported pack format.
        # Keep their original web icon map and exact-ID PNG fallback functional.
        return {}


def icon_path(root, mapping, ident):
    ident = str(ident)
    if not re.fullmatch(r'\d{1,10}', str(ident)):
        return None
    if ident in mapping and mapping[ident] is None:
        return None  # The client's explicit asset is missing; an old alias must not substitute another item.
    folder = (Path(root) / 'files/static/icons').resolve()
    for name in (mapping.get(ident), f'{int(ident):05d}.png'):
        if not isinstance(name, str) or Path(name).name != name or not name.lower().endswith('.png'):
            continue
        path = folder / name
        if path.is_file() and path.resolve().is_relative_to(folder):
            return path
    return None
