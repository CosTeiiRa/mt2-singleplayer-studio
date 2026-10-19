# Pocket Wiki

Bundled experimental reference add-on for client 2.0.112 / client API v2.

Install and enable it in Studio, then launch your **normal game client** and enter
a character. Click **Pocket Wiki** near the top-left of the game screen or press
**Ctrl+U** with chat closed. Studio can be closed while you play. Change **Shortcut**
or **Show button** under **Installed add-ons → Pocket Wiki → Details**, then review
and apply with the client closed and launch it again.

Browse crafting, upgrade links, material sources and reverse uses; bookmark pages,
pin a scrollable card and calculate costs per attempt. Client names/icons come
from the installed game. The native-wiki button opens the selected item's existing
equipment page when that optional feature is available.

Studio generates reference data locally. Read each snapshot's provenance and Info
notes: SQL seed and saved configuration references can differ from effective
running rules. Native crafting uses a read-only current snapshot when available.

See [usage, refresh, removal and testing](../../../docs/POCKET_WIKI.md). This package
contains original code only; game-specific data/assets are not distributed.

Validate with `python tools/addon.py validate addonhub/catalog/community.pocket-wiki`.
Update manifest payload hashes after edits. Settings and code updates follow the
normal reviewed install flow. Disabling/removing the package removes its runtime
integration while retaining local personal preferences for a later reinstall.
