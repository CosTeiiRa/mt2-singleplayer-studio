# -*- coding: utf-8 -*-
"""Optional in-game launcher, implemented as an ordinary API-v2 add-on."""
import sys
import weakref
import ui
import wndMgr

GOLD, INK, MUTED = 0xffe5c789, 0xffeee7d9, 0xffaab5c2
_characters = None


def display(value):
    global _characters
    if sys.version_info[0] >= 3:
        return str(value)
    if not isinstance(value, unicode):
        return str(value)
    if _characters is None:
        try:
            import app, wikiui
            chars = wikiui._CODEPAGE_CHARACTERS.get(app.GetDefaultCodePage(), '')
        except (ImportError, AttributeError):
            chars = ''
        _characters = dict((char, chr(index + 128)) for index, char in enumerate(chars))
    return ''.join(chr(ord(char)) if ord(char) < 128 else _characters.get(char, '?') for char in value)


class Callback(object):
    def __init__(self, owner, method, *args):
        self.owner, self.method, self.args = weakref.ref(owner), method, args

    def __call__(self, *ignored):
        owner = self.owner()
        if owner:
            return getattr(owner, self.method)(*self.args)


def label(parent, x, y, text, width, color=INK):
    result = ui.TextLine()
    result.SetParent(parent)
    result.AddFlag('not_pick')
    result.SetPosition(int(x), int(y))
    result.SetPackedFontColor(color)
    value = display(text)
    result.SetText(value)
    while len(value) > 3 and result.GetTextSize()[0] > width:
        value = value[:-4]
        result.SetText(value + '...')
    result.Show()
    return result


class Action(ui.Bar):
    def __init__(self, parent, x, y, width, text, event=None):
        ui.Bar.__init__(self)
        self.SetParent(parent)
        self.SetPosition(int(x), int(y))
        self.SetSize(int(width), 24)
        self.event = event
        self.SetColor(0x885b482c if event else 0x33000000)
        self.label = label(self, 6, 3, text, width - 12, GOLD if event else MUTED)
        self.Show()

    def OnMouseLeftButtonUp(self):
        if self.event:
            self.event()
        return True

    def OnMouseOverIn(self):
        if self.event:
            self.SetColor(0xaa80643c)

    def OnMouseOverOut(self):
        self.SetColor(0x885b482c if self.event else 0x33000000)


class Menu(ui.BoardWithTitleBar):
    def __init__(self, context, game):
        ui.BoardWithTitleBar.__init__(self)
        self.context, self.widgets, self.page = context, [], 0
        self.AddFlag('movable')
        self.AddFlag('float')
        width = min(480, max(240, wndMgr.GetScreenWidth() - 20))
        height = min(470, max(230, wndMgr.GetScreenHeight() - 50))
        self.SetSize(width, height)
        self.SetTitleName('Add-ons')
        self.SetCloseEvent(Callback(self, 'Close'))
        self.SetPosition(max(0, (wndMgr.GetScreenWidth() - width) // 2),
                         max(0, (wndMgr.GetScreenHeight() - height) // 2))
        self.visible_rows = max(1, (height - 145) // 58)
        self.Hide()

    def Open(self):
        x, y = self.GetGlobalPosition()
        self.SetPosition(max(0, min(x, wndMgr.GetScreenWidth() - self.GetWidth())),
                         max(0, min(y, wndMgr.GetScreenHeight() - self.GetHeight())))
        self.Render()
        self.Show()
        self.SetTop()

    def Close(self):
        self.Hide()

    def OnPressEscapeKey(self):
        self.Close()
        return True

    def Destroy(self):
        self.Hide()
        self.Clear()
        self.context = None
        self.SetCloseEvent(None)

    def Clear(self):
        for widget in self.widgets:
            widget.Hide()
            if isinstance(widget, Action):
                widget.event = None
        self.widgets = []

    def TurnPage(self, change):
        self.page += change
        self.Render()

    def Activate(self, ident, action):
        if self.context.open_addon(ident, action):
            if ident != self.context.id:
                self.Close()
        else:
            self.Render('This map has no available atlas.' if action == 'atlas' else 'This window could not open. Restart the client and try again.')

    def Render(self, message=None):
        self.Clear()
        width, height = self.GetWidth(), self.GetHeight()
        addons = sorted(self.context.addons(), key=lambda item: (item['id'] != self.context.id, item['name'].lower(), item['id']))
        rows = [(item, action) for item in addons for action in (item['actions'] or [None])]
        pages = max(1, (len(rows) + self.visible_rows - 1) // self.visible_rows)
        self.page = max(0, min(self.page, pages - 1))
        self.widgets.append(label(self, 14, 38, 'Your installed add-ons', width - 28, GOLD))
        start = self.page * self.visible_rows
        for index, (item, action) in enumerate(rows[start:start + self.visible_rows]):
            y = 68 + index * 58
            name = item['name']
            if action and len(item['actions']) > 1:
                name += ' - ' + action['label']
            self.widgets.append(label(self, 14, y, name, width - 138))
            detail = item['status']
            if action and action['available']:
                shortcut = action['shortcut']
                detail += ' | ' + ('Ctrl+U' if shortcut == 'CTRL_U' else 'Button only' if shortcut == 'NONE' else shortcut)
            self.widgets.append(label(self, 14, y + 21, detail, width - 138, MUTED))
            available = bool(action and action['available'])
            title = 'Open atlas' if action and action['id'] == 'atlas' else 'Open'
            if not available:
                title = 'Disabled' if not item['enabled'] else 'Automatic' if not action and item['status'] == 'Runs automatically' else 'Unavailable'
            callback = Callback(self, 'Activate', item['id'], action['id']) if available else None
            self.widgets.append(Action(self, width - 112, y + 6, 96, title, callback))
        status = message or ('%d installed. Disabled add-ons can be enabled in Studio.' % len(addons))
        self.widgets.append(label(self, 14, height - 105, status, width - 28, GOLD if message else MUTED))
        self.widgets.append(Action(self, 14, height - 71, 90, 'Previous', Callback(self, 'TurnPage', -1) if self.page else None))
        self.widgets.append(label(self, width // 2 - 30, height - 66, '%d / %d' % (self.page + 1, pages), 65))
        self.widgets.append(Action(self, width - 104, height - 71, 90, 'Next', Callback(self, 'TurnPage', 1) if self.page + 1 < pages else None))
        self.widgets.append(label(self, 14, height - 35, 'Manage installs, settings and updates in Studio.', width - 28, MUTED))


class Launcher(object):
    def __init__(self, handle):
        self.handle, self.button = handle, None

    def opened(self, game):
        self.closed(game)
        self.button = Action(game, 12, 95, 94, 'Add-ons', Callback(self.handle, 'toggle'))

    def closed(self, game):
        if self.button:
            self.button.Hide()
            self.button.event = None
            self.button = None


def register(context):
    handle = context.register_window('menu', lambda game: Menu(context, game))
    launcher = Launcher(handle)
    context.on('game.open', launcher.opened)
    context.on('game.close', launcher.closed)
    context.log('Add-on Menu registered; click Add-ons in the game')
