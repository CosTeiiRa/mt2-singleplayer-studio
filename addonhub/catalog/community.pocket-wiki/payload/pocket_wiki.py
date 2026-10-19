# -*- coding: utf-8 -*-
"""Original in-game crafting/reference browser, using native client widgets."""
import weakref
import sys
import ui
import app
import wndMgr
import item
pocket_model = None

try:
    unicode_type = unicode
except NameError:
    unicode_type = str

GOLD, INK, LINK = 0xffe5c789, 0xffeee7d9, 0xffa9d9e9
_characters = None
_encoded_characters = None


def native_characters():
    global _characters, _encoded_characters
    if _characters is None:
        try:
            import wikiui
            _characters = wikiui._CODEPAGE_CHARACTERS.get(app.GetDefaultCodePage(), '')
        except (ImportError, AttributeError):
            _characters = ''
        _encoded_characters = dict((char, chr(index + 128)) for index, char in enumerate(_characters))
    return _characters


def decoded(value):
    if not isinstance(value, bytes):
        return value
    chars = native_characters()
    return u''.join(unicode_type(chr(number)) if number < 128 else chars[number - 128] if chars else u'?' for number in bytearray(value))


def display(value):
    if not isinstance(value, unicode_type):
        return value
    if sys.version_info[0] >= 3:
        return value
    native_characters()
    return ''.join(chr(ord(char)) if ord(char) < 128 else _encoded_characters.get(char, '?') for char in value)


def native_name(ident):
    if hasattr(item, 'SelectItemWiki') and not item.SelectItemWiki(ident):
        return None
    if not hasattr(item, 'SelectItemWiki'):
        item.SelectItem(ident)
    return decoded(item.GetItemName())


class Callback(object):
    def __init__(self, owner, method, *args):
        self.owner, self.method, self.args = weakref.ref(owner), method, args

    def __call__(self, *ignored):
        owner = self.owner()
        if owner:
            return getattr(owner, self.method)(*self.args)


class Link(ui.Bar):
    def __init__(self, parent, x, y, width, label, event=None, color=INK, item_id=None):
        ui.Bar.__init__(self)
        self.SetParent(parent)
        self.SetPosition(int(x), int(y))
        self.SetSize(max(15, int(width)), 21)
        self.SetColor(0x55000000 if event else 0x00000000)
        self.event = event
        self.icon = None
        inset = 4
        if item_id:
            try:
                if item.SelectItemWiki(int(item_id)):
                    self.icon = ui.ExpandedImageBox()
                    self.icon.SetParent(self)
                    self.icon.AddFlag('not_pick')
                    self.icon.LoadImage(item.GetIconImageFileName())
                    self.icon.SetScale(0.5, 0.5)
                    self.icon.SetPosition(2, 1)
                    self.icon.Show()
                    inset = 23
            except Exception:
                self.icon = None
        self.label = ui.TextLine()
        self.label.SetParent(self)
        self.label.AddFlag('not_pick')
        self.label.SetPosition(inset, 2)
        self.label.SetPackedFontColor(color)
        self.label.SetText(display(label))
        self.label.Show()
        # Fit with real font measurements; the full name remains on its page.
        value = pocket_model.text(label)
        while len(value) > 3 and self.label.GetTextSize()[0] > width - inset - 4:
            value = value[:-4]
            self.label.SetText(display(value + '...'))
        self.Show()

    def OnMouseLeftButtonUp(self):
        if self.event:
            self.event()
        return True

    def OnMouseOverIn(self):
        if self.event:
            self.SetColor(0x99705d3c)

    def OnMouseOverOut(self):
        self.SetColor(0x55000000 if self.event else 0x00000000)


class Search(ui.EditLine):
    def __init__(self, owner):
        ui.EditLine.__init__(self)
        self.owner = weakref.ref(owner)

    def OnIMEUpdate(self):
        ui.EditLine.OnIMEUpdate(self)
        owner = self.owner()
        if owner:
            owner.search_due = app.GetTime() + 0.18


class PinCard(ui.BoardWithTitleBar):
    def __init__(self, owner, title, rows):
        ui.BoardWithTitleBar.__init__(self)
        self.owner, self.rows, self.widgets = weakref.ref(owner), rows, []
        self.AddFlag('movable')
        self.AddFlag('float')
        width = min(380, wndMgr.GetScreenWidth() - 20)
        height = min(340, wndMgr.GetScreenHeight() - 120)
        self.visible = max(4, (height - 55) // 23)
        self.SetSize(width, height)
        self.SetTitleName(display(pocket_model.text(title)[:35]))
        self.SetPosition(max(10, wndMgr.GetScreenWidth() - width - 12), 95)
        self.SetCloseEvent(Callback(self, 'Close'))
        self.scroll = ui.ScrollBar()
        self.scroll.SetParent(self)
        self.scroll.SetPosition(width - 24, 34)
        self.scroll.SetScrollBarSize(height - 48)
        self.scroll.SetScrollEvent(Callback(self, 'Render'))
        self.scroll.Show()
        self.Render()
        self.Show()
        self.SetTop()

    def Render(self):
        for widget in self.widgets:
            widget.Hide()
        self.widgets = []
        owner = self.owner()
        if not owner:
            return
        offset = int(max(0, len(self.rows) - self.visible) * self.scroll.GetPos())
        for index, row in enumerate(self.rows[offset:offset + self.visible]):
            link = row.get('link')
            self.widgets.append(Link(self, 10, 34 + index * 23, self.GetWidth() - 40, row['text'],
                                     Callback(owner, 'PinnedNavigate', *link) if link else None,
                                     LINK if link else INK, item_id=link[1] if link and link[0] == 'item' else None))

    def Close(self):
        self.Hide()

    def OnPressEscapeKey(self):
        self.Close()
        return True


class Wiki(ui.BoardWithTitleBar):
    def __init__(self, context, game):
        ui.BoardWithTitleBar.__init__(self)
        self.context, self.game = context, weakref.ref(game)
        self.AddFlag('movable')
        self.AddFlag('float')
        self.SetTitleName('Pocket Wiki')
        self.SetCloseEvent(Callback(self, 'Close'))
        self.model = pocket_model.Model(context.reference(), context.load_state(), native_name)
        self.children, self.result_widgets, self.detail_widgets = [], [], []
        self.search_due, self.result_offset, self.detail_offset = 0, 0, 0
        self.expanded, self.rebuilding = False, False
        self.pin = None
        self.page_offsets = {}
        self._layout()
        position = self.model.state.get('position', [40, 60])
        if not isinstance(position, list) or len(position) != 2 or not all(isinstance(value, (int, float)) for value in position):
            position = [40, 60]
        self.SetPosition(int(max(0, min(position[0], wndMgr.GetScreenWidth() - self.GetWidth()))),
                         int(max(0, min(position[1], wndMgr.GetScreenHeight() - self.GetHeight()))))
        self.Hide()

    def _link(self, x, y, width, label, method=None, *args):
        widget = Link(self, x, y, width, label, Callback(self, method, *args) if method else None)
        self.children.append(widget)
        return widget

    def _layout(self):
        self.rebuilding = True
        for widget in self.children + self.result_widgets + self.detail_widgets:
            widget.Hide()
        self.children, self.result_widgets, self.detail_widgets = [], [], []
        screen_width, screen_height = wndMgr.GetScreenWidth(), wndMgr.GetScreenHeight()
        saved_size = self.model.state.get('size', [840, 600])
        if not isinstance(saved_size, list) or len(saved_size) != 2 or not all(isinstance(value, (int, float)) for value in saved_size):
            saved_size = [840, 600]
        width = int(min(screen_width - 20, max(610, saved_size[0])))
        height = int(min(screen_height - 30, max(410, saved_size[1])))
        self.SetSize(width, height)
        self.left_width = min(240, max(180, width // 3))
        self.visible_rows = max(4, (height - 218) // 23)
        self.search_bg = ui.SlotBar()
        self.search_bg.SetParent(self)
        self.search_bg.SetPosition(12, 36)
        self.search_bg.SetSize(width - 102, 21)
        self.search_bg.Show()
        self.children.append(self.search_bg)
        self.search = Search(self)
        self.search.SetParent(self.search_bg)
        self.search.SetPosition(4, 3)
        self.search.SetSize(width - 112, 18)
        self.search.SetMax(120)
        self.search.SetText(display(self.model.query))
        self.search.SetReturnEvent(Callback(self, 'SearchNow'))
        self.search.SetEscapeEvent(Callback(self, 'Close'))
        self.search.Show()
        self.children.append(self.search)
        self._link(width - 84, 36, 70, 'Search', 'SearchNow')
        categories = ('All', 'Items', 'Crafts', 'Upgrades', 'NPCs', 'Bookmarks', 'History')
        tab_width = (width - 24) // len(categories)
        for index, category in enumerate(categories):
            self._link(12 + index * tab_width, 64, tab_width - 3, category, 'Category', category)
        self._link(12, 93, 50, '< Back', 'Travel', -1)
        self._link(65, 93, 55, 'Next >', 'Travel', 1)
        self._link(123, 93, 78, 'Bookmark', 'Bookmark')
        self._link(204, 93, 52, 'Pin', 'Pin')
        self._link(259, 93, 88, 'Native wiki', 'Native')
        self._link(350, 93, 60, 'Info', 'Info')
        self._link(413, 93, 48, 'Reset', 'Reset')
        self._link(width - 90, height - 35, 72, 'Resize +/-', 'Resize')
        self._link(self.left_width + 27, height - 63, 36, '-', 'Attempts', -1)
        attempt_background = ui.SlotBar()
        attempt_background.SetParent(self)
        attempt_background.SetPosition(self.left_width + 66, height - 63)
        attempt_background.SetSize(65, 21)
        attempt_background.Show()
        self.children.append(attempt_background)
        self.attempt_entry = ui.EditLine()
        self.attempt_entry.SetParent(attempt_background)
        self.attempt_entry.SetPosition(4, 3)
        self.attempt_entry.SetSize(57, 18)
        self.attempt_entry.SetMax(4)
        self.attempt_entry.SetNumberMode()
        self.attempt_entry.SetText(str(self.model.attempts))
        self.attempt_entry.SetReturnEvent(Callback(self, 'SetAttempts'))
        self.attempt_entry.SetEscapeEvent(Callback(self, 'Close'))
        self.attempt_entry.Show()
        self.children.append(self.attempt_entry)
        self._link(self.left_width + 136, height - 63, 78, 'attempt(s)')
        self._link(self.left_width + 220, height - 63, 36, '+', 'Attempts', 1)
        self.result_scroll = ui.ScrollBar()
        self.result_scroll.SetParent(self)
        self.result_scroll.SetPosition(self.left_width + 14, 142)
        self.result_scroll.SetScrollBarSize(self.visible_rows * 23)
        self.result_scroll.SetScrollEvent(Callback(self, 'ResultsScrolled'))
        self.result_scroll.Show()
        self.children.append(self.result_scroll)
        self.detail_scroll = ui.ScrollBar()
        self.detail_scroll.SetParent(self)
        self.detail_scroll.SetPosition(width - 25, 142)
        self.detail_scroll.SetScrollBarSize(self.visible_rows * 23)
        self.detail_scroll.SetScrollEvent(Callback(self, 'DetailsScrolled'))
        self.detail_scroll.Show()
        self.children.append(self.detail_scroll)
        self.status = self._link(12, height - 35, width - 115, '')
        self.rebuilding = False
        self.SearchNow()
        self.RenderPage()

    def Open(self):
        self.Show()
        self.SetTop()
        self.search.SetFocus()

    def Close(self):
        self.search.KillFocus()
        self.attempt_entry.KillFocus()
        self.Hide()
        self.Save()

    def Save(self):
        self.model.state['position'] = list(self.GetLocalPosition())
        self.model.state['size'] = [self.GetWidth(), self.GetHeight()]
        self.context.save_state(self.model.persist())

    def Destroy(self):
        self.Save()
        self.Hide()
        if self.pin:
            self.pin.Hide()
            self.pin = None
        self.search.KillFocus()
        for widget in self.children + self.result_widgets + self.detail_widgets:
            widget.Hide()
        self.children, self.result_widgets, self.detail_widgets = [], [], []
        self.context = None

    def OnPressEscapeKey(self):
        self.Close()
        return True

    def OnUpdate(self):
        if self.search_due and app.GetTime() >= self.search_due:
            self.search_due = 0
            self.SearchNow()

    def SearchNow(self):
        query = decoded(self.search.GetText())
        self.model.search(query=query)
        self.result_offset = 0
        self.RenderResults()

    def Category(self, category):
        self.model.category = category
        self.result_offset = 0
        self.RenderResults()

    def RenderResults(self):
        for widget in self.result_widgets:
            widget.Hide()
        self.result_widgets = []
        rows, total = self.model.search(offset=self.result_offset, limit=self.visible_rows)
        self.result_total = total
        for index, row in enumerate(rows):
            label = ('* ' if [row[0], row[1]] in self.model.state['bookmarks'] else '') + pocket_model.text(row[2])
            widget = Link(self, 12, 142 + index * 23, self.left_width, label, Callback(self, 'Navigate', row[0], row[1]), LINK)
            self.result_widgets.append(widget)
        self.status.label.SetText(display('%d results | %s | Ctrl+U / configured shortcut' % (total, self.model.category)))

    def ResultsScrolled(self):
        if not self.rebuilding:
            self.result_offset = int(max(0, getattr(self, 'result_total', 0) - self.visible_rows) * self.result_scroll.GetPos())
            self.RenderResults()

    def Navigate(self, kind, ident):
        if self.model.current:
            self.page_offsets[tuple(self.model.current)] = self.detail_offset
        if self.model.navigate(kind, ident):
            self.detail_offset = self.page_offsets.get(tuple(self.model.current), 0)
            self.RenderPage()

    def Travel(self, direction):
        if self.model.current:
            self.page_offsets[tuple(self.model.current)] = self.detail_offset
        if self.model.travel(direction):
            self.detail_offset = self.page_offsets.get(tuple(self.model.current), 0)
            self.RenderPage()

    def _detail_lines(self, rows, width):
        result = []
        for row in rows:
            value = pocket_model.text(row['text'])
            if not value:
                continue
            if row.get('link'):
                result.append(row)
                continue
            # Bound text line width using a conservative font character budget.
            budget = max(24, width // 7)
            words, line = value.split(), ''
            for word in words:
                if len(line) + len(word) + 1 > budget and line:
                    result.append({'text': line})
                    line = ''
                line += (' ' if line else '') + word
            if line:
                result.append({'text': line})
        return result

    def RenderPage(self, rows=None):
        for widget in self.detail_widgets:
            widget.Hide()
        self.detail_widgets = []
        title, data = self.model.page()
        if rows is not None:
            title, data = 'Reference data', rows
        self.SetTitleName(display('Pocket Wiki | ' + pocket_model.text(title)[:65]))
        width = self.GetWidth() - self.left_width - 64
        self.page_rows = self._detail_lines(data, width)
        self._render_detail_slice()
        self.attempt_entry.SetText(str(self.model.attempts))

    def _render_detail_slice(self):
        for widget in self.detail_widgets:
            widget.Hide()
        self.detail_widgets = []
        for index, row in enumerate(self.page_rows[self.detail_offset:self.detail_offset + self.visible_rows]):
            link = row.get('link')
            event = Callback(self, 'Navigate', *link) if link else None
            widget = Link(self, self.left_width + 40, 142 + index * 23, self.GetWidth() - self.left_width - 74,
                          row['text'], event, LINK if link else INK, item_id=link[1] if link and link[0] == 'item' else None)
            self.detail_widgets.append(widget)

    def DetailsScrolled(self):
        if not self.rebuilding:
            self.detail_offset = int(max(0, len(getattr(self, 'page_rows', [])) - self.visible_rows) * self.detail_scroll.GetPos())
            self._render_detail_slice()

    def Bookmark(self):
        self.model.bookmark()
        self.Save()
        self.RenderResults()

    def Attempts(self, change):
        self.model.attempts = min(9999, max(1, self.model.attempts + change))
        self.detail_offset = 0
        self.RenderPage()

    def SetAttempts(self):
        try:
            self.model.attempts = min(9999, max(1, int(self.attempt_entry.GetText())))
        except ValueError:
            self.model.attempts = 1
        self.attempt_entry.KillFocus()
        self.detail_offset = 0
        self.RenderPage()

    def Native(self):
        if self.model.current:
            kind, ident = self.model.current
            if kind == 'recipe':
                ident = self.model.data['recipes'][ident]['outputs'][0]['item']
            if kind in ('item', 'upgrade', 'recipe'):
                if not self.context.open_native_item(self.game(), ident):
                    self.status.label.SetText('Native wiki unavailable in this client.')

    def Info(self):
        meta = self.model.data['meta']
        rows = [{'text': 'Server %s | generated %s' % (meta['server_version'], meta['generated_at'])},
                {'text': 'Snapshot ' + meta['snapshot'][:16]}]
        rows.extend({'text': warning} for warning in meta['warnings'])
        self.detail_offset = 0
        self.RenderPage(rows)

    def Reset(self):
        self.model.state['size'] = [840, 600]
        self.SetPosition(10, 35)
        self._layout()

    def Resize(self):
        self.expanded = not self.expanded
        self.model.state['size'] = [1020, 740] if self.expanded else [740, 520]
        self._layout()
        x, y = self.GetLocalPosition()
        self.SetPosition(max(0, min(x, wndMgr.GetScreenWidth() - self.GetWidth())),
                         max(0, min(y, wndMgr.GetScreenHeight() - self.GetHeight())))

    def Pin(self):
        if not self.model.current:
            return
        if self.pin:
            self.pin.Hide()
        title, rows = self.model.page()
        width = min(380, wndMgr.GetScreenWidth() - 20)
        self.pin = PinCard(self, title, self._detail_lines(rows, width - 45))

    def PinnedNavigate(self, kind, ident):
        self.Navigate(kind, ident)
        self.Open()


class Launcher(object):
    def __init__(self, context, handle):
        self.context, self.handle, self.button = context, handle, None

    def opened(self, game):
        if self.context.settings.get('show_button', True):
            self.button = Link(game, 12, 125, 94, 'Pocket Wiki', Callback(self.handle, 'toggle'), GOLD)

    def closed(self, game):
        if self.button:
            self.button.Hide()
            self.button = None


def register(context):
    global pocket_model
    pocket_model = context.module('m2hub_addons.pocket_model')
    handle = context.register_window('wiki', lambda game: Wiki(context, game), context.settings.get('shortcut', 'CTRL_U'))
    launcher = Launcher(context, handle)
    context.on('game.open', launcher.opened)
    context.on('game.close', launcher.closed)
    context.log('Pocket Wiki registered; use its button or configured shortcut')
