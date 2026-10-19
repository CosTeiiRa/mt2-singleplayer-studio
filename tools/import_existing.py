"""Copy an existing Studio history into a fresh world data folder.

The old apps and state are never moved or rewritten. Legacy Hub transaction
metadata is imported read only; its client targets are not silently adopted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import uuid

PROJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROJECT), str(PROJECT / 'src')]
from metin2_studio.installation import atomic_json, resolve_settings, save_settings, world_state
from metin2_studio.filesystem import retry_windows_lock


def import_existing(server_root, studio_data, hub_data=None, port=8780, destination=None, settings_path=None):
    source = Path(studio_data).resolve()
    server_root = Path(server_root).resolve()
    destination = Path(destination or world_state(server_root)).resolve()
    if destination.exists():
        raise ValueError('Destination world data already exists. Import only into a fresh Studio copy.')
    binding = json.loads((source / 'studio-world.json').read_text('utf-8'))
    if Path(binding['serverRoot']).resolve() != server_root:
        raise ValueError('The source Studio history belongs to another world.')
    selected = resolve_settings(root=server_root, state=destination, port=port, saved={})
    stage = destination.with_name(destination.name + '-import-' + uuid.uuid4().hex[:8])
    stage.mkdir(parents=True)
    copied = []
    for name in ('workspace.sqlite', 'economy.sqlite'):
        database = source / name
        if database.is_file():
            original = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
            snapshot = sqlite3.connect(stage / name)
            try:
                original.backup(snapshot)
                if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Imported database integrity check failed.')
                if name == 'workspace.sqlite':
                    row = snapshot.execute("SELECT value FROM meta WHERE key='installation'").fetchone()
                    if row and Path(row[0]).resolve() != server_root:
                        raise ValueError('Workspace database belongs to another world.')
            finally:
                snapshot.close()
                original.close()
            copied.append(name)
    for name in ('backups', 'revisions'):
        folder = source / name
        if folder.is_dir():
            if any(p.is_symlink() for p in folder.rglob('*')):
                raise ValueError('Linked backup files need a manual migration review.')
            shutil.copytree(folder, stage / name)
            for old in folder.rglob('*'):
                if old.is_file():
                    cloned = stage / name / old.relative_to(folder)
                    if hashlib.sha256(old.read_bytes()).digest() != hashlib.sha256(cloned.read_bytes()).digest():
                        raise ValueError('A source backup changed during import; retry with the old Studio stopped.')
            copied.append(name)
    legacy = []
    if hub_data:
        hub = Path(hub_data).resolve()
        clients = [server_root.parent / 'Klient']
        for marker in (hub / 'sandboxes').glob('*/hub-sandbox.json'):
            record = json.loads(marker.read_text('utf-8'))
            client = Path(record['client']).resolve()
            if client.is_relative_to(hub / 'sandboxes') and Path(record['server_root']).resolve() == server_root:
                clients.append(client)
        allowed = {hashlib.sha256(os.path.normcase(str(client.resolve())).encode('utf-8')).hexdigest()[:24] for client in clients}
        for target in sorted((hub / 'targets').glob('*')):
            # Read only metadata, never copy packs, baselines, keys or executables.
            state = target / 'state.json'
            history = target / 'history.jsonl'
            if target.name not in allowed or not state.is_file() or not history.is_file():
                continue
            for line in history.read_text('utf-8').splitlines():
                row = json.loads(line)
                backup = Path(row.get('backup_directory', '')).resolve()
                if not backup.is_relative_to(hub):
                    continue
                row.update(legacy=True, legacy_target=target.name)
                legacy.append(row)
        # Bind imported records explicitly to the selected migration world.
        atomic_json(stage / 'legacy-addon-history.json', {'server_root': str(server_root), 'items': legacy, 'source': str(hub)})
    # Both resolved paths are siblings in the explicitly selected state parent.
    if stage.parent != destination.parent or not stage.name.startswith(destination.name + '-import-'):
        raise ValueError('Invalid migration staging path.')
    retry_windows_lock(stage.rename, destination)
    save_settings(selected, settings_path)
    report = {'copied': copied, 'legacy_addon_events': len(legacy), 'source_studio_data': str(source),
              'destination': str(destination), 'source_retained': True}
    atomic_json(destination / 'migration.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-root', type=Path, required=True)
    parser.add_argument('--studio-data', type=Path, required=True)
    parser.add_argument('--hub-data', type=Path)
    parser.add_argument('--port', type=int, default=8780)
    args = parser.parse_args()
    print(json.dumps(import_existing(args.server_root, args.studio_data, args.hub_data, args.port), indent=2))
