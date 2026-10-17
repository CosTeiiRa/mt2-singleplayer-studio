"""Read-only discovery of quest routes that open the Cube recipe system."""
import hashlib
import re
from quest_fields import tokens, calls
from quest_support import registered_sources, quest_name


def opens_cube(text):
    ts = tokens(text)
    for name, args, _, _ in calls(ts):
        if name == 'cube.open':
            return True
        if name == 'command' and len(args) == 1 and len(args[0]) == 1:
            value = args[0][0]
            if value.kind == 'string' and re.fullmatch(r'cube\s+open', value.value[1:-1]):
                return True
    return False


def npc_routes(raw):
    text = raw.decode('latin1')
    ts = tokens(text)
    starts = [i for i, token in enumerate(ts) if token.kind == 'name' and token.value == 'when']
    for offset, start in enumerate(starts):
        stop = starts[offset + 1] if offset + 1 < len(starts) else len(ts)
        begin = next((i for i in range(start + 1, stop) if ts[i].value == 'begin'), None)
        if begin is None:
            continue
        header = ts[start + 1:begin]
        if not opens_cube(text[ts[begin].end:ts[stop].start if stop < len(ts) else len(text)]):
            continue
        for i in range(len(header) - 2):
            if header[i].kind == 'number' and [t.value for t in header[i + 1:i + 3]] == ['.', 'chat']:
                yield header[i].value


def discover(studio):
    docker = studio.read(studio.game / 'Dockerfile') or b''
    compiled = set()
    for names in re.findall(rb'for q in\s+([^;]+);\s*do', docker):
        compiled.update(name for name in names.replace(b'\\', b' ').decode('ascii').split() if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name))
    sources = {studio.game / 'quest' / (name + '.quest') for name in compiled}
    sources.update(studio.game / rel for rel in registered_sources(studio))
    sources.update(studio.game.joinpath('custom-quests').glob('studio_*.quest'))
    docs = [(p, studio.read(p)) for p in sorted(sources) if studio.read(p) is not None]
    stock = studio.locale / 'quest/object'
    version = studio.root / 'VERSION'
    key = (hashlib.sha256(docker).hexdigest(),
           tuple((p.as_posix(), hashlib.sha256(raw).hexdigest()) for p, raw in docs),
           version.stat().st_mtime_ns if version.exists() else 0,
           stock.stat().st_mtime_ns if stock.exists() else 0)
    cached = getattr(studio, '_crafting_access', None)
    if cached and cached[0] == key:
        return cached[1]
    routes = {}
    overrides = {quest_name(raw) for _, raw in docs}
    for p in stock.glob('*/chat/*.script'):
        if p.name.split('.')[0] in overrides:
            continue
        npc = p.parent.parent.name
        if npc.isdigit() and opens_cube(p.read_text('latin1')):
            routes.setdefault(npc, []).append(p.relative_to(studio.root).as_posix())
    for p, raw in docs:
        for npc in npc_routes(raw):
            routes.setdefault(npc, []).append(p.relative_to(studio.root).as_posix())
    result = [{'id': npc, 'name': studio.mobs[npc]['name'],
               'source': 'seon' if npc == '20091' else 'base', 'evidence': sorted(set(evidence))}
              for npc, evidence in sorted(routes.items(), key=lambda pair: int(pair[0]))
              if npc in studio.mobs and studio.mobs[npc]['category'] == 'npc']
    studio._crafting_access = key, result
    return result


def native_calls(text, constants, npc):
    """Resolve only literal/constant windows and the game's NPC-vnum route."""
    for name, args, _, _ in calls(tokens(text)):
        if name != 'crafting.open' or len(args) != 1:
            continue
        value = ''.join(t.value for t in args[0])
        window = npc if value == 'npc.get_vnum()' else constants.get(value, value)
        if str(window).isdigit() and int(window) > 0:
            yield str(window)


def discover_native(studio):
    definitions = studio.locale / 'quest/libs/crafting/crafting_data.lua'
    raw = studio.read(definitions) or b''
    constants = dict(re.findall(r'\b(CRAFTING_[A-Z_]+)\s*=\s*(\d+)', raw.decode('latin1')))
    stock = studio.locale / 'quest/object'
    source_root = studio.locale / 'quest/quest'
    sources = [p for p in source_root.rglob('*') if p.suffix in ('.quest', '.lua') and '_unused' not in p.parts]
    docs = [(p, studio.read(p)) for p in sorted(sources)]
    version = studio.root / 'VERSION'
    key = (version.stat().st_mtime_ns if version.exists() else 0, hashlib.sha256(raw).hexdigest(), tuple((str(p), hashlib.sha256(data or b'').hexdigest()) for p, data in docs),
           stock.stat().st_mtime_ns if stock.exists() else 0)
    cached = getattr(studio, '_native_crafting_access', None)
    if cached and cached[0] == key:
        return cached[1]
    routes = {}
    for p in stock.glob('*/chat/*.script'):
        npc = p.parent.parent.name
        if npc.isdigit():
            for window in native_calls(p.read_text('latin1'), constants, npc):
                routes.setdefault((npc, window), set()).add(p.relative_to(studio.root).as_posix())
    # Source routes also expose the original entry conditions. Require the
    # quest's installed state; an unused source alone is not an active menu.
    for p, data in docs:
        if not data or not (stock / 'state' / (quest_name(data) or '')).is_file():
            continue
        text = data.decode('latin1')
        ts = tokens(text)
        starts = [i for i, t in enumerate(ts) if t.value == 'when' and t.kind == 'name']
        for offset, start in enumerate(starts):
            stop = starts[offset + 1] if offset + 1 < len(starts) else len(ts)
            begin = next((i for i in range(start + 1, stop) if ts[i].value == 'begin'), None)
            if begin is None:
                continue
            header = ts[start + 1:begin]
            body = text[ts[begin].end:ts[stop].start if stop < len(ts) else len(text)]
            for i in range(len(header) - 2):
                if header[i].kind == 'number' and [t.value for t in header[i + 1:i + 3]] == ['.', 'chat']:
                    npc = header[i].value
                    for window in native_calls(body, constants, npc):
                        routes.setdefault((npc, window), set()).add(p.relative_to(studio.root).as_posix())
    result = [{'id': npc, 'name': studio.mobs[npc]['name'], 'system': 'native', 'window': window,
               'evidence': sorted(evidence)} for (npc, window), evidence in sorted(routes.items(), key=lambda pair: (int(pair[0][0]), int(pair[0][1])))
              if npc in studio.mobs and studio.mobs[npc]['category'] == 'npc']
    studio._native_crafting_access = key, result
    return result
