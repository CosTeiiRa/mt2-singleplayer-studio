"""Manage the world's normal client packs with reviewed, journalled writes."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from .client_pack import EterPack, digest
from .map_data import WorldData

PROJECT = Path(__file__).resolve().parent
BOOTSTRAP = b'''\n# M2HUB_BOOTSTRAP_V1 - generated from the current baseline\ntry:\n    import m2hub_runtime\n    m2hub_runtime.install(globals())\nexcept Exception:\n    import dbg\n    import traceback\n    dbg.TraceError("M2Hub startup: " + traceback.format_exc())\n'''
GAME_BOOTSTRAP = b'''\n# M2HUB_GAME_V2 - owned game lifecycle integration\ntry:\n    import m2hub_client\n    m2hub_client.install(globals())\nexcept Exception:\n    import dbg\n    import traceback\n    dbg.TraceError("M2Hub game integration: " + traceback.format_exc())\n'''


def normalized_client(path):
    path = Path(path).expanduser().resolve()
    if (path / 'root.index').is_file() and path.name.lower() == 'pack':
        path = path.parent
    if path.name.lower() == 'serwer' and (path.parent / 'Klient' / 'pack' / 'root.index').is_file():
        path = path.parent / 'Klient'
    if (path / 'Klient' / 'pack' / 'root.index').is_file():
        path = path / 'Klient'
    if not (path / 'pack' / 'root.index').is_file() or not (path / 'pack' / 'root.data').is_file():
        raise ValueError('Choose an existing Klient folder, its Serwer sibling, or their parent folder.')
    return path


def discover_installations():
    roots = [Path.home() / 'Saved Games', Path.home() / 'Metin2Server', Path('C:/Games')]
    found = []
    for parent in roots:
        if not parent.is_dir():
            continue
        candidates = [parent] + [p for p in parent.iterdir() if p.is_dir() and 'metin' in p.name.lower()]
        for candidate in candidates:
            for path in [candidate, candidate / 'Metin2 Singleplayer']:
                try:
                    client = normalized_client(path)
                    if str(client) not in found:
                        found.append(str(client))
                except (ValueError, OSError):
                    pass
    return found


def _version(path):
    try:
        return path.read_text('utf-8-sig').strip()[:80]
    except OSError:
        return 'unknown'


def recorded_profile(executable_hash):
    """Admit only an exact executable recorded in the bundled profile set.

    Version labels describe coverage; they never select or bypass a profile.
    Ambiguous or damaged records fail closed instead of trusting glob order.
    """
    if not isinstance(executable_hash, str) or len(executable_hash) != 64:
        return None
    matches = []
    for path in sorted((PROJECT / 'profiles').glob('*.json')):
        try:
            known = json.loads(path.read_text('utf-8'))
        except (OSError, ValueError):
            continue
        if (isinstance(known, dict) and known.get('schema_version') == 1
                and isinstance(known.get('id'), str) and known['id']
                and known.get('executable_sha256') == executable_hash):
            matches.append(known)
    return matches[0] if len(matches) == 1 else None


def _process_image(pid):
    """Query an image path without requiring access to process memory."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        if ctypes.get_last_error() == 87:  # The enumerated process already exited.
            return None
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.value
    finally:
        kernel.CloseHandle(handle)


def running_client(executable):
    if os.name != 'nt':
        return False
    script = """$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$clients=@(Get-Process -Name metin2client -ErrorAction SilentlyContinue | ForEach-Object {
    [PSCustomObject]@{pid=$_.Id;path=$_.Path}
})
ConvertTo-Json -InputObject $clients -Compress
"""
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, text=True, encoding='utf-8', timeout=10,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('Cannot check the running game client. Close Metin2 before applying add-ons.')
        processes = json.loads(result.stdout.strip() or '[]')
        if not isinstance(processes, list) or any(not isinstance(item, dict) or type(item.get('pid')) is not int
                or item['pid'] <= 0 or item.get('path') is not None and not isinstance(item['path'], str) for item in processes):
            raise ValueError('Cannot check the running game client. Close Metin2 before applying add-ons.')
        for item in processes:
            path = item.get('path') or _process_image(item['pid'])
            if path and Path(path).resolve() == Path(executable).resolve():
                return True
        return False
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        raise ValueError('Cannot check the running game client. Close Metin2 before applying add-ons.') from error


class ClientAdapter:
    def __init__(self, path, state_dir):
        self.target_root = normalized_client(path)
        self.state_dir = Path(state_dir).resolve()
        self.ident = hashlib.sha256(str(self.target_root).casefold().encode('utf-8')).hexdigest()[:20]
        self._lock = threading.RLock()
        self._pack = None
        self._pack_hash = None
        self.marker = None
        marker_path = self.target_root.parent / 'hub-sandbox.json'
        sandboxes = self.state_dir / 'sandboxes'
        playable = self.state_dir / 'playable-clients'
        if (self.target_root.is_relative_to(sandboxes) or self.target_root.is_relative_to(playable)) and marker_path.is_file():
            marker = json.loads(marker_path.read_text('utf-8'))
            expected_format = 'm2hub-pack-sandbox-v1' if self.target_root.is_relative_to(sandboxes) else 'm2hub-playable-copy-v1'
            if marker.get('format') == expected_format and marker.get('client') == str(self.target_root):
                self.marker = marker
        self.server_root = Path(self.marker['server_root']) if self.marker and self.marker.get('server_root') else self.target_root.parent / 'Serwer'
        self._world = None
        self.reference_provider = None
        self.reference_metadata = None
        executable = self.target_root / 'metin2client.exe'
        self._connected_executable_hash = digest(executable.read_bytes()) if executable.is_file() else None

    def physical_snapshot(self):
        return {'pack/root.index': (self.target_root / 'pack' / 'root.index').read_bytes(),
                'pack/root.data': (self.target_root / 'pack' / 'root.data').read_bytes()}

    def pack(self):
        with self._lock:
            physical = self.physical_snapshot()
            signature = tuple(digest(physical[n]) for n in sorted(physical))
            if signature != self._pack_hash:
                self._pack = EterPack.open(self.target_root / 'pack')
                self._pack_hash = signature
            return self._pack

    def world(self, refresh=False):
        if self._world is None or refresh:
            self._world = WorldData(self.server_root)
        return self._world

    def profile(self):
        physical = self.physical_snapshot()
        fingerprint = digest(b''.join(bytes.fromhex(digest(physical[n])) for n in sorted(physical)))
        executable = self.target_root / 'metin2client.exe'
        executable_hash = digest(executable.read_bytes()) if executable.is_file() else (self.marker or {}).get('source_executable_sha256')
        validation = recorded_profile(executable_hash)
        is_playable = bool(self.marker and self.marker.get('format') == 'm2hub-playable-copy-v1')
        normal_client = not self.marker and self.target_root == (self.server_root.parent / 'Klient').resolve()
        writable = bool(self.marker) and (not is_playable or bool(validation and executable_hash == self.marker.get('source_executable_sha256')))
        if normal_client:
            writable = bool(validation and executable_hash == self._connected_executable_hash)
        return {'id': self.ident, 'profile_id': validation['id'] if validation else None,
                'name': 'Playable add-on test copy' if is_playable else 'Disposable client-pack sandbox' if self.marker else 'Metin2 Singleplayer',
                'path': str(self.target_root), 'client_root': str(self.target_root), 'server_root': str(self.server_root),
                'client_version': _version(self.target_root / 'client.version'),
                'server_version': _version(self.server_root / 'VERSION'),
                'kind': 'test-client' if is_playable else 'sandbox' if self.marker else 'installation',
                'writable': writable,
                'fingerprint': fingerprint, 'details': {'integration': 'experimental',
                'runtime_validation': 'native startup/import/widgets smoke-tested; interactive gameplay pending' if validation else 'not validated against a recorded native-client profile',
                'validation': validation,
                'executable_sha256': executable_hash,
                'read_only_reason': None if writable else 'This client runtime is not validated for pack changes, or its executable changed. Reconnect after updating; the game itself can still be updated normally.',
                'sandbox_scope': 'Root client packs only; this is not a standalone runnable game' if self.marker else None}}

    def snapshot(self):
        return dict(self.pack().files())

    def check_writable(self):
        if not self.marker:
            if not self.profile()['writable']:
                raise ValueError('This game client runtime is not validated for pack changes. Update/reconnect the client and review integration support.')
            if running_client(self.target_root / 'metin2client.exe'):
                raise ValueError('Close this Metin2 game client before applying add-ons. The game server can stay running.')
            return
        if not self.marker or not any(self.target_root.is_relative_to(self.state_dir / name) for name in ('sandboxes', 'playable-clients')):
            raise ValueError('This testing target is outside the selected world’s owned testing folders.')
        marker_path = self.target_root.parent / 'hub-sandbox.json'
        if not marker_path.is_file() or json.loads(marker_path.read_text('utf-8')) != self.marker:
            raise ValueError('Sandbox identity changed. Reconnect and inspect it before applying anything.')
        playable = self.marker.get('format') == 'm2hub-playable-copy-v1'
        executable = self.target_root / 'metin2client.exe'
        if playable:
            if not executable.is_file() or digest(executable.read_bytes()) != self.marker.get('source_executable_sha256'):
                raise ValueError('The playable copy executable changed. Create a fresh test copy.')
            if self.profile()['profile_id'] is None:
                raise ValueError('Playable copies require a recorded executable profile.')
            if running_client(executable):
                raise ValueError('Close this Metin2 game client before applying add-ons. The game server can stay running.')
        if executable.exists() and not playable:
            raise ValueError('A runnable client was added to this pack sandbox. Applying is blocked until it is inspected.')

    def mutation_blockers(self):
        executable = self.target_root / 'metin2client.exe'
        if executable.is_file() and running_client(executable):
            return ['Close this Metin2 game client before applying add-ons. The game server can stay running.']
        return []

    @staticmethod
    def is_clean_game_baseline(files):
        owned = {'m2hub_config.py', 'm2hub_runtime.py', 'm2hub_client.py', 'm2hub_world.py', 'm2hub_reference.py'}
        return (bool(files.get('uiminimap.py')) and not any(name in owned or name.startswith('m2hub_addons/') for name in files)
                and b'M2HUB_BOOTSTRAP_V1' not in files.get('uiminimap.py', b'')
                and b'M2HUB_GAME_V2' not in files.get('game.py', b''))

    def preview(self, logical_files):
        """Pure logical rendering, also used by the review screen."""
        files = dict(logical_files)
        active = False
        addons = []
        self.reference_metadata = None
        if 'm2hub_config.py' in files:
            tree = ast.parse(files['m2hub_config.py'].decode('utf-8'))
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ADDONS' for t in node.targets):
                        addons = ast.literal_eval(node.value)
                        active = bool(addons)
        if active:
            source = files.get('uiminimap.py')
            if not source or b'class AtlasWindow(' not in source or b'def OnUpdate(self)' not in source or b'def SetMapName(self, mapName)' not in source:
                raise ValueError('This client map module does not match the tested structural profile.')
            if b'M2HUB_BOOTSTRAP_V1' in source:
                raise ValueError('The baseline already contains an Add-on Hub bootstrap. Review its provenance first.')
            files['uiminimap.py'] = source.rstrip() + b'\n' + BOOTSTRAP
            files['m2hub_runtime.py'] = (PROJECT / 'runtime' / 'm2hub_runtime.py').read_bytes()
            data = {name.lower(): value for name, value in self.world(refresh=True).runtime_data().items()}
            files['m2hub_world.py'] = ('# -*- coding: utf-8 -*-\n# Generated locally from installed spawn configuration.\nWORLD = ' + ascii(data) + '\n').encode('ascii')
            files.setdefault('m2hub_addons/__init__.py', b'# Add-on Hub namespace\n')
            if any(item.get('api_version', 1) >= 2 for item in addons):
                game = files.get('game.py')
                if not game or any(token not in game for token in (b'class GameWindow(', b'def Open(self)', b'def Close(self)', b'def OnKeyDown(self, key)')):
                    raise ValueError('This client does not match the supported standalone-window profile.')
                if b'M2HUB_GAME_V2' in game:
                    raise ValueError('The baseline already contains a game lifecycle bootstrap.')
                files['game.py'] = game.rstrip() + b'\n' + GAME_BOOTSTRAP
                files['m2hub_client.py'] = (PROJECT / 'runtime/m2hub_client.py').read_bytes()
                # World-bound preferences remain stable across data/code updates.
                namespace = hashlib.sha256(str(self.server_root.resolve()).casefold().encode('utf-8')).hexdigest()[:32]
                files['m2hub_config.py'] += ('\nSTATE_NAMESPACE = %r\n' % namespace).encode('ascii')
            if any('knowledge.read' in item.get('capabilities', []) for item in addons):
                if not callable(self.reference_provider):
                    raise ValueError('Reference data requires the merged Studio world service.')
                reference = self.reference_provider()
                from .knowledge import encoded
                raw = encoded(reference).decode('ascii')
                files['m2hub_reference.py'] = ('# Locally generated reference data.\nJSON = u%r\n' % raw).encode('ascii')
                self.reference_metadata = {key: reference['meta'][key] for key in ('snapshot', 'server_version', 'generated_at', 'native_crafting', 'warnings')}
                self.reference_metadata['counts'] = {key: len(reference[key]) for key in ('items', 'recipes', 'upgrades', 'origins')}
        return files

    def prepare(self, logical_files, staging_dir):
        self.check_writable()
        original = self.pack()
        files = self.preview(logical_files)
        cache = self.state_dir / 'adapter-cache' / self.ident
        cache.mkdir(parents=True, exist_ok=True)
        if not (cache / 'root.index').exists():
            # A private source snapshot, not a game modification or distributed asset.
            (cache / 'root.index').write_bytes(original.index_bytes)
            (cache / 'root.data').write_bytes(original.data_bytes)
            (cache / 'config.json').write_text(json.dumps(original.config), encoding='utf-8')
        baseline = EterPack((cache / 'root.index').read_bytes(), (cache / 'root.data').read_bytes(),
                            json.loads((cache / 'config.json').read_text('utf-8')))
        if 'm2hub_config.py' not in files and files == baseline.files():
            return {'pack/root.index': baseline.index_bytes, 'pack/root.data': baseline.data_bytes}
        index, data = original.build(files)
        check = EterPack(index, data, original.config)
        if set(check.entries) != set(files) or any(check.read(name) != raw for name, raw in files.items()):
            raise ValueError('Rebuilt pack did not pass entry-by-entry verification.')
        return {'pack/root.index': index, 'pack/root.data': data}


def create_sandbox(source_path, state_dir):
    source = normalized_client(source_path)
    state_dir = Path(state_dir).resolve()
    destination = state_dir / 'sandboxes' / uuid.uuid4().hex[:12]
    client = destination / 'Klient'
    pack = client / 'pack'
    pack.mkdir(parents=True)
    for name in ('root.index', 'root.data', 'root.json', 'PackMakerLite.json'):
        path = source / 'pack' / name
        if path.is_file():
            shutil.copyfile(path, pack / name)
    (client / 'client.version').write_text(_version(source / 'client.version'), encoding='utf-8')
    source_marker = source.parent / 'hub-sandbox.json'
    source_server = source.parent / 'Serwer'
    if source_marker.is_file() and source.is_relative_to(state_dir / 'sandboxes'):
        source_server = Path(json.loads(source_marker.read_text('utf-8'))['server_root'])
    source_exe = source / 'metin2client.exe'
    source_exe_hash = digest(source_exe.read_bytes()) if source_exe.is_file() else None
    if source_marker.is_file() and source.is_relative_to(state_dir / 'sandboxes'):
        source_exe_hash = json.loads(source_marker.read_text('utf-8')).get('source_executable_sha256')
    marker = {'format': 'm2hub-pack-sandbox-v1', 'client': str(client), 'source_client': str(source), 'server_root': str(source_server),
              'source_executable_sha256': source_exe_hash}
    (destination / 'hub-sandbox.json').write_text(json.dumps(marker, indent=2), encoding='utf-8')
    return client


def create_playable_copy(source_path, state_dir):
    """Copy a known client into an owned runnable test target; never execute it."""
    source = normalized_client(source_path)
    state_dir = Path(state_dir).resolve()
    executable = source / 'metin2client.exe'
    if not executable.is_file():
        raise ValueError('A playable copy needs the installed client executable.')
    executable_hash = digest(executable.read_bytes())
    if not recorded_profile(executable_hash):
        raise ValueError('This executable has no recorded profile for a playable test copy.')
    files = []
    for folder in ('pack', 'lib', 'miles', 'BGM', 'locale', 'uiscript'):
        base = source / folder
        if not base.is_dir():
            continue
        for path in [base, *base.rglob('*')]:
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                raise ValueError('Linked client assets cannot be copied into an owned test target.')
            if path.is_file():
                files.append(path)
    files.extend(path for path in source.iterdir() if path.is_file() and
                 (path.suffix.lower() == '.dll' or path.name in ('metin2client.exe', 'client.version', 'game1.cfg', 'FPS.cfg', 'channel.inf', 'mouse.cfg')))
    if any(path.is_symlink() for path in files):
        raise ValueError('Linked client files are unsupported.')
    total = sum(path.stat().st_size for path in files)
    state_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(state_dir).free < total + 256 * 1024 * 1024:
        raise ValueError('Not enough free disk space to copy the client and rebuild packs.')
    original = {name: digest((source / 'pack' / name).read_bytes()) for name in ('root.index', 'root.data')}
    destination = state_dir / 'playable-clients' / uuid.uuid4().hex[:12]
    client = destination / 'Klient'
    client.mkdir(parents=True, exist_ok=False)
    for path in files:
        target = client / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    if any(digest((source / 'pack' / name).read_bytes()) != value or digest((client / 'pack' / name).read_bytes()) != value
           for name, value in original.items()) or digest((client / 'metin2client.exe').read_bytes()) != executable_hash:
        raise ValueError('The source changed while copying. This incomplete target was not registered.')
    marker = {'format': 'm2hub-playable-copy-v1', 'client': str(client), 'source_client': str(source),
              'server_root': str(source.parent / 'Serwer'), 'source_executable_sha256': executable_hash,
              'source_pack_hashes': original}
    (destination / 'hub-sandbox.json').write_text(json.dumps(marker, indent=2), encoding='utf-8')
    return client
