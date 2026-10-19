# Item catalogue

[Back to the overview](../README.md#see-what-you-can-do) · [All documentation](README.md)

Studio combines the package's compact catalogue with item definitions from the
installed server's SQL seed. The compact catalogue can include items from other
versions, unused entries, placeholder names and references to absent icons.

## Choose what to browse

Item selectors in drops, quests, crafting and Item explorer have a **Catalogue
scope** filter:

| Scope | What it shows |
| --- | --- |
| Installed definitions | Items present in the installed server's bundled `item_proto` seed. This is the default. |
| Full catalogue | All known catalogue and seed entries. |
| Catalogue only | Catalogue entries absent from that seed. |
| Installed · missing icons | Seed entries without a verified local icon. |
| Installed · unnamed items | Seed entries without a usable name from the available sources. |

Shared reward pools remain available in drop selectors. Searching an exact
numeric ID can also reveal a catalogue-only entry in another scope, while still
respecting the field's allowed items, category and function filters. Clear filters
returns to installed definitions. Old names and original seed names are searchable.

The seed is a package reference, not a live database query. A definition does not
prove an item is obtainable in game. Items added or renamed directly in the live
database may need the full catalogue or direct ID inspection in Item explorer.

## Where names come from

Studio prefers a usable name in the installed `playerbot_names_en.tsv`, then a
usable compact catalogue name, then the seed's locale name. The installed English
file can correct stale labels such as `NoNAme` even when the compact catalogue
already contains that ID. No game definitions or translations are written back.

Empty names, placeholder labels and recognised broken legacy encodings display
**Unnamed item #ID** and **Name unavailable**. A usable untranslated name can
remain when no installed English translation exists. Studio does not invent one.

## Where icons come from

Studio uses the package's shipped read-only pack reader to inspect the client's
`gamedata/item_list.txt`. Explicit aliases select existing PNGs from the server's
`files/static/icons` directory. Paths with spaces and filename casing are handled.

For items without an explicit alias or exact ID PNG, Studio can use the client's
original proto name when every matching known icon agrees on one file. This uses
the original bytes, not translated display names. Empty and placeholder names,
ambiguous matches and explicitly missing assets remain unresolved. Nearby numeric
IDs are never used to guess a picture.

An explicit client alias whose PNG is missing takes precedence over older web
aliases. Its result is **Icon unavailable**, rather than another item's picture.
The mapping is cached privately in `<stateDir>/item-icon-aliases.json` and refreshed
when source fingerprints change. **Reload catalog** or restarting Studio rereads
the installed sources. Older packages without a supported pack reader retain
their static web mapping and exact ID fallback.

Remaining gaps can reflect unused game entries, absent assets, incomplete
translations or ambiguous mappings. A placeholder in Studio alone does not prove
the item is broken in game. Repairing or translating the game package is separate
from this read-only catalogue display.
