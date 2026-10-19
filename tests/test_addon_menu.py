"""In-game launcher API, widget lifecycle and ordinary package transactions."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from addonhub import client_pack as codec

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class LauncherApiTests(unittest.TestCase):
    def setUp(self):
        self.client = module('menu_client', 'addonhub/runtime/m2hub_client.py')
        self.events = []
        self.records = [dict(id=ident, name=name, enabled=enabled, capabilities=caps) for ident, name, enabled, caps in
                        [('menu', 'Add-on Menu', True, []), ('wiki', 'Pocket Wiki', True, []),
                         ('atlas', 'Boss Atlas', True, ['atlas.overlay']), ('disabled', 'Disabled', False, []),
                         ('automatic', 'Automatic', True, []), ('broken', 'Broken', True, [])]]
        host = SimpleNamespace(_contexts=[SimpleNamespace(id=ident) for ident in ('menu', 'wiki', 'atlas', 'automatic')], _log=self.events.append)
        self.enterContext(patch.dict(sys.modules, {'m2hub_config': SimpleNamespace(ADDONS=[], INSTALLED_ADDONS=self.records), 'm2hub_runtime': host}))
        self.atlas_shown = False
        minimap = SimpleNamespace(ShowAtlas=self.show_atlas, AtlasWindow=SimpleNamespace(IsShow=lambda: self.atlas_shown))
        self.client._game = SimpleNamespace(interface=SimpleNamespace(wndMiniMap=minimap))

    def show_atlas(self):
        self.atlas_shown = True

    def test_enumeration_distinguishes_disabled_failed_and_automatic_addons(self):
        rows = {row['id']: row for row in self.client.addons()}
        self.assertEqual(rows['disabled']['status'], 'Disabled')
        self.assertFalse(rows['disabled']['actions'])
        self.assertEqual(rows['broken']['status'], 'Failed to load')
        self.assertEqual(rows['automatic']['status'], 'Runs automatically')
        self.assertEqual(rows['atlas']['actions'][0]['id'], 'atlas')
        rows['atlas']['name'] = 'Changed display copy'
        self.assertEqual(self.records[2]['name'], 'Boss Atlas')
        self.assertFalse(self.client.open_addon('disabled'))
        self.assertFalse(self.client.open_addon('broken'))
        self.assertFalse(self.client.open_addon('missing'))

    def test_open_raises_existing_window_instead_of_closing_it(self):
        class Window:
            shown = False
            def IsShow(inner): return inner.shown
            def Open(inner): inner.shown = True; self.events.append('open')
            def Close(inner): inner.shown = False; self.events.append('close')
            def SetTop(inner): self.events.append('top')
            def Destroy(inner): self.events.append('destroy')
        handle = self.client.register_window(SimpleNamespace(id='wiki'), 'wiki', lambda game: Window(), 'CTRL_U')
        self.assertTrue(self.client.open_addon('wiki'))
        self.assertTrue(self.client.open_addon('wiki', 'window:wiki'))
        self.assertEqual(self.events, ['open', 'top'])
        self.assertTrue(handle.toggle())
        self.assertEqual(self.events[-1], 'close')
        self.assertTrue(self.client.open_addon('atlas'))
        self.assertTrue(self.atlas_shown)
        self.client._game = None
        self.assertFalse(self.client.open_addon('wiki'))

    def test_failed_window_is_disabled_without_breaking_other_actions(self):
        def broken(game): raise ValueError('factory failure')
        self.client.register_window(SimpleNamespace(id='wiki'), 'wiki', broken, 'NONE')
        self.assertFalse(self.client.open_addon('wiki'))
        row = next(row for row in self.client.addons() if row['id'] == 'wiki')
        self.assertEqual(row['status'], 'Window unavailable')
        self.assertFalse(row['actions'][0]['available'])
        self.assertTrue(self.client.open_addon('atlas'))
        self.assertTrue(any('factory failure' in event for event in self.events))

    def test_api_v1_stays_guarded_and_api_v2_delegates_launcher_operations(self):
        host = module('menu_host', 'addonhub/runtime/m2hub_runtime.py')
        with patch.dict(sys.modules, {'m2hub_client': self.client}):
            with self.assertRaisesRegex(ValueError, 'API v2'):
                host.Context('legacy', {}).addons()
            context = host.Context('menu', {}, 2)
            self.assertEqual(len(context.addons()), len(self.records))
            self.assertTrue(context.open_addon('atlas'))


class Widget:
    def __init__(self): self.shown = False; self.width = self.height = 0; self.x = self.y = 0; self.text = ''
    def SetParent(self, parent): self.parent = parent
    def AddFlag(self, value): pass
    def SetPosition(self, x, y): self.x, self.y = x, y
    def GetGlobalPosition(self): return self.x, self.y
    def SetSize(self, width, height): self.width, self.height = width, height
    def GetWidth(self): return self.width
    def GetHeight(self): return self.height
    def SetTitleName(self, value): self.title = value
    def SetCloseEvent(self, event): self.close_event = event
    def SetColor(self, value): pass
    def SetPackedFontColor(self, value): pass
    def SetText(self, value): self.text = value
    def GetTextSize(self): return len(self.text) * 6, 12
    def SetTop(self): pass
    def Show(self): self.shown = True
    def Hide(self): self.shown = False
    def IsShow(self): return self.shown


class MenuWidgetTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(sys.modules, {'ui': SimpleNamespace(Bar=Widget, TextLine=Widget, BoardWithTitleBar=Widget),
                          'wndMgr': SimpleNamespace(GetScreenWidth=lambda: 640, GetScreenHeight=lambda: 480)}))
        self.payload = module('menu_widgets', 'addonhub/catalog/community.addon-menu/payload/addon_menu.py')
        self.rows = [dict(id=ident, name=name, status='Enabled', enabled=True,
                         actions=[dict(id='window:' + ident, label='Window', shortcut='NONE', available=True)])
                     for ident, name in [('other', 'A first-sorting add-on'), ('menu', 'Add-on Menu')] + [('extra%d' % i, 'Extra %d' % i) for i in range(8)]]
        self.opened = []
        self.context = SimpleNamespace(id='menu', addons=lambda: copy.deepcopy(self.rows),
                                      open_addon=lambda ident, action: self.opened.append((ident, action)) or True)
        self.menu = self.payload.Menu(self.context, Widget())

    def test_menu_is_first_paged_and_opens_other_addons_then_closes(self):
        self.menu.Open()
        names = [widget.text for widget in self.menu.widgets if isinstance(widget, Widget) and widget.text]
        self.assertEqual(names[1], 'Add-on Menu')
        self.assertLess(self.menu.GetWidth(), 640)
        self.assertLess(self.menu.GetHeight(), 480)
        self.menu.TurnPage(100)
        self.assertGreater(self.menu.page, 0)
        self.menu.TurnPage(-100)
        self.assertEqual(self.menu.page, 0)
        self.menu.Activate('menu', 'window:menu')
        self.assertTrue(self.menu.IsShow())
        self.menu.Activate('other', 'window:other')
        self.assertFalse(self.menu.IsShow())
        self.assertEqual(self.opened[-1], ('other', 'window:other'))
        self.menu.Open()
        self.assertTrue(self.menu.OnPressEscapeKey())
        self.assertFalse(self.menu.IsShow())

    def test_disabled_addon_has_no_open_callback_and_destroy_cleans_widgets(self):
        self.rows = [dict(id='disabled', name='Disabled', status='Disabled', enabled=False, actions=[])]
        self.menu.Open()
        actions = [widget for widget in self.menu.widgets if isinstance(widget, self.payload.Action)]
        self.assertEqual(actions[0].label.text, 'Disabled')
        actions[0].OnMouseLeftButtonUp()
        self.assertFalse(self.opened)
        self.menu.Destroy()
        self.assertFalse(self.menu.widgets)
        self.assertTrue(all(widget.event is None for widget in actions))

    def test_registration_creates_and_removes_the_button_on_game_lifecycle(self):
        events, toggles = {}, []
        class Handle:
            def toggle(self): toggles.append(True)
        context = SimpleNamespace(register_window=lambda name, factory: Handle(),
                                  on=lambda event, callback: events.update({event: callback}), log=lambda message: None)
        self.payload.register(context)
        launcher = events['game.open'].__self__
        events['game.open'](Widget())
        self.assertEqual(launcher.button.label.text, 'Add-ons')
        launcher.button.OnMouseLeftButtonUp()
        self.assertEqual(toggles, [True])
        button = launcher.button
        events['game.close'](Widget())
        self.assertIsNone(launcher.button)
        self.assertFalse(button.IsShow())
        self.assertIsNone(button.event)


@unittest.skipIf(codec.lzokay is None, 'Optional pack codec required')
class MenuIntegrationTests(unittest.TestCase):
    def test_menu_is_first_and_installs_disables_removes_as_an_ordinary_addon(self):
        from test_addon_integration import make_world
        with tempfile.TemporaryDirectory(dir=ROOT / '.test-tmp') as temporary:
            studio, client = make_world(Path(temporary))
            pack = codec.EterPack.open(client / 'pack')
            files = pack.files()
            files['game.py'] = b'class GameWindow(object):\n def Open(self): pass\n def Close(self): pass\n def OnKeyDown(self, key): pass\n'
            index, data = pack.build(files)
            (client / 'pack/root.index').write_bytes(index)
            (client / 'pack/root.data').write_bytes(data)
            service = studio.addons
            target = Path(service.post('sandbox', {})['path'])
            def apply(ident, action='install'):
                plan = service.post('plan', {'addon_id': ident, 'action': action})['plan']
                self.assertTrue(plan['can_apply'], plan['conflicts'])
                service.post('apply', {'plan_id': plan['id']})
            self.assertEqual(service.get('catalog', {})['catalog']['items'][0]['id'], 'community.addon-menu')
            apply('community.boss-atlas')
            apply('community.addon-menu')
            apply('community.boss-atlas', 'disable')
            current = codec.EterPack.open(target / 'pack').files()
            configuration = {}
            exec(current['m2hub_config.py'], configuration)
            self.assertEqual(configuration['ADDONS'][0]['id'], 'community.addon-menu')
            self.assertEqual(len(configuration['INSTALLED_ADDONS']), 2)
            self.assertFalse(next(item for item in configuration['INSTALLED_ADDONS'] if item['id'] == 'community.boss-atlas')['enabled'])
            self.assertIn(b'M2HUB_GAME_V2', current['game.py'])
            self.assertEqual(service.state()['installed'][0]['id'], 'community.addon-menu')
            apply('community.boss-atlas', 'enable')
            apply('community.addon-menu', 'disable')
            self.assertNotIn('m2hub_client.py', codec.EterPack.open(target / 'pack').files())
            apply('community.addon-menu', 'enable')
            apply('community.addon-menu', 'remove')
            self.assertEqual(len(service.state()['installed']), 1)
            apply('community.boss-atlas', 'remove')
            self.assertEqual((target / 'pack/root.index').read_bytes(), index)
            self.assertEqual((target / 'pack/root.data').read_bytes(), data)
