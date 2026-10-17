"""Portable, local-only Studio setup. Never writes to the game installation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets

HERE = Path(__file__).resolve().parent
APPLICATION = 'metin2-server-studio'
SETTINGS_PATH = HERE / 'data/studio-settings.json'
ROOT_ENV = 'METIN2_STUDIO_SERVER_ROOT'
REQUIRED = (
    'VERSION', 'files/items.json', 'files/drop_tables.py', 'files/playerbot_names_en.tsv',
    'files/static/item_icons.json', 'linux-port/docker/.env.example',
    'linux-port/docker/game/Dockerfile', 'linux-port/docker/game/.dockerignore',
    'linux-port/docker/mariadb/initdb.d/dumps/world.sql',
    'linux-port/docker/game/share/locale/poland/mob_drop_item.txt',
    'linux-port/docker/game/share/locale/poland/special_item_group.txt',
    'linux-port/docker/game/share/locale/poland/cube.txt',
    'linux-port/docker/game/share-add/cube.seon_pyeong.txt',
)


def studio_version():
    path = HERE / 'VERSION'
    return path.read_text('utf-8').strip() if path.is_file() else 'development'


def load_settings(path=None):
    path = Path(path or SETTINGS_PATH)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text('utf-8-sig'))
        if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('serverRoot'), str):
            raise ValueError()
        port_number(data.get('port', 8765))
        if 'stateDir' in data and not isinstance(data['stateDir'], str):
            raise ValueError()
        return data
    except (ValueError, TypeError):
        raise ValueError('Studio settings are invalid. Run Install Studio.bat to configure the existing server again. Your game and Studio backups are retained.') from None


def port_number(value):
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit() or not 1024 <= int(value) <= 65535:
        raise ValueError('Choose a local port between 1024 and 65535.')
    return int(value)


def default_root(settings=None, environ=None):
    env = os.environ if environ is None else environ
    if env.get(ROOT_ENV):
        return Path(env[ROOT_ENV]).expanduser().resolve()
    saved = load_settings() if settings is None else settings
    value = env.get(ROOT_ENV) or saved.get('serverRoot')
    return Path(value).expanduser().resolve() if value else None


def server_root(value):
    selected = Path(str(value).strip().strip('"')).expanduser().resolve()
    candidates = (selected, selected / 'Serwer', selected / 'Metin2 Singleplayer/Serwer')
    root = next((p for p in candidates if (p / 'files/items.json').is_file()), selected)
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    compose = root / 'linux-port/docker'
    if not any((compose / name).is_file() for name in ('compose.yaml', 'compose.yml', 'docker-compose.yml', 'docker-compose.yaml')):
        missing.append('linux-port/docker/docker-compose.yml (or compose.yaml)')
    if missing:
        raise ValueError('Choose the Serwer folder of the supported Metin2 Singleplayer Linux/Docker package. Missing: ' + ', '.join(missing[:8]) + (f' and {len(missing)-8} more' if len(missing)>8 else '') + '.')
    return root


def world_state(root, base=None):
    identity = os.path.normcase(str(Path(root).resolve())).encode('utf-8')
    return Path(base or HERE / 'data') / 'worlds' / hashlib.sha256(identity).hexdigest()[:16]


def resolve_settings(root=None, port=None, state=None, saved=None, environ=None, base=None):
    if saved is None:
        try:
            saved = load_settings()
        except ValueError:
            if root or (os.environ if environ is None else environ).get(ROOT_ENV):
                saved = {}
            else:
                raise
    chosen = root or default_root(saved, environ)
    if not chosen:
        raise ValueError('Studio is not configured. Double-click Install Studio.bat and choose your existing Serwer folder, or run python server.py --root "path/to/Serwer".')
    root = server_root(chosen)
    same_world = bool(saved.get('serverRoot')) and Path(saved['serverRoot']).expanduser().resolve() == root
    state = Path(state or (saved.get('stateDir') if same_world else None) or world_state(root, base)).expanduser().resolve()
    if state == root or state.is_relative_to(root) or root.is_relative_to(state):
        raise ValueError('Keep Studio data outside the game installation and its parent folders. Choose a separate Studio data folder.')
    return {'schema': 1, 'application': APPLICATION, 'studioVersion': studio_version(), 'serverRoot': str(root),
            'serverVersion': (root / 'VERSION').read_text('utf-8-sig').strip(), 'stateDir': str(state),
            'port': port_number(port if port is not None else saved.get('port', 8765))}


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp-' + secrets.token_hex(5))
    try:
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', 'utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def bind_state(settings):
    state = Path(settings['stateDir'])
    binding = state / 'studio-world.json'
    if binding.exists():
        try:
            recorded = json.loads(binding.read_text('utf-8'))
            if Path(recorded['serverRoot']).resolve() != Path(settings['serverRoot']).resolve():
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise ValueError('This Studio data folder belongs to another server. Choose a separate --state folder; existing history and backups were retained.') from None
    else:
        atomic_json(binding, {'schema': 1, 'serverRoot': settings['serverRoot']})


def save_settings(settings, path=None):
    bind_state(settings)
    atomic_json(Path(path or SETTINGS_PATH), {key: settings[key] for key in ('schema', 'serverRoot', 'stateDir', 'port')})
