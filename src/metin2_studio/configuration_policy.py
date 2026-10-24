"""Editable game data, server quest sources and the quest compiler integration."""
from collections import Counter
import re


READ_ONLY_REASON = 'Studio edits supported configurations and server quests. Engine/client binaries and unrelated program files are read-only.'


def editable_path(studio, path):
    path = studio.safe(path)
    if path == studio.compose / '.env':
        return True
    if path in {target for target, _, _ in studio.sources.values()}:
        return True
    if path in (studio.game / 'Dockerfile', studio.game / '.dockerignore'):
        return True
    if path == studio.game / 'custom-quests/studio-source-list.txt':
        return True
    if path == studio.game / 'share-add/studio-crafting.json':
        return True
    if path.parent in (studio.game / 'quest', studio.game / 'custom-quests'):
        return path.suffix.lower() in ('.quest', '.lua')
    if path.is_relative_to(studio.locale):
        relative = path.relative_to(studio.locale)
        if any(part.lower() in ('object', 'pre_qc', '_unused') for part in relative.parts):
            return False
        return path.suffix.lower() in ('.txt', '.tsv', '.lua', '.quest') or path.name in ('regen', 'npc', 'boss', 'stone', 'index')
    return path.parent == studio.game / 'share-add' and path.suffix.lower() in ('.txt', '.tsv')


def check_change(studio, path, old, new):
    path = studio.safe(path)
    if not editable_path(studio, path):
        raise ValueError(READ_ONLY_REASON)
    if path == studio.game / 'share-add/studio-crafting.json' and new is not None:
        import json
        from metin2_studio.native_crafting import validate_document
        try:
            validate_document(json.loads(new))
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ValueError('Use the guided native crafting editor to save a valid configuration.') from None
    new_quest = (path.parent == studio.game / 'custom-quests' and bool(re.fullmatch(r'studio_[a-z][a-z0-9_]{2,40}\.quest', path.name))) or path == studio.game / 'quest/mounts_legacy.quest'
    if old is None and not new_quest and path not in (studio.game / 'custom-quests/studio-source-list.txt', studio.game / 'share-add/studio-crafting.json') and path not in {target for target, _, _ in studio.sources.values()}:
        raise ValueError('New files must be supported drop sources or Studio quest templates. Other new game files need a dedicated integration.')
    if path != studio.compose / '.env':
        return
    if old is None or new is None:
        raise ValueError('World settings must preserve the existing environment file.')
    def lines(raw):
        return raw.removeprefix(b'\xef\xbb\xbf').splitlines()
    def assignments(raw):
        return Counter(line for line in lines(raw) if re.match(rb'^[A-Z][A-Z0-9_]*=', line))
    def unmanaged(raw):
        return [line for line in lines(raw) if line.strip() and not line.lstrip().startswith(b'#') and not (re.match(rb'^[A-Z][A-Z0-9_]*=', line) and line.split(b'=', 1)[0].decode('ascii') in studio.settings_schema)]
    if unmanaged(old) != unmanaged(new):
        raise ValueError('Only exposed gameplay settings can change; internal values and executable lines are preserved.')
    # Validate every new assignment, including duplicate keys whose last value could hide an earlier expression.
    for line in (assignments(new) - assignments(old)).elements():
        key, raw_value = line.split(b'=', 1)
        name = key.decode('ascii')
        schema = studio.settings_schema.get(name)
        if schema is None:
            raise ValueError('Only the exposed gameplay settings can be changed; internal and credential values are preserved.')
        if schema.get('fresh'):
            raise ValueError('New-world rates are read-only. Use the existing Rates page for your current world.')
        value = raw_value.decode('ascii', 'replace')
        if schema.get('options'):
            valid = value in schema['options']
        elif name == 'M2_BRAND':
            valid = bool(re.fullmatch(r'[\w .-]{1,60}', value, re.ASCII))
        elif name == 'M2_MONSTER_HP':
            valid = value in ('default', 'easy') or bool(re.fullmatch(r'\d+', value)) and 10 <= int(value) <= 300
        else:
            valid = bool(re.fullmatch(r'\d+(?:\.\d+)?', value))
            if valid and 'min' in schema:
                valid = schema['min'] <= float(value) <= schema['max']
                if schema.get('step') == '1':
                    valid = valid and value.isdigit()
        if not valid:
            raise ValueError('Use a supported configuration value for ' + name + '.')
