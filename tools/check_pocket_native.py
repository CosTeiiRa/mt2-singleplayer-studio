"""Exercise original Pocket Wiki widgets in an owned client copy, without login.

Never launches or modifies the source client. The temporary original startup
harness is restored before returning the copy for ordinary manual testing.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HARNESS = r'''# -*- coding: utf-8 -*-
import os, json, traceback, time
result = {'status':'failed','server_connection':False,'interactive_gameplay':False}
def report():
    with open('pocket-native-result.json','wb') as stream:
        stream.write(json.dumps(result))
try:
    import app, wndMgr, ui, miniMap, grp
    result['stage']='device'
    wndMgr.SetScreenSize(1024,768)
    app.Create('Pocket Wiki isolated native test',1024,768,1)
    miniMap.Create()
    import uiMiniMap, m2hub_runtime, m2hub_client
    import game as shipped_game
    result['shipped_game_hooked']=bool(getattr(shipped_game.GameWindow,'_m2hub_v2',False))
    if not result['shipped_game_hooked']: raise ValueError('Shipped game lifecycle bootstrap did not install')
    result['registered']=[c.id for c in m2hub_runtime._contexts]
    expected=set(('community.addon-menu','community.boss-atlas','community.map-legend','community.pocket-wiki'))
    if set(result['registered']) != expected: raise ValueError('A default add-on failed native registration')
    result['atlas_hooks']=all(getattr(getattr(uiMiniMap.AtlasWindow,name),'_m2hub_wrapped',False) for name in ('OnUpdate','Destroy','SetMapName'))
    if not result['atlas_hooks']: raise ValueError('Shipped atlas lifecycle hooks missing')
    import m2hub_world
    names=[name for name,data in m2hub_world.WORLD.items() if any(region.get('type')=='boss' for region in data.get('regions',[]))]
    if not names: raise ValueError('No configured atlas regions exported')
    atlas=type('AtlasFixture',(object,),{})()
    atlas.AtlasMainWindow=ui.Window()
    atlas.AtlasMainWindow.SetSize(512,512)
    atlas.AtlasMainWindow.Show()
    atlas.mapName=names[0]
    original_size=miniMap.GetAtlasSize
    miniMap.GetAtlasSize=lambda:(True,512,512)
    try:
        atlas_callbacks=list(m2hub_runtime._listeners.get('atlas.update',[]))
        m2hub_runtime._emit('atlas.update',atlas)
        if len(m2hub_runtime._listeners.get('atlas.update',[])) != len(atlas_callbacks): raise ValueError('Atlas callback failed')
        atlas_widgets={}
        for ident,callback in atlas_callbacks:
            cells=getattr(callback,'func_closure',None) or ()
            values=[cell.cell_contents.get(id(atlas)) for cell in cells if isinstance(cell.cell_contents,dict)]
            values=[value for value in values if value is not None]
            if not values: raise ValueError('Atlas add-on produced no native widgets: '+ident)
            value=values[0]
            widgets=value[1] if isinstance(value,tuple) else [value]
            if not widgets or not all(widget.IsShow() for widget in widgets): raise ValueError('Atlas widgets not visible: '+ident)
            atlas_widgets[ident]=len(widgets)
        result['atlas_widgets']=atlas_widgets
        m2hub_runtime._emit('atlas.destroy',atlas)
        for ident,callback in atlas_callbacks:
            for cell in getattr(callback,'func_closure',None) or ():
                if isinstance(cell.cell_contents,dict) and id(atlas) in cell.cell_contents: raise ValueError('Atlas widgets did not dispose')
        result['atlas_lifecycle']=True
    finally:
        miniMap.GetAtlasSize=original_size
        atlas.AtlasMainWindow.Hide()
    context=[c for c in m2hub_runtime._contexts if c.id=='community.pocket-wiki'][0]
    class Game(ui.Window):
        def Open(self): self.Show()
        def Close(self): self.Hide()
        def OnKeyDown(self,key): return False
    m2hub_client.install({'GameWindow':Game})
    game=Game()
    import interfaceModule
    import uiToolTip
    game.interface=interfaceModule.Interface()
    game.interface.tooltipItem=uiToolTip.ItemToolTip()
    game.SetSize(1024,768)
    game.Open()
    result['stage']='addon-menu'
    menu_handle=m2hub_client._windows[('community.addon-menu','menu')]
    callback=[callback for ident,callback in m2hub_runtime._listeners['game.open'] if ident=='community.addon-menu'][0]
    launcher=getattr(callback,'im_self',getattr(callback,'__self__',None))
    if not launcher or not launcher.button or not launcher.button.IsShow(): raise ValueError('Add-ons launcher button missing')
    launcher.button.OnMouseLeftButtonUp()
    menu=menu_handle.window
    if not menu or not menu.IsShow(): raise ValueError('Add-ons menu did not open')
    result['menu_entries']=[row['name'] for row in menu.context.addons()]
    if result['menu_entries'][0]!='Add-on Menu': raise ValueError('Add-on Menu is not listed first')
    result['launcher_button']=True
    handle=m2hub_client._windows[('community.pocket-wiki','wiki')]
    started=time.clock()
    menu.Activate('community.pocket-wiki','window:wiki')
    if not handle.window or not handle.window.IsShow(): raise ValueError('Pocket Wiki did not open from Add-on Menu')
    if menu.IsShow(): raise ValueError('Add-on Menu did not close after opening Pocket Wiki')
    result['menu_opened_wiki']=True
    result['first_open_ms']=int((time.clock()-started)*1000)
    wiki=handle.window
    wiki.Close()
    original_pressed=app.IsPressed
    app.IsPressed=lambda key:key==app.DIK_LCONTROL
    try:
        if not game.OnKeyDown(app.DIK_U) or not handle.window.IsShow(): raise ValueError('Pocket Wiki shortcut did not open its window')
        result['wiki_shortcut']=True
    finally:
        app.IsPressed=original_pressed
    result['stage']='search-and-navigation'
    wiki.Category('Crafts')
    started=time.clock()
    rows,total=wiki.model.search('', 'Crafts')
    result['search_ms']=int((time.clock()-started)*1000)
    result['recipes']=total
    if not rows: raise ValueError('No recipes exported')
    wiki.Navigate(rows[0][0],rows[0][1])
    wiki.Attempts(2)
    wiki.Bookmark()
    wiki.Pin()
    wiki.Resize()
    wiki.Native()
    result['native_wiki_link']=bool(game.interface.wndWiki and game.interface.wndWiki.IsShow())
    if game.interface.wndWiki:
        game.interface.wndWiki.Close()
    wiki.Navigate(rows[0][0],rows[0][1])
    result['items']=len(wiki.model.data['items'])
    result['upgrades']=len(wiki.model.data['upgrades'])
    menu.Open()
    result['stage']='render'
    class Tick(ui.Window):
        def __init__(self):
            ui.Window.__init__(self)
            self.started=app.GetTime()
            self.done=False
            self.Show()
        def OnUpdate(self):
            if self.done or app.GetTime()-self.started < 1.5: return
            self.done=True
            try:
                result['screenshot']=grp.SaveScreenShotToPath(os.getcwd()+os.sep)
                game.Close()
                game.Open()
                if not menu_handle.open(): raise ValueError('Add-on Menu reopen failed')
                if not handle.toggle(): raise ValueError('Reopen failed')
                game.Close()
                result.update(status='passed',stage='complete',native_widgets=True,lifecycle=True)
            except Exception:
                result.update(error=traceback.format_exc())
            report()
            app.Exit()
    tick=Tick()
    app.Loop()
except Exception:
    result['error']=traceback.format_exc()
    report()
    try: app.Exit()
    except Exception: pass
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-root', type=Path)
    parser.add_argument('--prepared', type=Path, help='Reuse a previously created owned playable copy for this check.')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    from installation import default_root
    from server import Studio
    from addonhub.client_pack import EterPack
    from addonhub.client_adapter import create_playable_copy
    root = args.server_root or default_root()
    state = ROOT / '.test-tmp' / ('pocket-native-' + uuid.uuid4().hex[:10])
    if args.prepared:
        client = args.prepared.resolve()
        allowed = ROOT / '.test-tmp'
        if not client.is_relative_to(allowed) or not (client.parent / 'hub-sandbox.json').is_file():
            raise ValueError('Reuse only an owned test copy beneath Studio .test-tmp.')
        state = client.parents[4]
    studio = Studio(root, state / 'studio')
    service = studio.addons
    source = service.source
    before = {name: hashlib.sha256((source / 'pack' / name).read_bytes()).hexdigest() for name in ('root.index', 'root.data')}
    if not args.prepared:
        print('Copying client assets into an isolated playable test target...', flush=True)
        client = create_playable_copy(source, service.state_dir)
    service.manager.connect(client)
    for ident in ('community.addon-menu', 'community.boss-atlas', 'community.map-legend', 'community.pocket-wiki'):
        item = next(row for row in service.manager.catalog()['items'] if row['id'] == ident)
        if item['installed'] and not item['update_available']:
            continue
        print('Reviewing/installing ' + ident, flush=True)
        plan = service.post('plan', {'addon_id': ident, 'action': 'update' if item['installed'] else 'install'})['plan']
        if not plan['can_apply']:
            raise ValueError(plan['conflicts'])
        service.post('apply', {'plan_id': plan['id']})
    if args.prepared:
        plan = service.post('plan', {'addon_id': 'community.pocket-wiki', 'action': 'refresh-data'})['plan']
        if not plan['can_apply']:
            raise ValueError(plan['conflicts'])
        service.post('apply', {'plan_id': plan['id']})
    print('Prepared client: ' + str(client), flush=True)
    result = {'status': 'prepared', 'copy': str(client), 'executed': False, 'server_connection': False}
    if args.run:
        pack = EterPack.open(client / 'pack')
        files = pack.files()
        saved = {name: (client / 'pack' / name).read_bytes() for name in ('root.index', 'root.data')}
        report_path = client / 'pocket-native-result.json'
        report_path.unlink(missing_ok=True)
        files['prototype.py'] = HARNESS.encode('ascii')
        index, data = pack.build(files)
        (client / 'pack/root.index').write_bytes(index)
        (client / 'pack/root.data').write_bytes(data)
        try:
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            env = dict(os.environ, __COMPAT_LAYER='RunAsInvoker', LOCALAPPDATA=str(state / 'preferences'))
            process = subprocess.Popen([str(client / 'metin2client.exe')], cwd=client, startupinfo=startup, env=env)
            try:
                code = process.wait(timeout=55)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise ValueError('Owned native test did not finish within 55 seconds.')
            result.update(json.loads(report_path.read_text('utf-8')) if report_path.is_file() else {'status': 'failed', 'error': 'No native report'})
            result.update(executed=True, exit_code=code)
            if code != 0:
                result.update(status='failed', error='The copied native client exited with code %s.' % code)
        finally:
            for name, raw in saved.items():
                (client / 'pack' / name).write_bytes(raw)
    result['source_unchanged'] = before == {name: hashlib.sha256((source / 'pack' / name).read_bytes()).hexdigest() for name in before}
    output = state / 'result.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    (ROOT / 'data/pocket-native-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    if result['status'] == 'failed' or not result['source_unchanged']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
