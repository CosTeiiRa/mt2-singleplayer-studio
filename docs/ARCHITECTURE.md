# Architecture and storage

[Overview diagram](../README.md#architecture-overview) · [All documentation](README.md)

The overview diagram introduces the Studio/game boundary. This guide explains the responsibilities, reviewed operations and storage behind it.

## Responsibilities and operations

Solid arrows show data access, loading and the game's own connections.
Dashed arrows show work performed during an explicit Studio **Apply**. External
sources are consulted only for requested checks/imports/downloads; Studio sends
them no game data or session token. This is a simplified view of the game's
supporting services. GitHub renders the diagram; the table describes the division.
The game's launcher/updater remains independent of Studio; game files take
priority when updates and customisations conflict.

| Responsibility | Where it belongs | How Studio interacts with it |
| --- | --- | --- |
| Dashboard, editors and add-on management | Studio | Runs locally; prepares reviews and coordinates explicit operations. |
| Drafts, history, installed add-on records, baselines and pack backups | Studio's private data folder | Preserved across Studio updates; separate from the game installation. |
| Launcher, client, scripts, server and MariaDB | Game | The game owns its updates and gameplay; Studio reads sources and applies only reviewed changes. |
| Installed add-on code and generated reference snapshots | Client packs, loaded inside the game client | Studio composes and installs them; they continue working when Studio is closed. |

**Server workflow — Review → Save → Apply:**

- **Review:** inspect the proposed values and source diff. This does not write game files or deploy anything.
- **Save:** write the reviewed configuration files with backups. A named change set holds edits in Studio until you publish that set. Saving does not restart the game; native crafting changes remain in a Studio-owned JSON configuration until Apply.
- **Server Apply:** build the saved configuration, compile custom quests, run the required settings migration and recreate the game container. Native crafting customisations are written to MariaDB in a guarded transaction while the game is stopped. Unsaved drafts and unpublished change sets are excluded. Connected players disconnect when the game restarts.

**Add-on workflow — Review → Apply:** validate the selected packages/settings,
compose them over the current game baseline, back up affected pack files, rebuild
and verify the packs. Close the selected client first, then launch it normally
afterwards. The server can stay running; unfinished transactions have a recovery
workflow.

The existing client connects directly to the game server. Closing Studio leaves
the game and installed add-ons running. Economy observations read existing game
data and save aggregate snapshots in Studio's SQLite files outside Docker.
Custom quests are optional server-side `.quest` scripts compiled by the existing
build; their creation also adds a backed-up compiler integration. Client add-ons
add Python integration to client packs. Studio does not patch engine or client
executable binaries.

See [Databases and Docker](#databases-and-docker) for storage details and [Your first edit](GETTING_STARTED.md#your-first-edit) for the editing workflow. Game updates have a separate [custom-change review](UPDATES_AND_BACKUPS.md#updating-the-game-or-studio) before Apply.

## Databases and Docker

The game and Studio use separate storage:

| Component | Database | Location and purpose |
|---|---|---|
| Existing game | MariaDB | Runs in the game's Docker setup; stores accounts, characters, inventories, shops, game logs and native crafting. Studio connects to this existing service. |
| Studio workspace | `workspace.sqlite` | A local Windows file holding drafts, tracked custom changes, change sets, deployment records and preferences. |
| Studio economy history | `economy.sqlite` | A local Windows file holding economic snapshots, journal notes and balancing experiments. |

**SQLite is outside Docker.** Studio's Python process accesses these files directly; SQLite needs no separate server or container. They live in the selected Studio data folder, normally `data/worlds/<id>/`. Setup prints its exact path; migrated installations can keep an older or explicitly chosen data folder.

Add-on management uses **`<stateDir>/addons/`** for installed package records,
immutable payloads, game-pack baselines, transaction backups and generated data
caches. These records are separate from MariaDB and the client packs themselves.
In-game preferences such as Pocket Wiki bookmarks live under
`%LOCALAPPDATA%/Metin2Studio/addon-preferences/<world-id>/`.

With Docker stopped, Studio can still open file-based editors and saved Studio
history. Live economy data and live native crafting require the game's MariaDB
service; **Server Apply** requires Docker. Client pack changes have their own
Apply and do not rebuild or restart the server. Stopping Studio leaves the game,
its database and installed add-ons running. Back up Studio's data folder and the
game/world database separately.

### Scalability

This beta is designed for one local owner managing one world. Each Studio installation has independent local databases; players do not write to Studio's SQLite files when they kill monsters or trade. By default, Studio collects aggregate economy snapshots every 60 minutes while running, has a 180-day snapshot retention setting and caches live observations for up to 60 seconds.

SQLite suits this workload, but it permits only one writer per database at a time; see [SQLite's deployment guidance](https://www.sqlite.org/whentouse.html). A shared service with many simultaneous administrators would need changes to Studio's architecture as well as its storage.

Larger economic histories would benefit from indexed history queries and more compact snapshot processing. Analytics also query the game's MariaDB, so performance depends on game data, queries and hardware. Some collection limits deliberately bound work—for example, 20,000 sales records per observation—with incomplete coverage flagged in the report. Functional tests do not establish a maximum supported player count.
