"""Creator CLI: scaffold, validate, pack, inspect, catalog and collection sources."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import quote, urljoin

PROJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROJECT), str(PROJECT / 'src')]
from metin2_studio.addons.artifacts import build_artifact, inspect_artifact
from metin2_studio.addons.collections import create_collection, load_collection
from metin2_studio.addons.hubcore.packages import ID_RE, load_package, sha256, validate_manifest
from metin2_studio.addons.repositories import validate_index
from metin2_studio.addons.transport import https_url
from metin2_studio.addons.versions import Version


def scaffold(addon_id, name, author, destination, version='0.1.0', license_name='UNLICENSED'):
    if not ID_RE.fullmatch(addon_id):
        raise ValueError('Use an id such as yourname.example.')
    Version(version)
    if not name.strip() or not author.strip():
        raise ValueError('Provide an add-on name and author.')
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Scaffold destination already exists.')
    module = addon_id.replace('.', '_').replace('-', '_') + '_' + sha256(addon_id.encode())[:8]
    payload = b'''# -*- coding: utf-8 -*-
# Client API v1; keep Python 2.7/3-compatible syntax.
def register(context):
    last_map = [None]

    def on_update(atlas):
        name = getattr(atlas, 'mapName', None)
        if name != last_map[0]:
            last_map[0] = name
            if context.settings.get('log_map_changes', True):
                context.log('Atlas map changed: ' + str(name))

    def on_destroy(atlas):
        last_map[0] = None

    context.on('atlas.update', on_update)
    context.on('atlas.destroy', on_destroy)
    context.log('Registered')
'''
    manifest = {'schema_version': 1, 'api_version': 1, 'id': addon_id, 'name': name, 'author': author,
                'version': version, 'description': 'Original client atlas extension created with the Studio creator tools.',
                'category': 'Interface', 'kind': 'client-python', 'entry': 'm2hub_addons.' + module,
                'requires': [], 'conflicts': [], 'capabilities': ['atlas.events'], 'license': license_name,
                'files': [{'source': module + '.py', 'target': 'm2hub_addons/' + module + '.py', 'sha256': sha256(payload)}],
                'settings_schema': {'type': 'object', 'properties': {'log_map_changes': {'type': 'boolean', 'default': True}}},
                'compatibility': {'client_versions': ['2.0.112'], 'experimental': True},
                'release_notes': 'Initial creator scaffold. Interactive game validation is not recorded.'}
    validate_manifest(manifest)
    destination.mkdir(parents=True)
    (destination / 'payload').mkdir()
    (destination / 'payload' / (module + '.py')).write_bytes(payload)
    (destination / 'addon.json').write_text(json.dumps(manifest, indent=2) + '\n', 'utf-8')
    load_package(destination)
    return {'id': addon_id, 'path': str(destination), 'entry': manifest['entry']}


def catalog(artifacts, name, publisher, base_url, output):
    base_url = https_url(base_url.rstrip('/') + '/')
    packages = {}
    filenames = set()
    inspected = []
    for artifact in artifacts:
        artifact = Path(artifact)
        if artifact.name.casefold() in filenames:
            raise ValueError('Artifact filenames must be unique within the release base URL.')
        filenames.add(artifact.name.casefold())
        info = inspect_artifact(artifact.read_bytes())
        inspected.append((artifact, info))
    # The newest manifest supplies display metadata independently of argument order.
    for artifact, info in sorted(inspected, key=lambda row: (Version(row[1]['manifest']['version']), row[1]['manifest']['version']), reverse=True):
        manifest = info['manifest']
        item = packages.setdefault(manifest['id'], {'id': manifest['id'], 'name': manifest['name'],
            'description': manifest['description'], 'author': manifest['author'], 'category': manifest['category'], 'releases': []})
        if any(row['version'] == manifest['version'] for row in item['releases']):
            raise ValueError('Duplicate artifact id/version in catalog inputs.')
        item['releases'].append({'version': manifest['version'], 'url': urljoin(base_url, quote(artifact.name, safe='')),
                                'sha256': info['sha256'], 'bytes': info['bytes'],
                                'release_notes': manifest.get('release_notes', 'No release notes provided.')})
    result = validate_index({'schema_version': 1, 'name': name, 'publisher': publisher, 'packages': list(packages.values())})
    output = Path(output)
    if output.exists():
        raise ValueError('Catalog output already exists. Use a fresh output filename.')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', 'utf-8')
    return {'packages': len(result['packages']), 'path': str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('new')
    create.add_argument('id')
    create.add_argument('--name', required=True)
    create.add_argument('--author', required=True)
    create.add_argument('--output', type=Path, required=True)
    create.add_argument('--version', default='0.1.0')
    create.add_argument('--license', default='UNLICENSED')
    validate = commands.add_parser('validate')
    validate.add_argument('path', type=Path)
    pack = commands.add_parser('pack')
    pack.add_argument('path', type=Path)
    pack.add_argument('--output', type=Path, required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('path', type=Path)
    index = commands.add_parser('catalog')
    index.add_argument('artifacts', type=Path, nargs='+')
    index.add_argument('--name', required=True)
    index.add_argument('--publisher', required=True)
    index.add_argument('--base-url', required=True)
    index.add_argument('--output', type=Path, required=True)
    collection = commands.add_parser('collection')
    collection.add_argument('path', type=Path)
    collection.add_argument('--name', required=True)
    collection.add_argument('--publisher', required=True)
    collection.add_argument('--addon', action='append', required=True)
    check_collection = commands.add_parser('validate-collection')
    check_collection.add_argument('path', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'new':
            result = scaffold(args.id, args.name, args.author, args.output, args.version, args.license)
        elif args.command == 'validate':
            package = load_package(args.path)
            result = {'id': package.manifest['id'], 'version': package.manifest['version'], 'package_digest': package.digest}
        elif args.command == 'collection':
            result = create_collection(args.path, args.addon, args.name, args.publisher)
        elif args.command == 'validate-collection':
            declaration, packages = load_collection(args.path)
            result = {'name': declaration['name'], 'addons': [package.metadata() for package in packages]}
        elif args.command == 'pack':
            result = build_artifact(args.path, args.output)
        elif args.command == 'inspect':
            result = inspect_artifact(args.path.read_bytes())
        else:
            result = catalog(args.artifacts, args.name, args.publisher, args.base_url, args.output)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
