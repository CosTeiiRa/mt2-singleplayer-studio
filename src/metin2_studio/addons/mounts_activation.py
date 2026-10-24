"""Read-only activation plans for the original Legacy Mount Support quest.

Plans contain saved-file changes, never a build, database write or game action.
The caller owns backup/commit/deployment and supplies verified current client
model availability. An engine profile establishes the native API boundary;
package declarations and version labels cannot grant that support.
"""
from __future__ import annotations

import copy
import base64
import hashlib
import json
from pathlib import Path
import re

from metin2_studio import quest_support

IDENTITY = 'mounts_legacy'
SOURCE = 'quest/mounts_legacy.quest'
TEMPLATE_KEY = 'server/mounts_legacy.quest.in'
MAPPING_KEY = 'server/mounts.json'
PAYLOAD = Path(__file__).resolve().parent / 'catalog/community.legacy-mount-support/payload'
HISTORICAL_SOURCE_SHA256 = '1d8ef93c47e2e2dab6712bcca1193683eb0571563f4eda8e99f0516a5bc49c17'
NATIVE_ITEM_IDS = (71124, 71125, 71126, 71127, 71128, 71131, 71132, 71133,
                   71134, 71137, 71138, 71139, 71140, 71141, 71142, 71161,
                   71164, 71165, 71166, 71171, 71172)
ENGINE_PROFILES = {
    # Offline ELF registration table: get_point at 0x10f7828 -> 0x753bc0
    # reads Lua argument 1 on the current character. pc.mount at 0x73fc70
    # installs model as point 109 through affect 221. Native table 0xca88a0
    # has 21 rows consumed by 0x8af220. Type-18 UseItemEx dispatch at
    # 0x15add8 reaches questmanager::UseItem at 0x80ccc0, not that table.
    # Static capability evidence is not a runtime gameplay confirmation.
    '673cae985c2060e664103f3756d86de54b3773bdde4565adc5b94602f92f983a': {
        'point_api': 'pc.get_point', 'point_api_arity': 1, 'native_item_ids': list(NATIVE_ITEM_IDS),
        'mount_point': 109, 'inventory_slots': 225, 'mount_bonus_affect': 533,
        'evidence': 'Offline ELF32 registration, point-affect dispatch and native seal-table inspection.',
    },
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def _read(path):
    path = Path(path)
    return path.read_bytes() if path.is_file() else None


def _payload(package, key):
    if package is None:
        return (PAYLOAD / key).read_bytes()
    files = package.files if hasattr(package, 'files') else package
    raw = files.get(key)
    if not isinstance(raw, bytes):
        raise ValueError('Legacy Mount Support is missing ' + key + '.')
    return raw


def mappings(package=None):
    raw = _payload(package, MAPPING_KEY)
    if len(raw) > 256 * 1024:
        raise ValueError('The mount mapping exceeds its size limit.')
    value = json.loads(raw.decode('ascii'))
    if not isinstance(value, dict) or value.get('schema_version') != 1 or value.get('quest_identity') != IDENTITY:
        raise ValueError('Unsupported mount mapping format.')
    rows = value.get('rows')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 256:
        raise ValueError('Provide between 1 and 256 documented legacy mount mappings.')
    seen, result = set(), []
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError('A mount mapping must be an object.')
        row = copy.deepcopy(item)
        for key, lower, upper in (('vnum', 1, 9999999), ('model', 1, 9999999),
                                   ('bonus', -100000, 100000), ('level', 0, 255),
                                   ('duration', 0, 31536000)):
            if type(row.get(key)) is not int or not lower <= row[key] <= upper:
                raise ValueError('Invalid mount mapping field: ' + key)
        if row['vnum'] in seen or row['vnum'] in NATIVE_ITEM_IDS:
            raise ValueError('Mount mappings must be unique and exclude native seals.')
        if not isinstance(row.get('apply'), str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', row['apply']):
            raise ValueError('Invalid mount bonus type.')
        if any(type(row.get(key)) is not bool for key in ('consume', 'timed')):
            raise ValueError('Mount lifetime and consumption flags must be booleans.')
        if not row['timed'] and not row['duration']:
            raise ValueError('A non-real-time mount needs a bounded duration.')
        seen.add(row['vnum'])
        result.append(row)
    return sorted(result, key=lambda row: row['vnum'])


def model_requests(package=None):
    return sorted({row['model'] for row in mappings(package)})


def _definitions(studio, guards):
    explicit = getattr(studio, 'mount_item_definitions', None)
    if explicit is not None:
        return {str(key): value for key, value in explicit.items()}
    catalogue = getattr(studio, 'catalogue', None)
    if catalogue is not None:
        refresh = getattr(studio, 'refresh_catalog', None)
        if callable(refresh):
            refresh(force=True)
        elif callable(getattr(catalogue, 'refresh', None)):
            catalogue.refresh(force=True)
        # Include physical data as a guard even when a live catalogue provides
        # richer rows. A cached snapshot alone cannot hide a package update.
        seed = Path(studio.game).parent / 'mariadb/initdb.d/dumps/world.sql'
        guards[seed] = sha(_read(seed))
        status = getattr(catalogue, 'status', {})
        if status.get('refreshPending') or status.get('cacheFromOlderVersion'):
            raise ValueError('Current item definitions could not be refreshed after this package update. Refresh the server catalogue before applying mounts.')
        return catalogue.export().get('definitions', {})
    from metin2_studio.server import sql_rows
    path = Path(studio.game).parent / 'mariadb/initdb.d/dumps/world.sql'
    raw = _read(path)
    guards[path] = sha(raw)
    if raw is None:
        raise ValueError('Installed item definitions are unavailable; inspect the game package first.')
    return {row[0]: row for row in sql_rows(raw.decode('utf-8-sig', 'replace'), 'item_proto')}


def _profile(studio, capabilities):
    engine = Path(studio.game) / 'bin/game'
    fingerprint = sha(_read(engine))
    profile = copy.deepcopy(capabilities) if capabilities is not None else copy.deepcopy(ENGINE_PROFILES.get(fingerprint))
    if not profile:
        raise ValueError('This server engine has no verified mount-activation API profile. Add support for its exact engine build before applying activation.')
    if profile.get('engine_sha256', fingerprint) != fingerprint or not fingerprint:
        raise ValueError('The server engine changed after mount capability validation.')
    if (profile.get('point_api') != 'pc.get_point' or profile.get('point_api_arity', 2) not in (1, 2) or profile.get('mount_point') != 109
            or profile.get('mount_bonus_affect') != 533
            or type(profile.get('inventory_slots')) is not int or not 1 <= profile['inventory_slots'] <= 10000):
        raise ValueError('Unsupported mount-activation API profile.')
    native = profile.get('native_item_ids')
    if not isinstance(native, (list, tuple)) or any(type(ident) is not int or ident <= 0 for ident in native):
        raise ValueError('The native mount-handler profile is incomplete.')
    profile['engine_sha256'] = fingerprint
    profile.setdefault('point_api_arity', 2)
    return profile


def _without_comments(raw):
    text = (raw or b'').decode('utf-8', 'replace')
    text = re.sub(r'--\[\[.*?\]\]', '', text, flags=re.S)
    return re.sub(r'--[^\r\n]*', '', text)


def _active_sources(studio, guards):
    """Inspect only registered or explicitly compiled sources, not _unused."""
    sources = set(quest_support.registered_sources(_ReadOverlay(studio, {})))
    dockerfile = Path(studio.game) / 'Dockerfile'
    raw = _read(dockerfile)
    guards[dockerfile] = sha(raw)
    for group in re.findall(r'for\s+q\s+in\s+([A-Za-z0-9_ \t\r\n\\-]+);\s*do', _without_comments(raw)):
        sources.update('quest/' + name + '.quest' for name in group.replace('\\', ' ').split()
                       if re.fullmatch(r'[A-Za-z0-9_]+', name))
    return sorted(sources)


def _provided_items(studio, rows, guards, *, own_source_known=False):
    ids = {row['vnum'] for row in rows}
    provided, conflicts = set(), []
    for relative in _active_sources(studio, guards):
        path = Path(studio.game) / relative
        raw = _read(path)
        guards[path] = sha(raw)
        identity = quest_support.quest_name(raw)
        if identity == IDENTITY:
            if relative != SOURCE:
                conflicts.append('Another registered source already declares mounts_legacy: ' + relative)
            continue
        if identity == 'boar_mount_52006':
            conflicts.append('The previous boar-only quest is still compiled. Migrate its handler before enabling Legacy Mount Support.')
            continue
        text = _without_comments(raw)
        provided.update(int(ident) for event in re.findall(r'\bwhen\s+(.*?)\s+begin\b', text, re.S)
                        for ident in re.findall(r'(?<![A-Za-z0-9_])(\d+)\.use\b', event) if int(ident) in ids)
    objects = Path(studio.game) / 'share/locale/poland/quest/object'
    for ident in ids:
        folder = objects / str(ident) / 'use'
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            raw = _read(path)
            guards[path] = sha(raw)
            if not raw:
                continue
            if path.name.startswith(IDENTITY + '.'):
                if not own_source_known:
                    conflicts.append('Compiled mounts_legacy handlers exist without a known managed/manual source. Preserve and review that installation before adoption.')
                continue
            if path.name.startswith('boar_mount_52006.'):
                conflicts.append('The previous boar-only compiled handler is present. Migrate it before enabling Legacy Mount Support.')
            else:
                provided.add(ident)
    return provided, conflicts


def _cleanup_source(profile):
    # The identity and qflags are retained until every old rider returns. This
    # dormant handler cannot activate a seal or alter another mount/horse.
    source = '''-- Legacy Mount Support disabled: cleanup-only retirement handler.
quest mounts_legacy begin
    state start begin
        function clear_owned_mount()
            local model = pc.getqf("active_model")
            if model > 0 then
                local mounted = pc.get_point(pc.get_player_id(), 109)
                if mounted == model then pc.unmount()
                elseif mounted == 0 and not pc.is_riding() then affect.remove_new(533) end
            end
            cleartimer("legacy_mount_watch")
            pc.setqf("active_item", 0)
            pc.setqf("active_vnum", 0)
            pc.setqf("active_model", 0)
            pc.setqf("active_until", 0)
        end
        when login or logout or legacy_mount_watch.timer begin
            mounts_legacy.clear_owned_mount()
        end
    end
end
'''
    return _point_source(source, profile).encode('ascii')


def _point_source(source, profile):
    if profile['point_api_arity'] == 1:
        return source.replace('pc.get_point(pc.get_player_id(), 109)', 'pc.get_point(109)')
    return source


def _render(package, rows, profile):
    template = _payload(package, TEMPLATE_KEY).decode('ascii')
    if quest_support.quest_name(template.encode('ascii')) != IDENTITY:
        raise ValueError('The activation template must preserve the mounts_legacy identity.')
    if template.count('__DEFINITIONS__') != 1 or template.count('__EVENTS__') != 1:
        raise ValueError('The activation template has invalid generation markers.')
    definitions = '\n'.join('                [%d] = {%d, apply.%s, %d, %d, %d, %d, %d, %d},' %
        (row['vnum'], row['model'], row['apply'], row['bonus'], row['level'], row['duration'],
         row['consume'], row['timed'], row['available']) for row in rows)
    source = template.replace('__DEFINITIONS__', definitions).replace('__EVENTS__', ' or '.join(str(row['vnum']) + '.use' for row in rows))
    source = source.replace('for cell = 0, 224 do', 'for cell = 0, %d do' % (profile['inventory_slots'] - 1))
    return _point_source(source, profile).encode('ascii')


class _ReadOverlay:
    def __init__(self, studio, changes):
        self._studio, self._changes = studio, changes
        self.game = Path(studio.game)

    def read(self, path):
        path = Path(path)
        return self._changes[path] if path in self._changes else _read(path)

    def __getattr__(self, name):
        return getattr(self._studio, name)


def _integration_changes(studio, source):
    path = Path(studio.game) / SOURCE
    changes = {path: source}
    overlay = _ReadOverlay(studio, changes)
    sources = quest_support.registered_sources(overlay)
    if SOURCE not in sources:
        sources.append(SOURCE)
    sources = sorted(set(sources))
    registry = Path(studio.game) / 'custom-quests' / quest_support.SOURCE_LIST
    changes[registry] = ('# Existing quest sources compiled after package quests.\n' + '\n'.join(sources) + '\n').encode('ascii')
    changes.update(quest_support.build_changes(overlay, sources))
    dockerfile = Path(studio.game) / 'Dockerfile'
    hook = changes[dockerfile]
    needle = b'      /usr/local/bin/qc "$name"; \\\n'
    if hook.count(needle) != 1:
        raise ValueError('The Studio compiler hook changed; review mount registration before applying.')
    # quest_support retains the conditional whitelist when another quest editor
    # regenerates the shared hook. Never grant it to the remaining quest loop.
    if b'pc.get_point' not in hook:
        raise ValueError('The Studio compiler integration does not provide the scoped mount API whitelist.')
    return {path: raw for path, raw in changes.items() if _read(path) != raw}


def inspect_activation(studio, package=None, *, asset_availability=None, capabilities=None, owned=None):
    return plan_activation(studio, package, 'inspect', asset_availability=asset_availability,
                           capabilities=capabilities, owned=owned)


def plan_activation(studio, package=None, action='install', *, asset_availability=None, capabilities=None, owned=None):
    """Return an exact saved-source plan. The caller must check every guard again.

    owned is the previous result's ownership object, including source_sha256
    (the last successful managed source hash) and the recoverable baseline.
    Remove/disable leaves a cleanup-only quest registered for offline riders.
    It never deletes saved character flags directly or assumes everyone is online.
    """
    if action not in ('inspect', 'install', 'update', 'reapply', 'repair', 'enable', 'disable', 'remove'):
        raise ValueError('Unsupported mount activation action.')
    changes, guards, conflicts, warnings = {}, {}, [], []
    path = Path(studio.game) / SOURCE
    current = _read(path)
    guards[path] = sha(current)
    registry = Path(studio.game) / 'custom-quests' / quest_support.SOURCE_LIST
    guards[registry] = sha(_read(registry))
    engine = Path(studio.game) / 'bin/game'
    guards[engine] = sha(_read(engine))
    status, rows, native, provided, absent = 'ready', [], set(), set(), []
    source, profile, context_sha256 = None, None, None
    ownership = copy.deepcopy(owned or {})
    try:
        profile = _profile(studio, capabilities)
        native = set(profile['native_item_ids'])
        recipe = mappings(package)
        known_owned = (owned or {}).get('source_sha256')
        known_hashes = (known_owned, HISTORICAL_SOURCE_SHA256, sha(_cleanup_source(profile)))
        provided, source_conflicts = _provided_items(studio, recipe, guards,
                                                     own_source_known=bool(owned) or current is not None and sha(current) in known_hashes)
        conflicts.extend(source_conflicts)
        definitions = _definitions(studio, guards) if action not in ('disable', 'remove') else {}
        foreign = ((str(file), digest) for file, digest in guards.items()
                   if file not in (path, registry, engine, Path(studio.game) / 'Dockerfile')
                   and not file.name.startswith(IDENTITY + '.'))
        context_sha256 = sha(json.dumps({'definitions': {str(row['vnum']): definitions.get(str(row['vnum'])) for row in recipe},
                                        'handler_files': sorted(foreign),
                                        'provided': sorted(provided)}, sort_keys=True, separators=(',', ':')).encode())
        if current is not None and sha(current) not in known_hashes:
            conflicts.append('The existing mounts_legacy source is not a known managed/manual version. Keep it and review its custom changes before adoption.')
        if action in ('disable', 'remove'):
            if current is None and not owned:
                status = 'not-installed'
            else:
                source = _cleanup_source(profile)
                status = 'cleanup-only'
                warnings.append('A dormant cleanup-only quest remains registered for offline riders. It cannot activate seals and clears only this add-on\'s recorded ride when they return.')
        else:
            if asset_availability is None:
                raise ValueError('Verify the current client model assets before preparing mount activation.')
            for original in recipe:
                ident = original['vnum']
                if ident in native or ident in provided:
                    continue
                definition = definitions.get(str(ident))
                if definition is None:
                    absent.append(ident)
                    continue
                if isinstance(definition, dict):
                    typ = definition.get('type')
                    limits = [(definition.get('limittype' + str(i), 0), definition.get('limitvalue' + str(i), 0)) for i in (0, 1)]
                else:
                    if len(definition) < 24:
                        raise ValueError('Item definitions do not expose supported mount type and lifetime fields.')
                    typ = definition[3]
                    limits = [(definition[i], definition[i + 1]) for i in (20, 22)]
                if str(typ) != '18':
                    conflicts.append('Seal %d changed item type and has no verified native-handler mapping; its activation is left unchanged.' % ident)
                    continue
                row = copy.deepcopy(original)
                row['timed'] = any(int(kind) in (6, 7) for kind, value in limits)
                row['level'] = max([row['level']] + [int(value) for kind, value in limits if int(kind) == 1])
                if not row['timed'] and not row['duration']:
                    conflicts.append('Seal %d no longer has its known absolute-expiry limit. Review its lifetime before enabling it.' % ident)
                    continue
                row['available'] = asset_availability.get(row['model'], asset_availability.get(str(row['model']))) is True
                rows.append(row)
            if absent:
                warnings.append('%d mapped seals are absent from this game and are not added.' % len(absent))
            if provided:
                warnings.append('%d seals already have compiled/registered game quest handlers and are not intercepted.' % len(provided))
            if any(not row['available'] for row in rows):
                warnings.append('%d seals keep their intended missing appearance and refuse activation without consuming the seal.' % sum(not row['available'] for row in rows))
            if rows:
                source = _render(package, rows, profile)
                if current == source:
                    status = 'already-integrated' if SOURCE in quest_support.registered_sources(_ReadOverlay(studio, {})) else 'adopted'
                elif current is not None and sha(current) == HISTORICAL_SOURCE_SHA256:
                    status = 'adopted'
            elif provided or native.intersection(row['vnum'] for row in recipe):
                status = 'already-provided'
                if current is not None or owned:
                    source = _cleanup_source(profile)
                    warnings.append('The game provides the mapped activation paths; the old add-on source is retired to cleanup-only handling.')
            else:
                conflicts.append('No supported legacy seal definitions are available in this installation.')
        if source is not None:
            changes = _integration_changes(studio, source)
        if not owned:
            ownership.update(baseline_source_sha256=sha(current),
                             baseline_source_base64=base64.b64encode(current).decode('ascii') if current is not None else None,
                             baseline_registered=SOURCE in quest_support.registered_sources(_ReadOverlay(studio, {})))
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as error:
        conflicts.append(str(error))
    for changed_path in changes:
        guards.setdefault(changed_path, sha(_read(changed_path)))
    if conflicts:
        status = 'blocked'
        changes = {}
    ownership.update(identity=IDENTITY, source=path.relative_to(Path(studio.root)).as_posix(),
                     source_sha256=sha(source) if source is not None else sha(current),
                     adopted=ownership.get('adopted', False) or current is not None and sha(current) == HISTORICAL_SOURCE_SHA256,
                     cleanup_only=status == 'cleanup-only' or bool(source and b'cleanup-only retirement' in source))
    return {'status': status, 'conflicts': sorted(set(conflicts)), 'warnings': warnings,
            'changes': changes, 'guards': list(guards.items()), 'requires_build': bool(changes), 'context_sha256': context_sha256,
            'component': {'id': 'activation', 'name': 'Legacy seal activation', 'status': status,
                          'seals': len(rows), 'available': sum(bool(row['available']) for row in rows),
                          'refused_missing_assets': sum(not row['available'] for row in rows),
                          'provided_by_game': sorted(provided), 'native_seals_untouched': sorted(native),
                          'absent_seals': absent, 'engine_sha256': sha(_read(engine)),
                          'source': SOURCE, 'combat': 'separate'},
            'ownership': ownership}
