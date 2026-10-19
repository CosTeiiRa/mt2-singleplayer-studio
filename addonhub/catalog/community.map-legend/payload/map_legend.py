# -*- coding: utf-8 -*-
"""A second independent add-on using the same shared atlas callback."""
import miniMap
import ui


def register(context):
    labels = {}

    def clear(atlas):
        item = labels.pop(id(atlas), None)
        if item:
            item.Hide()

    def update(atlas):
        parent = getattr(atlas, 'AtlasMainWindow', None)
        if not parent:
            return
        valid, width, height = miniMap.GetAtlasSize()
        if not valid:
            return
        label = labels.get(id(atlas))
        if label is None:
            label = ui.TextLine()
            label.SetParent(parent)
            label.AddFlag('not_pick')
            label.SetOutline()
            label.SetPackedFontColor(0xffeadac1)
            labels[id(atlas)] = label
        label.SetPosition(8, max(0, int(height)-18))
        label.SetText('Add-on Hub | Configured zones, not live')
        label.Show()

    context.on('atlas.update', update)
    context.on('atlas.destroy', clear)
