"""Collection source declarations: bounded ids and independent, confined folders."""
import json
from pathlib import Path

from .hubcore.packages import ID_RE, PackageError, confined_file, load_package, logical_path, parse_json

COLLECTION_LIMIT = 256 * 1024
MAX_ADDONS = 20


def validate_collection(value):
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 1:
        raise PackageError('Only collection schema version 1 is supported.')
    result = {'schema_version': 1}
    for key in ('name', 'publisher'):
        label = value.get(key)
        if not isinstance(label, str) or not label.strip() or len(label) > 128 or any(ord(c) < 32 for c in label):
            raise PackageError('Collection %s must be nonempty text of at most 128 characters.' % key)
        result[key] = label
    rows = value.get('addons')
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ADDONS:
        raise PackageError('A collection must list 1 to 20 add-ons.')
    result['addons'] = []
    ids, paths = set(), []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'id', 'path'} or not isinstance(row.get('id'), str) or not ID_RE.fullmatch(row['id']) or row['id'] in ids:
            raise PackageError('Collection entries need a unique add-on id and a relative path.')
        path = logical_path(row['path'])
        logical_path(path + '/addon.json')
        folded = path.casefold()
        if any(folded == old or folded.startswith(old + '/') or old.startswith(folded + '/') for old in paths):
            raise PackageError('Collection folders must be distinct, non-overlapping paths without case collisions.')
        ids.add(row['id'])
        paths.append(folded)
        result['addons'].append({'id': row['id'], 'path': path})
    return result


def load_collection(root):
    root = Path(root).resolve()
    if (root / 'addon.json').exists():
        raise PackageError('A collection root cannot also contain addon.json. Put each add-on in its own folder.')
    path = confined_file(root, 'addons.json')
    if path.stat().st_size > COLLECTION_LIMIT:
        raise PackageError('addons.json exceeds 256 KiB.')
    declaration = validate_collection(parse_json(path.read_bytes(), COLLECTION_LIMIT))
    packages = []
    for row in declaration['addons']:
        manifest = confined_file(root, row['path'] + '/addon.json')
        package = load_package(manifest.parent)
        if package.manifest['id'] != row['id']:
            raise PackageError('Collection id does not match the add-on manifest in %s.' % row['path'])
        packages.append(package)
    return declaration, packages


def create_collection(root, paths, name, publisher):
    root = Path(root).resolve()
    output = root / 'addons.json'
    if output.exists() or (root / 'addon.json').exists():
        raise PackageError('Collection output already exists or the root contains addon.json.')
    rows = []
    for path in paths:
        manifest = confined_file(root, logical_path(path) + '/addon.json')
        package = load_package(manifest.parent)
        rows.append({'id': package.manifest['id'], 'path': path})
    declaration = validate_collection({'schema_version': 1, 'name': name, 'publisher': publisher, 'addons': rows})
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(declaration, indent=2, ensure_ascii=False) + '\n')
    return {'path': str(output), 'addons': declaration['addons']}
