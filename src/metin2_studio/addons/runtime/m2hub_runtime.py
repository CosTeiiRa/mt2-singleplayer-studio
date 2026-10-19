# -*- coding: utf-8 -*-
"""Small Python 2.7/3 compatible client extension host.

Loaded once at the end of uiMiniMap. Original callbacks always run first.
Add-ons are trusted client code, not a security sandbox.
"""
import sys
import types

_listeners = {}
_contexts = []
_installed = False


def _log(message):
    try:
        import dbg
        dbg.TraceError('M2Hub: ' + str(message))
    except Exception:
        pass


def _source(name):
    path = name.replace('.', '/') + '.py'
    try:
        import pack
        if pack.Exist(path):
            return pack.Get(path), path
    except ImportError:
        pass
    with open(path, 'rb') as stream:
        return stream.read(), path


def _load(name):
    if not name.startswith('m2hub_addons.') or any(not p.replace('_', '').isalnum() for p in name.split('.')):
        raise ValueError('Invalid add-on module name')
    if name in sys.modules:
        return sys.modules[name]
    if 'm2hub_addons' not in sys.modules:
        namespace = types.ModuleType('m2hub_addons')
        namespace.__path__ = []
        sys.modules['m2hub_addons'] = namespace
    source, path = _source(name)
    module = types.ModuleType(name)
    module.__file__ = path
    sys.modules[name] = module
    try:
        eval(compile(source, path, 'exec'), module.__dict__)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


class Context(object):
    def __init__(self, ident, settings, api_version=1):
        self.id = ident
        self.settings = settings
        self.api_version = api_version

    def on(self, event, callback):
        allowed = ('atlas.update', 'atlas.destroy', 'atlas.map')
        if self.api_version >= 2:
            allowed += ('game.open', 'game.close')
        if event not in allowed:
            raise ValueError('Unknown map event')
        _listeners.setdefault(event, []).append((self.id, callback))

    def log(self, message):
        _log(self.id + ': ' + str(message))

    def world(self, name):
        import m2hub_world
        return m2hub_world.WORLD.get(str(name).lower())

    def _v2(self):
        if self.api_version < 2:
            raise ValueError('This operation requires client API v2')
        import m2hub_client
        return m2hub_client

    def reference(self):
        return self._v2().reference()

    def module(self, name):
        self._v2()
        return _load(name)

    def load_state(self):
        return self._v2().load_state(self.id)

    def save_state(self, value):
        return self._v2().save_state(self.id, value)

    def register_window(self, name, factory, shortcut='NONE'):
        return self._v2().register_window(self, name, factory, shortcut)

    def addons(self):
        return self._v2().addons()

    def open_addon(self, ident, action=None):
        return self._v2().open_addon(ident, action)

    def open_native_item(self, game, ident):
        return self._v2().open_native_item(game, ident)


def _emit(event, instance):
    for ident, callback in list(_listeners.get(event, [])):
        try:
            callback(instance)
        except Exception as exc:
            _log(ident + ' callback disabled: ' + repr(exc))
            _listeners[event] = [(i, c) for i, c in _listeners[event] if c is not callback]


def _wrap(cls, method, event):
    original = getattr(cls, method)
    if getattr(original, '_m2hub_wrapped', False):
        return
    def wrapped(instance, *args, **kwargs):
        if event == 'atlas.destroy':
            _emit(event, instance)
        result = original(instance, *args, **kwargs)
        if event != 'atlas.destroy':
            _emit(event, instance)
        return result
    wrapped._m2hub_wrapped = True
    wrapped._m2hub_original = original
    setattr(cls, method, wrapped)


def install(namespace):
    global _installed
    if _installed:
        return
    from m2hub_config import ADDONS
    atlas = namespace['AtlasWindow']
    _wrap(atlas, 'OnUpdate', 'atlas.update')
    _wrap(atlas, 'Destroy', 'atlas.destroy')
    _wrap(atlas, 'SetMapName', 'atlas.map')
    _installed = True
    for item in ADDONS:
        ident = item['id']
        try:
            context = Context(ident, item.get('settings', {}), item.get('api_version', 1))
            _load(item['entry']).register(context)
            _contexts.append(context)
        except Exception as exc:
            if item.get('api_version', 1) >= 2:
                import m2hub_client
                m2hub_client.unregister(ident)
            for event in _listeners:
                _listeners[event] = [(i, c) for i, c in _listeners[event] if i != ident]
            _log(ident + ' failed to load: ' + repr(exc))
