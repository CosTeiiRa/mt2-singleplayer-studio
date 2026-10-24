"""Reviewed, record-level Legacy Mount Support corrections for gamedata.

This module never writes a client file or executes installed Python. Pack keys
and the proto layout are read as literal data from reviewed installed codecs.
The game's models, packs, executable and codec are not redistributed.
"""
from __future__ import annotations

import ast
import copy
import hashlib
from pathlib import Path, PurePosixPath
import re
import struct
import zlib

from . import client_pack

CODEC_SHA256 = {
    'c945fbafa491d294009d0c811b638bf515f3aa996869d8271f9aa7ecc0ad4fd5',
    '3ec242afa8c1b2ed272e6f358be2ada7e608ea3836231dfd4b8f735718000f51',
}
PACK_FILES = ('pack/gamedata.index', 'pack/gamedata.data')
NPC_MEMBER = 'gamedata/npclist.txt'
ITEM_MEMBER = 'gamedata/item_proto'
NPC_FIXES = {20110: ('horse2_king_normal', 'boar'),
             20111: ('horse2_king_member', 'dog_god'),
             20112: ('horse2_master', 'fire_tiger')}
ITEM_FIXES = {'subtype': (0, 2), 'limittype0': (7, 1),
              'limitvalue0': (604800, 20), 'value0': (0, 28800), 'value5': (20119, 0)}
ITEM_INVARIANTS = {'type': 16, 'flag': 9216, 'wearflag': 128,
                   'limittype1': 0, 'limitvalue1': 0,
                   'value1': 0, 'value2': 0, 'value3': 0, 'value4': 0}
MAX_INDEX_BYTES = 32 * 1024 * 1024
MAX_INDEX_TOTAL = 128 * 1024 * 1024


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _regular(path, root):
    path, root = Path(path), Path(root).resolve()
    if '..' in path.parts:
        raise ValueError('Mount client input contains a parent traversal.')
    if not path.resolve().is_relative_to(root):
        raise ValueError('Mount client input escapes the selected installation.')
    cursor = path
    while cursor != root:
        if cursor.is_symlink() or getattr(cursor, 'is_junction', lambda: False)():
            raise ValueError('Linked client inputs are not supported for mount corrections.')
        cursor = cursor.parent
        if cursor == cursor.parent and cursor != root:
            raise ValueError('Mount client input escapes the selected installation.')
    if not path.is_file():
        raise ValueError('Required client input is missing: ' + path.name)
    return path


def _codec(client, server_root=None, codec=None):
    """The injectable literal descriptor is for synthetic tests, never a path."""
    if codec is not None:
        return codec, None
    server = Path(server_root).resolve() if server_root else client.parent / 'Serwer'
    path = _regular(server / 'files/client_protos.py', server)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('The installed client-proto codec exceeds its reviewed size limit.')
    raw = path.read_bytes()
    fingerprint = sha(raw)
    if fingerprint not in CODEC_SHA256:
        raise ValueError('The installed client-proto codec is unreviewed. Client-data fixes need an updated compatibility recipe.')
    wanted = {'PACK_INDEX_KEY', 'PACK_DATA_KEY', 'ITEM_PROTO_KEY', 'ITEM_FIELDS'}
    values = {}
    for node in ast.parse(raw, filename=str(path)).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    values[target.id] = ast.literal_eval(node.value)
    if set(values) != wanted:
        raise ValueError('The reviewed client-proto codec has an unsupported layout.')
    layout = struct.Struct('<' + ''.join(code for _, code in values['ITEM_FIELDS']))
    if layout.size != 184 or values['ITEM_FIELDS'][0] != ('vnum', 'I'):
        raise ValueError('The installed item table is not the supported 184-byte layout.')
    values['ITEM_STRUCT'] = layout
    values['ITEM_NAMES'] = tuple(name for name, _ in values['ITEM_FIELDS'])
    return values, {'path': str(path), 'sha256': fingerprint}


def _pack_config(codec):
    return {'eter_pack_index_key': codec['PACK_INDEX_KEY'], 'eter_pack_data_key': codec['PACK_DATA_KEY']}


def _item_rows(blob, codec):
    if len(blob) < 20:
        raise ValueError('The client item table is truncated.')
    magic, version, stride, count, size = struct.unpack_from('<4sIIII', blob)
    layout = codec['ITEM_STRUCT']
    if (magic, version, stride) != (b'MIPX', 1, layout.size) or count > 100000:
        raise ValueError('The client item table has an unsupported format.')
    if size > len(blob) - 20:
        raise ValueError('The client item table object is truncated.')
    raw = client_pack.decode_object(blob[20:20 + size], codec['ITEM_PROTO_KEY'])
    if len(raw) != count * stride:
        raise ValueError('The client item table row count does not match its contents.')
    rows = [dict(zip(codec['ITEM_NAMES'], layout.unpack_from(raw, at))) for at in range(0, len(raw), stride)]
    if len({row['vnum'] for row in rows}) != len(rows):
        raise ValueError('The client item table contains duplicate item identifiers.')
    return rows


def _write_rows(rows, codec):
    raw = b''.join(codec['ITEM_STRUCT'].pack(*(row[name] for name in codec['ITEM_NAMES'])) for row in rows)
    obj = client_pack.encode_object(raw, codec['ITEM_PROTO_KEY']) + bytes(4)
    return struct.pack('<4sIIII', b'MIPX', 1, codec['ITEM_STRUCT'].size, len(rows), len(obj)) + obj


def _npc_rows(raw):
    rows = {}
    for line in raw.splitlines(keepends=True):
        match = re.match(rb'^([0-9]+)[ \t]+([^\s]+)', line)
        if match:
            ident = int(match[1])
            # Installed npclist files include disabled race-0 rows and a few
            # unrelated duplicates. Preserve these bytes; relevant ambiguous
            # mappings are unavailable rather than choosing a load order.
            rows[ident] = None if ident in rows else match[2].decode('ascii')
    return rows


def _replace_npc(raw, ident, before, after):
    pattern = rb'(?m)^(' + str(ident).encode() + rb'[ \t]+)' + re.escape(before.encode()) + rb'(?=[ \t\r\n]|$)'
    result, count = re.subn(pattern, lambda m: m[1] + after.encode(), raw)
    if count != 1:
        raise ValueError('The reviewed model mapping changed for race %d.' % ident)
    return result


class _AssetIndex:
    """Index inventory plus bounded lazy object reads; no asset extraction."""
    def __init__(self, client, codec):
        self.client, self.codec = client, codec
        self.entries, self.guards, self.used_data = {}, {}, {}
        self.index_paths = []
        total = 0
        folder = client / 'pack'
        index_order = folder / 'Index'
        if index_order.is_file():
            _regular(index_order, client)
            self.guards['pack/Index'] = _file_sha(index_order)
        for index_path in sorted(folder.glob('*.index')):
            _regular(index_path, client)
            data_path = _regular(index_path.with_suffix('.data'), client)
            size = index_path.stat().st_size
            total += size
            if size > MAX_INDEX_BYTES or total > MAX_INDEX_TOTAL:
                raise ValueError('Client asset index inventory exceeds its supported size limit.')
            rel = index_path.relative_to(client).as_posix()
            self.index_paths.append(rel)
            encoded = index_path.read_bytes()
            self.guards[rel] = sha(encoded)
            index = client_pack.decode_object(encoded, codec['PACK_INDEX_KEY']) if encoded[:4] == b'MCOZ' else encoded
            if len(index) < 12:
                raise ValueError('A client asset index is truncated.')
            magic, version, count = struct.unpack_from('<4sII', index)
            if magic != b'EPKD' or version != 2 or count > 100000 or len(index) != 12 + count * client_pack.RECORD.size:
                raise ValueError('A client asset index has an unsupported layout.')
            for offset in range(12, len(index), client_pack.RECORD.size):
                _, name, name_crc, _, length, crc, pos, kind = client_pack.RECORD.unpack_from(index, offset)
                if not name_crc:
                    continue
                path = client_pack.logical_name(name.split(b'\0', 1)[0].decode('latin-1'))
                if kind not in (0, 1, 2) or length > client_pack.MAX_OBJECT or pos + length > data_path.stat().st_size:
                    raise ValueError('A client asset entry is unsupported or out of bounds.')
                self.entries.setdefault(path, []).append((data_path, pos, length, crc, kind))

    def read(self, name):
        name = client_pack.logical_name(name)
        choices = self.entries.get(name, [])
        if not choices:
            raise ValueError('Missing model resource: ' + name)
        values = []
        for path, pos, length, crc, kind in choices:
            _regular(path, self.client)
            if path not in self.used_data:
                self.used_data[path] = _file_sha(path)
            with path.open('rb') as stream:
                stream.seek(pos)
                encoded = stream.read(length)
            if len(encoded) != length or zlib.crc32(encoded) & 0xffffffff != crc:
                raise ValueError('Model resource failed stored CRC validation: ' + name)
            value = encoded if kind == 0 else client_pack.decode_object(encoded, self.codec['PACK_DATA_KEY'])
            values.append(value)
        if any(value != values[0] for value in values[1:]):
            raise ValueError('Ambiguous installed model resource: ' + name)
        return values[0]

    def final_guards(self):
        return {**self.guards, **{path.relative_to(self.client).as_posix(): digest for path, digest in self.used_data.items()}}


def _resolve(folder, reference):
    reference = reference.replace('\\', '/').lower()
    return client_pack.logical_name(reference if re.match(r'^[a-z]:/', reference) else folder + '/' + reference)


def _model_assets(index, name):
    """Return complete render/motion coverage for an exact installed appearance."""
    name = name.lower()
    if not re.fullmatch(r'[a-z0-9_]+', name):
        return {'available': False, 'model': name, 'reason': 'Unsupported installed appearance name.', 'missing': []}
    candidates = [key for key in index.entries if key.endswith('/' + name + '.msm')]
    if not candidates:
        return {'available': False, 'model': name, 'reason': 'The intended appearance has no installed model definition.', 'missing': [name + '.msm']}
    successes, errors = [], []
    for msm_path in sorted(candidates):
        files, coverage = set(), set()
        try:
            def read(path):
                files.add(path)
                return index.read(path).decode('latin-1')
            folder = str(PurePosixPath(msm_path).parent)
            msm = read(msm_path)
            models = re.findall(r'(?im)^\s*BaseModelFileName\s+"([^"]+)"', msm)
            if not models:
                raise ValueError('The model definition does not declare its base model.')
            for reference in models:
                read(_resolve(folder, reference))
            motlist = read(folder + '/motlist.txt')
            for line in motlist.splitlines():
                cells = line.split()
                if len(cells) < 3 or cells[0].startswith(('#', '//')):
                    continue
                mode, kind, reference = cells[:3]
                msa_path = _resolve(folder, reference)
                msa = read(msa_path)
                refs = re.findall(r'(?im)^\s*MotionFileName\s+"([^"]+)"', msa)
                if not refs:
                    raise ValueError('A declared motion lacks its animation resource.')
                for motion in refs:
                    read(_resolve(str(PurePosixPath(msa_path).parent), motion))
                if mode == 'GENERAL':
                    coverage.add(kind)
            if not {'WAIT', 'WALK', 'RUN', 'COMBO_ATTACK'} <= coverage:
                raise ValueError('The intended appearance lacks required mount motions.')
            successes.append({'available': True, 'model': name, 'msm': msm_path,
                              'motion_coverage': sorted(coverage), 'files': sorted(files)})
        except (ValueError, UnicodeError) as error:
            errors.append(str(error))
    if len(successes) == 1:
        return successes[0]
    return {'available': False, 'model': name,
            'reason': 'The intended appearance is ambiguous.' if successes else '; '.join(errors), 'missing': errors}


def _load(client_root, server_root=None, codec=None):
    client = Path(client_root).resolve()
    codec, external_guard = _codec(client, server_root, codec)
    paths = [_regular(client / name, client) for name in PACK_FILES]
    if any(path.stat().st_size > client_pack.MAX_PACK for path in paths):
        raise ValueError('The client gamedata pack exceeds its supported size limit.')
    before = {name: path.read_bytes() for name, path in zip(PACK_FILES, paths)}
    pack = client_pack.EterPack(before[PACK_FILES[0]], before[PACK_FILES[1]], _pack_config(codec))
    for name, entry in pack.entries.items():
        stored = pack.data_bytes[entry['position']:entry['position'] + entry['size']]
        if zlib.crc32(stored) & 0xffffffff != entry['crc']:
            raise ValueError('Stored gamedata CRC validation failed: ' + name)
    logical = pack.files()
    if NPC_MEMBER not in logical or ITEM_MEMBER not in logical:
        raise ValueError('The client gamedata pack is missing its mount tables.')
    return client, codec, external_guard, before, pack, logical


def _blank():
    return {'component': 'client-fixes', 'status': 'ready', 'can_apply': True,
            'changes': [], 'conflicts': [], 'warnings': [], 'outputs': {}, 'guards': {},
            'external_guards': [], 'ownership': {'schema_version': 1, 'mappings': [], 'item_fields': []},
            'assets': {}, 'asset_availability': {}, 'asset_index_paths': []}


def _validate_ownership(owned):
    if not isinstance(owned, dict) or owned.get('schema_version') != 1:
        raise ValueError('Unsupported client mount ownership receipt.')
    for kind, expected in (('mappings', NPC_FIXES), ('item_fields', ITEM_FIXES)):
        records = owned.get(kind, [])
        if not isinstance(records, list):
            raise ValueError('The client mount ownership receipt is malformed.')
        seen = set()
        for row in records:
            if not isinstance(row, dict):
                raise ValueError('The client mount ownership receipt is malformed.')
            key = row.get('vnum') if kind == 'mappings' else row.get('field')
            columns = {'vnum', 'before', 'after'} | ({'field'} if kind == 'item_fields' else set())
            if (set(row) != columns or type(row.get('vnum')) is not int
                    or key not in expected or key in seen
                    or (kind == 'item_fields' and row['vnum'] != 71128)
                    or (row.get('before'), row.get('after')) != expected[key]
                    or (kind == 'item_fields' and any(type(row[x]) is not int for x in ('before', 'after')))):
                raise ValueError('The client mount ownership receipt has unsupported corrections.')
            seen.add(key)


def inspect_client_fixes(client_root, *, server_root=None, codec=None, model_requests=None):
    return plan_client_fixes(client_root, server_root=server_root, codec=codec, model_requests=model_requests)


def plan_client_fixes(client_root, action='install', ownership=None, *, server_root=None,
                      codec=None, model_requests=None, baseline=None):
    """Produce bytes and exact guards only. The coordinator owns the transaction.

    ``ownership`` is the last successfully installed narrow record receipt.
    ``baseline`` may supply backed-up physical pairs for exact unchanged rollback.
    """
    if action not in ('install', 'reapply', 'update', 'enable', 'disable', 'remove'):
        raise ValueError('Unsupported client mount correction action.')
    result = _blank()
    try:
        client, codec, external_guard, before, pack, logical = _load(client_root, server_root, codec)
        result['guards'] = {name: sha(raw) for name, raw in before.items()}
        if external_guard:
            result['external_guards'].append(external_guard)
        result['ownership']['before_sha256'] = copy.deepcopy(result['guards'])
        npc_raw = logical[NPC_MEMBER]
        npc_rows = _npc_rows(npc_raw)
        rows = _item_rows(logical[ITEM_MEMBER], codec)
        target = next((row for row in rows if row['vnum'] == 71128), None)
        removing = action in ('disable', 'remove')
        owned = ownership or {'schema_version': 1, 'mappings': [], 'item_fields': []}
        _validate_ownership(owned)
        mappings = owned.get('mappings', []) if removing else [
            {'vnum': ident, 'before': old, 'after': new} for ident, (old, new) in NPC_FIXES.items()]
        fields = owned.get('item_fields', []) if removing else [
            {'vnum': 71128, 'field': name, 'before': old, 'after': new} for name, (old, new) in ITEM_FIXES.items()]
        proposed_names = dict(npc_rows)
        for record in mappings:
            ident = record['vnum']; old, new = record['before'], record['after']
            expected, replacement = (new, old) if removing else (old, new)
            observed = npc_rows.get(ident)
            if observed == replacement:
                continue
            if observed != expected:
                result['conflicts'].append('Race %d has an unknown model mapping; review it before changing mount data.' % ident)
                continue
            proposed_names[ident] = replacement
        index = None
        if not removing:
            index = _AssetIndex(client, codec)
            requests = dict(model_requests) if isinstance(model_requests, dict) else {int(ident): None for ident in model_requests or NPC_FIXES}
            # Corrected appearances are validated even if activation requests a
            # different model set; they must never install a missing resource.
            requests.update({ident: None for ident in NPC_FIXES})
            for ident, override in requests.items():
                ident = int(ident)
                name = override or proposed_names.get(ident)
                proof = _model_assets(index, name) if name else {'available': False, 'reason': 'No model mapping is installed.'}
                result['assets'][str(ident)] = proof
                result['asset_availability'][ident] = proof['available']
            result['guards'].update(index.final_guards())
            result['asset_index_paths'] = index.index_paths
        for record in mappings:
            ident = record['vnum']; old, new = record['before'], record['after']
            expected, replacement = (new, old) if removing else (old, new)
            observed = npc_rows.get(ident)
            if observed == replacement or observed != expected:
                continue
            if not removing and not result['asset_availability'].get(ident):
                result['conflicts'].append('Race %d cannot be corrected because its intended model assets are missing or invalid.' % ident)
                continue
            npc_raw = _replace_npc(npc_raw, ident, expected, replacement)
            result['changes'].append({'path': NPC_MEMBER, 'vnum': ident, 'field': 'model', 'before': expected, 'after': replacement})
            if not removing:
                result['ownership']['mappings'].append(copy.deepcopy(record))
        if fields:
            if target is None:
                result['conflicts'].append('Mount seal 71128 is missing from the client item table.')
            elif any(target.get(key) != value for key, value in ITEM_INVARIANTS.items()):
                result['conflicts'].append('Mount seal 71128 has an unsupported runtime layout; its custom fields were retained.')
            else:
                for record in fields:
                    name = record['field']; old, new = record['before'], record['after']
                    expected, replacement = (new, old) if removing else (old, new)
                    observed = target[name]
                    if observed == replacement:
                        continue
                    if observed != expected:
                        result['conflicts'].append('Mount seal 71128 field %s changed outside this add-on.' % name)
                        continue
                    target[name] = replacement
                    result['changes'].append({'path': ITEM_MEMBER, 'vnum': 71128, 'field': name, 'before': expected, 'after': replacement})
                    if not removing:
                        result['ownership']['item_fields'].append(copy.deepcopy(record))
        if result['conflicts']:
            result.update(status='conflict', can_apply=False, changes=[], outputs={})
            return result
        output_logical = dict(logical)
        output_logical[NPC_MEMBER] = npc_raw
        if any(change['path'] == ITEM_MEMBER for change in result['changes']):
            output_logical[ITEM_MEMBER] = _write_rows(rows, codec)
        if result['changes']:
            encoded_index, encoded_data = pack.build(output_logical)
            outputs = dict(zip(PACK_FILES, (encoded_index, encoded_data)))
            checked = client_pack.EterPack(encoded_index, encoded_data, _pack_config(codec))
            if checked.files() != output_logical:
                raise ValueError('The staged mount client data did not pass full pack verification.')
            for name, entry in pack.entries.items():
                if logical[name] == output_logical[name]:
                    old_blob = pack.data_bytes[entry['position']:entry['position'] + entry['size']]
                    current = checked.entries[name]
                    new_blob = checked.data_bytes[current['position']:current['position'] + current['size']]
                    if old_blob != new_blob:
                        raise ValueError('An unrelated stored client object changed while staging mount corrections.')
            if removing and baseline and all(result['guards'].get(name) == owned.get('after_sha256', {}).get(name) for name in PACK_FILES):
                original = {name: baseline[name] for name in PACK_FILES}
                if any(sha(raw) != owned.get('before_sha256', {}).get(name) for name, raw in original.items()):
                    raise ValueError('The client mount baseline backup failed its recorded checksum.')
                restored = client_pack.EterPack(original[PACK_FILES[0]], original[PACK_FILES[1]], _pack_config(codec))
                restored_logical = restored.files()
                # The inner MIPX table may use a different valid compressor.
                # Validate every original row, then restore its exact encoding.
                if (set(restored_logical) != set(output_logical)
                        or any(restored_logical[name] != raw for name, raw in output_logical.items() if name != ITEM_MEMBER)
                        or _item_rows(restored_logical[ITEM_MEMBER], codec) != rows):
                    raise ValueError('The recorded client baseline does not match the reviewed inverse corrections.')
                outputs = original
            result['outputs'] = outputs
            result['ownership']['after_sha256'] = {name: sha(raw) for name, raw in outputs.items()}
        else:
            result['ownership']['after_sha256'] = {name: result['guards'][name] for name in PACK_FILES}
        # Unchanged packs retain our existing ownership. A new game pack is a
        # new baseline: corrections already supplied there belong to the game.
        same_pack = all(result['guards'][name] == owned.get('after_sha256', {}).get(name) for name in PACK_FILES)
        had_owned_records = bool(owned.get('mappings') or owned.get('item_fields'))
        if not removing and ownership and same_pack and had_owned_records:
            for kind in ('mappings', 'item_fields'):
                merged = {tuple(sorted(row.items())): row for row in [*ownership.get(kind, []), *result['ownership'][kind]]}
                result['ownership'][kind] = list(merged.values())
            if ownership.get('before_sha256'):
                result['ownership']['before_sha256'] = copy.deepcopy(ownership['before_sha256'])
        elif not removing and ownership and not same_pack:
            result['warnings'].append('The game data changed since the previous application; this application owns only newly required corrections.')
        result['status'] = 'ready' if result['changes'] else 'already-provided'
        result['summary'] = ('%d narrow client-data changes' % len(result['changes']) if result['changes'] else
                             'No owned client corrections require removal.' if removing else
                             'The installed client already provides these data corrections.')
        result['warnings'].append('Client model checks validate installed resources and motion references; they do not prove in-game rendering or combat.')
        verify_client_guards(client, result)
        return result
    except (OSError, ValueError, UnicodeError, struct.error, KeyError, TypeError) as error:
        result.update(status='unavailable', can_apply=False, outputs={}, changes=[])
        result['conflicts'].append(str(error))
        return result


def verify_client_guards(client_root, plan):
    client = Path(client_root).resolve()
    for relative, expected in plan.get('guards', {}).items():
        path = _regular(client / relative, client)
        if _file_sha(path) != expected:
            raise ValueError('Client mount inputs changed since review. Prepare a new plan.')
    if plan.get('asset_index_paths'):
        current = sorted(path.relative_to(client).as_posix() for path in (client / 'pack').glob('*.index'))
        if current != plan['asset_index_paths']:
            raise ValueError('The client asset inventory changed since review. Prepare a new plan.')
    for guard in plan.get('external_guards', []):
        path = Path(guard['path'])
        if _file_sha(path) != guard['sha256']:
            raise ValueError('The installed client-proto codec changed since review.')
