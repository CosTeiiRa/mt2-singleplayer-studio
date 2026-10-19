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
        cells = line.split()
        if len(cells) < 3 or not re.fullmatch(r'\d{1,10}', cells[0]):
            continue
        path = cells[2].replace('\\', '/').lower()
        if '/icon/item/' not in '/' + path:
            continue
        name = PurePosixPath(path).name
        if re.fullmatch(r'[a-z0-9_-]+\.(?:tga|dds|png)', name):
            result[cells[0]] = PurePosixPath(name).stem + '.png'
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
        if previous.get('version') == 1 and previous.get('fingerprint') == fingerprint and isinstance(previous.get('aliases'), dict):
            aliases = previous['aliases']
        else:
            spec = importlib.util.spec_from_file_location('studio_item_icon_pack_reader', reader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _, entries = module.read_pack(inputs[1].read_bytes(), inputs[2].read_bytes())
            entry = next((e for e in entries if e.key() == 'gamedata/item_list.txt'), None)
            aliases = item_list_aliases(module.entry_data(entry)) if entry else {}
            state.mkdir(parents=True, exist_ok=True)
            temporary = cache.with_suffix('.tmp')
            temporary.write_text(json.dumps({'version': 1, 'fingerprint': fingerprint, 'aliases': aliases}), encoding='utf-8')
            temporary.replace(cache)
        # Use the actual filename casing on both Windows and case-sensitive hosts.
        files = {p.name.lower(): p.name for p in folder.glob('*.png') if p.is_file()}
        return {str(ident): files[name.lower()] for ident, name in aliases.items()
                if re.fullmatch(r'\d{1,10}', str(ident)) and isinstance(name, str) and name.lower() in files}
    except Exception:
        # Older packages may not ship the reader or use a supported pack format.
        # Keep their original web icon map and exact-ID PNG fallback functional.
        return {}


def icon_path(root, mapping, ident):
    if not re.fullmatch(r'\d{1,10}', str(ident)):
        return None
    folder = (Path(root) / 'files/static/icons').resolve()
    for name in (mapping.get(ident), f'{int(ident):05d}.png'):
        if not isinstance(name, str) or Path(name).name != name or not name.lower().endswith('.png'):
            continue
        path = folder / name
        if path.is_file() and path.resolve().is_relative_to(folder):
            return path
    return None
