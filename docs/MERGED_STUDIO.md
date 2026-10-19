# Merged Studio workflow

Metin2 Studio combines the server workspace with Add-on Hub in one local Python
service. This guide describes **beta-1.11.0**, the small-beta candidate. Publishing
the repository or inviting testers remains a separate maintainer decision. See
[beta scope and acceptance](BETA_REVIEW.md) for current evidence and remaining work.

## Navigation and shared world

Overview, Economy and the existing Game configuration editors remain available. World atlas shows configured boss/Metin regions and base intervals from the selected server. Its View drops action opens the resolved mob in Studio, and Inspect spawn configuration opens the saved source. Neither action saves or applies a change.

Add-ons contains Discover, Repositories, Installed and Add-on settings.
Repositories subscribes to public GitHub repositories or creator HTTPS catalogs
and checks updates only when requested. Collections expose independent packages;
downloading one does not select its siblings. Source checks, download reviews and
downloads run as cancellable background jobs. Navigation stays available while
other add-on writes wait. Studio never automatically updates add-ons. Importing a
local ZIP or downloading a release validates/caches it; installation requires a
separate review and Apply. See the [repository guide](ADDON_REPOSITORIES.md).

**Add-on settings → Normal game client** selects the existing sibling `Klient`.
Close it before reviewed pack writes, then launch it with your usual game
shortcut. No second playable copy is required. Advanced testing tools retain
optional owned copies and nonrunnable pack sandboxes. Settings also provides
diagnostics and an allowlisted support report that omits paths, tokens, settings,
URLs and game content. Cross-world targets are rejected. Activity combines server
events and add-on transactions; server rollback remains in Change history.

The top-bar Apply to server control builds/restarts the server when explicitly requested. Add-on installation instead uses its own reviewed plan and pack transaction. A server build or package installation blocks new add-on mutations. Add-on operations never trigger a Docker build or restart.

## Start and optional dependencies

Use Install Studio.bat for the existing server, then Start Studio.bat. A matching running instance is reused. Stop Studio.bat validates the project and state folder and requests authenticated shutdown of that Studio only.

Python 3.10+ supports the server workspace and read-only atlas. Optional client pack support requires 64-bit Python 3.11+, lzokay 2.1.0 and NumPy 2.3.4 wheels. Install Add-on Support.bat installs them into `.vendor`; no system Python environment is modified. Restart after installation. Missing optional support leaves the server editors and atlas available.

## State and migration

Studio's selected server remains the world identity. Existing server history retains its SQLite schema, saved drafts, protected customisations and file backups. Add-on state is nested under that world's `addons/`, with its own baselines, ownership, journals and physical backups. These formats are not combined.

For a fresh Studio copy, the developer migration command is:

```powershell
python tools/import_existing.py --server-root "D:\Games\Metin2 Singleplayer\Serwer" --studio-data "D:\OldStudio\data" --hub-data "D:\OldHub\data" --port 8780
```

The destination must be fresh. SQLite's backup API creates consistent local snapshots; file backups are copied and checked. The old folders remain present. Migration checks both the world binding and workspace database identity. Only matching-world Hub history metadata is imported, labelled Previous Hub. Existing Hub client targets and installed payloads are not silently adopted. Their original state and backups remain in the old Hub folder. Never delete that folder merely because its history is visible here.

Import is a snapshot. Do not run both versions to make competing changes to the same world; stop the old UI before switching to the merged one. The game itself does not need a restart for this switch. If an interrupted import leaves an `-import-` staging folder, preserve it while investigating; a destination already in use is never overwritten.

Private migration details remain in the world's `migration.json` and are excluded
from source packages. A fresh install normally defaults to port 8765; setup can
select a different port. Imported histories do not transfer ownership of old Hub
targets or remove the need to preserve their original recovery files.

## Limits

Normal-client installation is implemented with reviewed plans, exact executable
checks, pack backups and transaction recovery. Clean game-pack replacements offer
**Review reapply** against the new baseline; mixed external edits require
inspection. Game updates take priority and never require keeping an old game
version for Studio. Unknown executables or changed hooks need adapter support;
publisher version coverage warnings alone do not prove incompatibility.

Pack sandboxes contain no runnable game. Spawn configuration is not live boss
telemetry, and intervals do not include every runtime override or dynamic
encounter. Native import/widget tests and pack lifecycle fixtures are separate
from logged-in gameplay, cross-resolution alignment and performance acceptance.
See the [acceptance matrix](BETA_REVIEW.md) for what has actually been checked.

Users choose sources they trust; publisher certification and mandatory signing
are outside scope. A hosted discovery catalog is optional. Configuration/pack
backups do not replace world/database backups; see [recovery](USER_GUIDE.md#backups-and-recovery).
