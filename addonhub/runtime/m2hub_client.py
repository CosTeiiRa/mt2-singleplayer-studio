# -*- coding: utf-8 -*-
"""API v2 services for the supported embedded Python 2.7 client.

Game methods are wrapped once by the host. Add-ons own their widgets and
never patch the shared game interface. No HTTP/database access happens here.
"""
import json
import os
import re
import sys

_reference = None
_windows = {}
_game = None


def _log(message):
    import m2hub_runtime
    m2hub_runtime._log(message)


def reference():
    global _reference
    if _reference is None:
        import m2hub_reference
        if len(m2hub_reference.JSON) > 24 * 1024 * 1024:
            raise ValueError('Reference data exceeds its size limit')
        data = json.loads(m2hub_reference.JSON)
        if data.get('schema_version') != 1:
            raise ValueError('Unsupported reference data schema')
        _reference = data
    return _reference


def _state_path(ident):
    if not re.match(r'^[a-z][a-z0-9_.-]{0,127}$', ident):
        raise ValueError('Invalid add-on state id')
    import m2hub_config
    scope = getattr(m2hub_config, 'STATE_NAMESPACE', '')
    if not re.match(r'^[0-9a-f]{32}$', scope):
        raise ValueError('Missing world-local state namespace')
    root = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    return os.path.join(root, 'Metin2Studio', 'addon-preferences', scope, ident + '.json')


def load_state(ident):
    path = _state_path(ident)
    for candidate in (path, path + '.bak'):
        try:
            with open(candidate, 'rb') as stream:
                raw = stream.read(32769)
            if len(raw) > 32768:
                continue
            try:
                decoded = raw.decode('utf-8')
            except LookupError:
                decoded = u''.join(unichr(number) for number in bytearray(raw))
            value = json.loads(decoded)
            if isinstance(value, dict):
                return value
        except (IOError, OSError, ValueError, UnicodeError):
            pass
    return {}


def save_state(ident, value):
    if not isinstance(value, dict):
        raise ValueError('Local preferences must be an object')
    raw = json.dumps(value, ensure_ascii=True, allow_nan=False)
    # This embedded interpreter has no registered encodings, including ASCII.
    raw = ''.join(chr(ord(char)) for char in raw) if sys.version_info[0] < 3 else raw.encode('ascii')
    if len(raw) > 32768:
        raise ValueError('Local preferences exceed 32 KiB')
    path = _state_path(ident)
    directory = os.path.dirname(path)
    try:
        if not os.path.isdir(directory):
            os.makedirs(directory)
        with open(path + '.tmp', 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Keep a complete previous generation for interrupted Windows renames.
        if os.path.exists(path):
            if os.path.exists(path + '.bak'):
                os.remove(path + '.bak')
            os.rename(path, path + '.bak')
        os.rename(path + '.tmp', path)
        return True
    except (IOError, OSError) as exc:
        _log(ident + ' preferences were not saved: ' + repr(exc))
        return False


class WindowHandle(object):
    def __init__(self, context, name, factory, shortcut):
        self.context, self.name, self.factory = context, name, factory
        self.shortcut, self.window, self.failed = shortcut, None, False

    def toggle(self):
        return self._activate(True)

    def open(self):
        return self._activate(False)

    def _activate(self, toggle):
        if _game is None or self.failed:
            return False
        try:
            if self.window is None:
                self.window = self.factory(_game)
            if self.window.IsShow():
                if toggle:
                    self.window.Close()
                elif hasattr(self.window, 'SetTop'):
                    self.window.SetTop()
            else:
                self.window.Open()
            return True
        except Exception as exc:
            self.failed = True
            self.dispose()
            import traceback
            _log(self.context.id + ' window disabled: ' + traceback.format_exc())
            return False

    def dispose(self):
        window, self.window = self.window, None
        if window:
            try:
                window.Destroy()
            except Exception as exc:
                _log(self.context.id + ' cleanup: ' + repr(exc))


def register_window(context, name, factory, shortcut):
    if not re.match(r'^[a-z][a-z0-9_-]{0,63}$', name) or not callable(factory):
        raise ValueError('Invalid window registration')
    if shortcut not in ('CTRL_U', 'F12', 'NONE'):
        raise ValueError('Unsupported shortcut')
    key = (context.id, name)
    if key in _windows:
        raise ValueError('Window already registered')
    if shortcut != 'NONE' and any(value.shortcut == shortcut for value in _windows.values()):
        raise ValueError('Add-on shortcut is already registered')
    handle = WindowHandle(context, name, factory, shortcut)
    _windows[key] = handle
    return handle


def unregister(ident):
    for key in list(_windows):
        if key[0] == ident:
            _windows.pop(key).dispose()


def addons():
    """Read-only installed metadata and registered actions for in-game launchers."""
    import m2hub_config
    import m2hub_runtime
    loaded = set(context.id for context in m2hub_runtime._contexts)
    records = getattr(m2hub_config, 'INSTALLED_ADDONS', m2hub_config.ADDONS)
    result = []
    for item in records:
        ident = item['id']
        enabled = bool(item.get('enabled', True))
        status = 'Disabled' if not enabled else 'Enabled' if ident in loaded else 'Failed to load'
        actions = []
        if enabled and ident in loaded:
            for key, handle in sorted(_windows.items()):
                if key[0] == ident:
                    actions.append({'id': 'window:' + key[1], 'label': key[1].replace('_', ' ').title(),
                                    'shortcut': handle.shortcut, 'available': not handle.failed})
            if not actions and 'atlas.overlay' in item.get('capabilities', []):
                actions.append({'id': 'atlas', 'label': 'Open atlas', 'shortcut': 'M', 'available': True})
            if actions and not any(action['available'] for action in actions):
                status = 'Window unavailable'
            elif not actions:
                status = 'Runs automatically'
        result.append({'id': ident, 'name': item.get('name', ident), 'version': item.get('version', ''),
                       'enabled': enabled, 'status': status, 'actions': actions})
    return result


def open_addon(ident, action=None):
    """Open an enabled extension without toggling an already visible window shut."""
    if _game is None:
        return False
    item = next((value for value in addons() if value['id'] == ident), None)
    if not item or not item['enabled']:
        return False
    choices = [value for value in item['actions'] if value['available'] and (action is None or value['id'] == action)]
    if not choices:
        return False
    selected = choices[0]['id']
    if selected.startswith('window:'):
        return _windows[(ident, selected[7:])].open()
    if selected == 'atlas':
        minimap = getattr(getattr(_game, 'interface', None), 'wndMiniMap', None)
        if minimap and hasattr(minimap, 'ShowAtlas'):
            try:
                minimap.ShowAtlas()
                atlas = getattr(minimap, 'AtlasWindow', None)
                return bool(atlas and atlas.IsShow())
            except Exception as exc:
                _log(ident + ' atlas could not open: ' + repr(exc))
    return False


def open_native_item(game, ident):
    interface = getattr(game, 'interface', None)
    if not interface or not hasattr(interface, 'MakeWiki'):
        return False
    try:
        if interface.MakeWiki():
            interface.wndWiki.ShowItemInfo(int(ident), 0)
            interface.wndWiki.Open()
            return True
    except Exception as exc:
        _log('Native wiki link unavailable: ' + repr(exc))
    return False


def _key(game, key):
    import app
    # Respect built-in key registrations and focused text-entry windows.
    for field in ('onPressKeyDict', 'onClickKeyDict'):
        if key in getattr(game, field, {}):
            return False
    focused = getattr(game, '_GameWindow__ChannelInputFocused', None)
    if focused and focused():
        return False
    try:
        import ime
        if hasattr(ime, 'IsCaptureInput') and ime.IsCaptureInput():
            return False
    except ImportError:
        pass
    control = app.IsPressed(app.DIK_LCONTROL) or app.IsPressed(app.DIK_RCONTROL)
    shortcut = 'CTRL_U' if control and key == app.DIK_U else 'F12' if key == app.DIK_F12 else None
    for handle in list(_windows.values()):
        if shortcut and handle.shortcut == shortcut:
            return handle.toggle()
    return False


def install(namespace):
    cls = namespace['GameWindow']
    if getattr(cls, '_m2hub_v2', False):
        return
    import m2hub_runtime
    original_open, original_close, original_key = cls.Open, cls.Close, cls.OnKeyDown

    def opened(instance, *args, **kwargs):
        global _game
        result = original_open(instance, *args, **kwargs)
        _game = instance
        for handle in _windows.values():
            handle.failed = False
        m2hub_runtime._emit('game.open', instance)
        return result

    def closed(instance, *args, **kwargs):
        global _game
        m2hub_runtime._emit('game.close', instance)
        for handle in list(_windows.values()):
            handle.dispose()
        _game = None
        return original_close(instance, *args, **kwargs)

    def key_down(instance, key):
        try:
            if _key(instance, key):
                return True
        except Exception as exc:
            _log('Add-on shortcut: ' + repr(exc))
        return original_key(instance, key)

    cls.Open, cls.Close, cls.OnKeyDown = opened, closed, key_down
    cls._m2hub_v2 = True
