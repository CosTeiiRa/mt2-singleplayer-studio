# -*- coding: utf-8 -*-
"""Configured spawn areas on the atlas. No claim of current boss presence."""
import miniMap
import ui


def register(context):
    rendered = {}

    def clear(atlas):
        previous = rendered.pop(id(atlas), None)
        if previous:
            for widget in previous[1]:
                widget.Hide()

    def update(atlas):
        parent = getattr(atlas, 'AtlasMainWindow', None)
        if not parent:
            return
        data = context.world(getattr(atlas, 'mapName', ''))
        if not data:
            clear(atlas)
            return
        valid, width, height = miniMap.GetAtlasSize()
        if not valid or width <= 0 or height <= 0:
            return
        key = (data['id'], width, height)
        previous = rendered.get(id(atlas))
        if previous and previous[0] == key:
            return
        clear(atlas)
        widgets = []
        for region in data['regions']:
            if region['type'] == 'metin' and not context.settings.get('show_metins', False):
                continue
            x = region['x'] / float(data['width']) * width
            y = region['y'] / float(data['height']) * height
            rw = region['width'] / float(data['width']) * width
            rh = region['height'] / float(data['height']) * height
            color = 0xffffbd69 if region['type'] == 'boss' else 0xff89c3d8
            if context.settings.get('show_areas', True):
                left, top = max(0, x-rw/2), max(0, y-rh/2)
                right, bottom = min(width, x+rw/2), min(height, y+rh/2)
                zone = ui.Bar()
                zone.SetParent(parent)
                zone.AddFlag('not_pick')
                zone.SetPosition(int(left), int(top))
                zone.SetSize(max(1, int(right-left)), max(1, int(bottom-top)))
                zone.SetColor((color & 0x00ffffff) | 0x22000000)
                zone.Show()
                widgets.append(zone)
            dot = ui.Bar()
            dot.SetParent(parent)
            dot.AddFlag('not_pick')
            dot.SetPosition(max(0, int(x)-2), max(0, int(y)-2))
            dot.SetSize(5, 5)
            dot.SetColor(color)
            dot.Show()
            widgets.append(dot)
            if context.settings.get('show_labels', True):
                label = ui.TextLine()
                label.SetParent(parent)
                label.AddFlag('not_pick')
                label.SetPosition(max(0, min(int(x)+6, int(width)-110)), max(0, int(y)-8))
                label.SetText(str(region['name'])[:26])
                label.SetOutline()
                label.SetPackedFontColor(color)
                label.Show()
                widgets.append(label)
        rendered[id(atlas)] = (key, widgets)

    context.on('atlas.update', update)
    context.on('atlas.destroy', clear)
    context.log('Configured boss atlas registered')
