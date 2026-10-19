# Item catalogue

[Back to the overview](../README.md#see-what-you-can-do) · [All documentation](README.md)

Studio builds one catalogue from the running server and installed client. Editors,
search, Pocket Wiki reference exports and atlas names use this
shared snapshot. The catalogue status above the page shows whether Studio is using
live data, a previous cache or the package's bundled fallback files.

## Startup, updates and offline use

At startup Studio reads item and mob definitions from the existing MariaDB world
database in a read-only transaction. It reads names, descriptions and icon pixels
from the installed client's `gamedata`, `locale` and `icon` packs. It never starts
Docker, changes database rows or rewrites packs to read the catalogue.

While Studio runs, local source fingerprints are checked every 15 seconds and
live database definitions every minute. Changed package files must remain stable
across checks before replacing the snapshot. An interrupted or unreadable client
update retains the last readable client data. The dashboard's normal status refresh
updates its shared item/mob maps and open picker without discarding editor drafts.

Private generated data lives under `<stateDir>/catalogue/`:

- `server.json`: last successful item/mob definitions, source version and timestamp.
- `client.json`: client names, descriptions, icon mappings and source fingerprints.
- `icons/`: generated PNGs keyed by their pixel-file hash.

The caches are bound to the selected installation. When the server is unavailable,
Studio keeps its last successful definitions and retries automatically. If the
client packs are unavailable, cached names and icons remain usable. A cache from
an earlier server package is labelled. On a first offline launch without a cache,
the package's SQL seed and web exports provide fallback data.

**Reload catalog** performs an immediate check. Reopening Studio also checks the
current server and client; updating Studio does not require clearing these caches.

## Choose what to browse

Item selectors in drops, quests, crafting and Item explorer have a **Catalogue
scope** filter:

| Scope | What it shows |
| --- | --- |
| Installed definitions | Items in the live server snapshot, its offline cache, or the seed fallback. This is the default. |
| Full catalogue | All known server, client and bundled catalogue entries. |
| Catalogue only | Entries absent from the selected server definition snapshot. |
| Installed · missing icons | Server definition entries without a verified local icon. |
| Installed · unnamed items | Server definition entries without a usable name. |

Shared reward pools remain available in drop selectors. Searching an exact
numeric ID can also reveal a catalogue-only entry in another scope, while still
respecting the field's allowed items, category and function filters. Clear filters
returns to installed definitions. Old names and original seed names are searchable.

A definition does not prove an item is obtainable in game. Runtime script rules,
player inventories and rolled item bonuses are outside this catalogue. A bundled
seed fallback can omit newer custom server items until a live read succeeds.

## Explore and return to your results

**Item explorer** opens the searchable catalogue directly. **Saved items** opens
favourites and recently inspected items. Selecting an item keeps the picker open
behind its details. **Back to items**, **Back to item search**, Close or Escape
return to that picker with its search, filters, loaded results and scroll intact.
Selecting an item in an editing field still selects it and closes that picker.

Search, saved items, drops, crafting, quest rewards share the
same item identity and hover/focus details. Hover or focus an item for its configured effects. Weapon attack/magic attack
ranges, armour defence and fixed bonuses use server definition fields; their
displayed formulas follow the installed client tooltip. Bonus names and native
point mappings are read as literal data from the package's panel sources.

Dragon Stones use the last successfully read **deployed**
`/opt/metin2/share/locale/poland/dragon_soul_table.txt`. This installation's build
replaces the table in the host folder, so the host copy is not treated as proof of
runtime values. The server cache retains the deployed balance and bonus labels.
Background catalogue checks also pick up changes to this balance.

The preview decodes the item's family, class, quality and strength, applies the
configured weight to base values, and rounds calculated values up to whole points.
Fixed base effects and possible additional rolls are separate. Additional options
are alternatives, not bonuses guaranteed together. This is a calculated catalogue
preview, not the attributes of a particular inventory stone. Missing/unsupported
table entries display no invented bonus values.

## Where names come from

Studio prefers the client's English item/mob names. The installed English export,
live server locale name, client proto locale name and older compact catalogue
provide fallbacks where available. Previous compact and server names remain
searchable. Client descriptions appear alongside the general guide and server
definition facts. No game names or translations are written back.

Empty names, placeholder labels and recognised broken legacy encodings display
**Unnamed item #ID** and **Name unavailable**. A usable untranslated name can
remain when no installed English translation exists. Studio does not invent one.

## Where icons come from

Studio uses the package's shipped read-only pack reader to inspect the client's
`gamedata/item_list.txt`. Explicit aliases select original pixels from the client's
`icon` pack. True-colour and RLE TGA icons are converted to private PNGs using
Python's standard library; PNG sources are retained directly. Paths with spaces
and filename casing are handled. Unsupported formats remain unresolved.

For items without an explicit alias or exact ID client icon, Studio can use the client's
original proto name when every matching known icon agrees on one file. This uses
the original bytes, not translated display names. Empty and placeholder names,
ambiguous matches and explicitly missing assets remain unresolved. Nearby numeric
IDs are never used to guess a picture.

An explicit client alias whose asset is missing takes precedence over older web
aliases. Its result is **Icon unavailable**, rather than another item's picture.
The mapping and generated images are cached privately under `<stateDir>/catalogue/`.
Older packages without a supported pack reader retain their static web mapping and
exact ID PNG fallback. The earlier `item-icon-aliases.json` cache is no longer the
source used by the shared catalogue.

## Add-on reference data

Pocket Wiki exports use the same item names, descriptions, types and definition
snapshot as Studio. Atlas/Boss Atlas/Map Legend exports use its mob names. The
generated reference metadata records the catalogue revision, and Pocket Wiki's
installed details show when that revision is outdated.

Installed in-game add-ons keep the reference data already written into their pack
until **Review reference-data refresh** is applied. The preview reads the shared
current snapshot again and rejects changed reference data after review. Close the
client before applying; the server can stay running. Catalogue background checks
never write to the client packs. This also keeps the in-game wiki usable with
Studio closed. Recipe/shop/drop reference coverage is documented separately in
the [Pocket Wiki guide](POCKET_WIKI.md).

Remaining gaps can reflect unused game entries, absent assets, incomplete
translations or ambiguous mappings. A placeholder in Studio alone does not prove
the item is broken in game. Repairing or translating the game package is separate
from this read-only catalogue display.
