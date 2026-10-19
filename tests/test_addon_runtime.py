import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.addon import scaffold
from metin2_studio.addons.hubcore.packages import load_package

PROJECT = Path(__file__).resolve().parents[1]


def runtime():
    spec = importlib.util.spec_from_file_location('test_hub_runtime', PROJECT / 'src/metin2_studio/addons' / 'runtime' / 'm2hub_runtime.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeTests(unittest.TestCase):
    def test_creator_scaffold_registers_and_handles_map_changes_and_settings(self):
        scratch = PROJECT / '.test-tmp'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            path = Path(temporary) / 'creator'
            scaffold('fixture.runtime', 'Runtime fixture', 'Fixture creator', path)
            package = load_package(path)
        for enabled in (True, False):
            host, messages = runtime(), []
            class Atlas:
                def OnUpdate(self): return 42
                def Destroy(self): pass
                def SetMapName(self, name): self.mapName = name
            addons = [{'id': 'fixture.runtime', 'entry': package.manifest['entry'], 'settings': {'log_map_changes': enabled}}]
            with patch.dict(sys.modules, {'m2hub_config': types.SimpleNamespace(ADDONS=addons)}), patch.object(host, '_source', return_value=(next(iter(package.files.values())), 'original-fixture.py')), patch.object(host, '_log', messages.append):
                host.install({'AtlasWindow': Atlas})
                atlas = Atlas()
                atlas.SetMapName('first_map')
                self.assertEqual(atlas.OnUpdate(), 42)
                atlas.OnUpdate()
                atlas.SetMapName('second_map')
                atlas.OnUpdate()
                atlas.Destroy()
                atlas.OnUpdate()
            self.assertEqual(sum('Atlas map changed:' in message for message in messages), 3 if enabled else 0)
            self.assertTrue(any('Registered' in message for message in messages))

    def test_shared_hook_preserves_original_and_isolates_failures(self):
        host = runtime()
        events = []
        class Atlas:
            def OnUpdate(self): events.append('original'); return 42
            def Destroy(self): events.append('destroy')
            def SetMapName(self, name): self.mapName = name
        first = host.Context('first', {})
        second = host.Context('second', {})
        first.on('atlas.update', lambda atlas: events.append('first'))
        second.on('atlas.update', lambda atlas: events.append('second'))
        with patch.dict(sys.modules, {'m2hub_config': types.SimpleNamespace(ADDONS=[])}):
            host.install({'AtlasWindow': Atlas})
            host.install({'AtlasWindow': Atlas})
        self.assertEqual(Atlas().OnUpdate(), 42)
        self.assertEqual(events, ['original', 'first', 'second'])
        def broken(atlas): raise RuntimeError('failure')
        first.on('atlas.update', broken)
        Atlas().OnUpdate()
        self.assertFalse(any(callback is broken for _, callback in host._listeners['atlas.update']))
        self.assertIn('second', events)

    def test_original_exception_is_not_swallowed(self):
        host = runtime()
        class Atlas:
            def OnUpdate(self): raise ValueError('original error')
            def Destroy(self): pass
            def SetMapName(self, name): pass
        with patch.dict(sys.modules, {'m2hub_config': types.SimpleNamespace(ADDONS=[])}):
            host.install({'AtlasWindow': Atlas})
        with self.assertRaisesRegex(ValueError, 'original error'):
            Atlas().OnUpdate()

    def test_bad_entry_cannot_load_outside_namespace(self):
        host = runtime()
        for name in ('os', 'm2hub_addons...escape', 'm2hub_addons.bad/path'):
            with self.assertRaises(ValueError):
                host._load(name)
