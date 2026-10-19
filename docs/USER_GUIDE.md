# Operator guide

Installation and first launch: [setup guide](GETTING_STARTED.md). `<stateDir>` is the local world data folder printed by setup.

## What is included

| Area | Features |
|---|---|
| Drops and chests | Metin/boss/monster filters, searchable items, quantities, weights/chances, shared pools and combined-source views |
| Item catalog | Category/function filters, descriptions, icons and existing drop/craft/shop/refinement references |
| Quests | A quest library, guided editing of supported existing fields, hunt/turn-in/exchange templates, cooldowns, NPC guidance, cloning and removal of Studio quests |
| Crafting | Existing Cube and native NPC menus, automatic system selection, ingredients/reward/chance/cost/requirements, cloning, shared-definition warnings and removal |
| Economy | GM-separated views, stock/trade/price/activity indicators, snapshots, experiments, event journal and CSV/JSON exports with coverage limits |
| Configuration | Submenus for gameplay settings, spawns/maps, fishing, alchemy and supported advanced files |
| Change management | Drafts, named change sets, reviewable backups/rollbacks, pending Apply counts and custom-difference update protection |
| Client add-ons | Discover, repositories, local import, reviewed install/update/settings/enable/disable/removal, pack backups and recovery |
| Bundled in-game tools | Add-on Menu, Boss Atlas, Atlas Legend and Pocket Wiki; install the ones you want in your normal game client |

See the [operator guide](USER_GUIDE.md) for mechanics, source coverage and limitations. Normal configuration edits use the game's existing systems. **New quests are opt-in server-side scripts:** saving one adds `.quest` source and a backed-up compiler integration; generated templates use the existing game logging API for their limited item-flow records. They do not change engine or client binaries. Native crafting saves a Studio JSON configuration; its database changes happen only during Apply.

Change history separates **Gameplay changes** (recipes, drops, quests, EXP and settings) from **Update reconciliations** (game-update merges and conflict resolutions). **All changes** shows both. Rollback still checks newer edits across both categories.

Use **Change type** to filter either view by Quests, Crafting, Drops, World settings,
Maps & spawns, Shops, Fishing, Alchemy, Items, Skills, Events or Other server files.
Existing backups are included. A save touching several types appears under each;
**Review rollback** still reviews the whole save. Select **All types** to clear the filter.

## Client add-ons

**Add-on Menu** is the first bundled package. Install/enable it to get an **Add-ons**
button near the top-left in-game. Click it after entering a character, then choose
an extension to open. Atlas overlays open the normal atlas; standalone extensions
open their registered windows. Disabled/unavailable entries explain why they cannot
open. This menu can be removed independently; other add-on controls remain.

Use **Add-on settings → Normal game client**. Close that client, review and apply
an add-on, then launch the game with your usual shortcut. The server may keep
running. Backups cover changed pack files; a second playable client is optional
under **Advanced testing tools**.

If an update replaces the managed packs with clean game files, **Review reinstall**
uses those new files as the baseline and retains installed add-on settings. Apply
is manual. Removing the last add-on restores the current game baseline. A partial
external edit retaining Hub code remains a conflict for inspection.

## What you can change

The inventory is generated from the installed package, rather than from a generic Metin2 server guide. Counts are discovered from the selected installation and change as files change. The initial small-beta target is server 2.2.110 / client 2.0.114; see the [acceptance matrix](BETA_REVIEW.md) for tested scope and remaining human checks.

| Area | Editor | Source / behavior |
|---|---|---|
| Metin, boss and monster loot | Searchable target and reward selectors, counts, percentages, weights, linked reward pools | `game/share/locale/poland/mob_drop_item.txt` and `game/share-add/mob_drop_item.m3.append.txt` |
| Chests and shared reward pools | Searchable rewards, quantities and weights; weighted shares shown separately from independent percentages | `special_item_group.txt` plus the package’s Moonlight, starter and hexagonal additions |
| Moonlight chest | Same guided editor | Writes the persistent `game/special_item_group.moonlight.custom.txt`, rather than the shipped default that updates replace |
| New quests | NPC, minimum level, hunt target, kill count, item/Yang/EXP rewards, source preview and download | One completion per character. Adds `game/custom-quests/studio_*.quest` and a backed-up build hook in the existing Linux compiler stage |
| Crafting | Searchable NPC, ingredients, rewards, quantities, Yang cost and success chance | Cube files and the current native crafting tables, selected automatically by NPC; see Crafting access below |
| Difficulty and waiting times | Searchable settings forms with package notes | `.env`; custom waits and exchange chances require `M2_DIFFICULTY=custom` |
| World features | Forms | Starter kit/chest, horse quest skip, Auto Hunt, companion, Dragon Soul, flea market, extra drops, itemshop price scaling and more |
| Bots | Forms | Population, kingdoms, arrival schedule, world layout and channel-related gameplay settings |
| Material and common loot | Advanced file editor | `etc_drop_item.txt`, `common_drop_item.txt`; common drops have a rank/level table format |
| Boss schedules and map spawns | Advanced file editor | `special_spawns.txt`, spawn groups, per-map regen/npc/boss/stone files |
| Fishing, potion bonuses and alchemy | Advanced file editor | `fishing.txt`, `blend.txt`, `dragon_soul_table.txt` |
| Skills, OX quiz and Lua configuration | Advanced file editor | `skill_power.txt`, quiz files and exposed Lua settings |
| Existing quests | Guided fields, item/target selectors, section filter; Advanced source for custom logic | Recognised literal requirements, quantities, rewards, kills, levels and cooldowns. Linked references are patched together; original quest identity/states retained. Exact edited sources are registered for compilation. |
| Extended NPC shops | Advanced file editor | `shop_table_ex.txt`; ordinary shop inventories/prices live in the database |
| Restore | Reviewable restore in Change history | Configuration backups; checks for newer edits before restoring |

All `game/...` paths above are relative to `Serwer/linux-port/docker/`.

## Managing quests

Open **Quests** for the quest menu. It lists game quests and Studio quests, with name/ID/source search, origin and type filters, staged/customized badges, and resumable drafts. Sources sharing one quest identity are grouped; an edited source takes precedence, followed by the package override and then base source. This is a source library, not a claim that every shipped quest is available to every character.

**New quest** opens the guided builder for hunts, item turn-ins or exchanges. **Edit quest** opens that builder for a Studio template, or a full source editor for a game quest. Native quests are never replaced by a simplified template. **Back to quests** preserves unfinished work, and each guided quest has its own draft. Cloning creates a fresh quest identity.

Reviewing a native quest edit includes the original source file, a `custom-quests/studio-source-list.txt` compilation list and any required Dockerfile/context changes. The hook explicitly copies each selected source into the compiler stage and verifies its declared quest's state output. Old compiled handlers for that identity are removed before installing the replacement, so removed events do not linger. Saving retains the original quest name; keep existing state names for characters who already started it. The normal custom-diff update protection tracks edits in the original source, rather than a detached copy. Build validation is still required before an in-game play test.

## Finding items

Every item selector in drops, quests and crafting has **Category**, **Function / type**, **Catalogue scope** and **Sort by** filters. The default scope shows live server definitions, or their cached/offline fallback; **Full catalogue** includes other known IDs. Separate scopes show catalogue-only entries, installed items missing icons and installed unnamed items. Exact numeric ID searches can reveal catalogue-only entries while respecting the field's allowed items and other filters. Quick buttons open **Bonus items**, **Scrolls** and **Potions & buffs** without typing. For example, choose Bonus items → Bonus changer, or Scrolls → Upgrade scroll & protection. Other categories cover equipment, materials, chests, books, stones, tools, fishing and quest items. Shared reward pools have their own category in the drop editor.

Filters combine with name, ID, translated keyword and function searches; separate search words can match different parts of an item. Results show readable types, IDs and known level requirements. **Show more** lets you browse beyond the first 100 results. **Clear filters** resets the search. Category, function and sorting choices are remembered while Studio stays open. Monster selectors also filter Metins, bosses, monsters and NPCs within the field's allowed targets.

Types and properties use the current server catalogue, with a cached snapshot when offline and the bundled seed on a first offline launch. Names and descriptions prefer installed client data; previous labels remain searchable. Missing names and icons are labelled. The catalogue status shows which sources are available, and updates refresh automatically. Browsing and filtering do not modify game files. See [catalogue sources and limits](ITEM_CATALOG.md).

Hover an item in the catalog, a drop row, a crafting row or the quest reward to read its description. Keyboard focus shows the same tooltip; arrow keys browse picker results. Escape dismisses the description first, then the picker on a second press. The tooltip stays open while hovered, fits the viewport and can scroll for longer notes. Browsing never selects or saves an item. Descriptions are also searchable.

The hover card also shows **Configured in N Metins**, up to four Metin names with levels and IDs, and counts for bosses, monsters, known chests and other reward tables. Each target ID counts once, even across several groups or shared-pool routes. Counts reflect saved drop sources, including zero-parameter references (flagged when present); they are not a guarantee of live drops. Unsaved drafts are excluded. The lightweight lookup rereads drop bytes and refreshes its in-memory index after saved files change, without scanning quests or SQL on hover. **Inspect item ↗** opens item details, matching groups and their sources.

Descriptions distinguish bonus changers, bonus adders, fifth-bonus marbles and common scrolls. Recovery amounts and known level requirements come from the installed seed. General mechanics are labeled as a **General Metin2 guide** because Studio does not inspect the running engine or database. Items without reliable details say so. Older catalogue labels called `25041` Magic Stone and `25042` Ritualstein; the installed English data identifies them as Blessing Scroll and Magic Stone respectively. Studio uses those installed names and retains a note about the older mismatch. Game definitions are unchanged.

Description references: installed `item_proto` and package `CHANGELOG.md` (1.23.4), the [Singleplayer wiki entry for 25041](https://metin2singleplayer.com/wiki/#/przedmiot/25041), and the official Metin2 guides for [upgrade items](https://en-wiki.metin2.gameforge.com/index.php/Upgrade_Items), [Enchant Item](https://en-wiki.metin2.gameforge.com/index.php/Enchant_Item), [Reinforce Item](https://en-wiki.metin2.gameforge.com/index.php/Reinforce_Item), [Green Magic](https://en-wiki.metin2.gameforge.com/index.php/Green_Magic), [Green Strength](https://en-wiki.metin2.gameforge.com/index.php/Green_Strength), and [Exorcism Scroll](https://en-wiki.metin2.gameforge.com/index.php/Exorcism_Scroll). Studio serves this help locally and makes no wiki requests when hovering.

## Item explorer: where an item is used

Open **Item explorer** in the sidebar and choose an item with the same search/category filters. **Inspect item ↗** on an existing drop, crafting ingredient/result or quest reward opens the same read-only view. Search, saved items, combined drops, quest rewards and economy tables share the same item icon, name, ID and hover/focus details. The ↗ button beside an item-picker result inspects it without selecting it as a reward. Back retains the underlying search or returns to the source view. A numeric ID absent from the catalog can be inspected directly, which also covers native crafting items missing from the catalog.

The view separates **Drops in**, **Found in chests**, **Reward pools & other tables**, **Can be crafted by**, **Used to craft**, **Sold by NPCs**, **Used in equipment upgrades**, and **Other file references**. It follows explicit shared-pool links, respects Studio's chest source precedence, and shows one shortest matching route per group. The same numeric value in the item and pool namespaces is never treated as the same object. A zero parameter on the displayed route is called out. Only known chest definitions are listed as physical chests; unclassified special reward tables remain in Reward pools & other tables. Route parameters are configuration values, not computed final game probabilities.

Cube recipes show their NPC, ingredients, results, success chance and Yang cost, with a link to the recipe editor. Native crafting relationships use the current database with saved Studio overrides; pending changes need Apply. Shop inventory and refinement relationships use the installed `world.sql` seed and are labeled **DATABASE SEED**. Native window assignments come from `crafting_windows.sql`, and literal NPC handlers in saved quest sources resolve their NPC names. A recipe with no window assignment is shown as a definition whose availability is unconfirmed. Seed references can differ from the running database. If native crafting cannot be read, its references fall back to clearly labelled seeds.

Other file references show exact ID tokens, filenames and line numbers with **Open source** links. They are possible references, not proof of a reward or active quest. For IDs below 1000, only explicit item-related contexts are included to avoid treating every small count/level as an item ID. Compiled/dynamically computed uses and files outside the reported coverage may be missing. File mentions display at most 150 files and four matching lines per file.

Each lookup scans saved sources again; **Refresh references** rereads them after edits. Unsaved drafts are excluded and stay intact while inspecting. Opening another editor is disabled while a draft is dirty. The explorer never saves game files or applies changes.

## Economy dashboard

Open **Economy** in the sidebar. The default is **Regular economy (no GMs) / Whole server / Last 7 days**. Population filters include regular humans and bots, humans only, playerbots only, GM accounts only, everyone including GMs, and unknown ownership. Any account with a character registered in `common.gmlist` is classified as GM, including its other characters and shared storage. If the registry is unavailable, the dashboard does not claim the filtered figures exclude GMs; Everyone remains available for unseparated data. This changes analytics only, not account permissions or gameplay.

Progression filters cover every stage equally. Default view boundaries are early 1–39, mid 40–74 and late/endgame 75+, and **Stage boundaries** changes those view boundaries without editing the game. Log periods are 1, 7 or 28 days. Stock and balances are current snapshots; log totals cover the selected period. Stage attribution uses current character levels, not historical levels. Account storage has known population where its owner is known, but no progression stage.

- **Overview:** character-wallet Yang, account activity, held item units, equipment stock by catalog upgrade grade, completed Yang-only shop turnover, upgrades, matched commodity price movement, stage comparisons, wallet distribution, bank balances and review signals. Listed units require a shop with remaining duration. Accounts are deduplicated within each view; multi-stage accounts can appear in several comparison rows. Activity requires retained CHARACTER/ITEM log activity, not seeded `last_play` timestamps. The GM banner shows the funds kept outside normal views. Unregistered demo accounts are not automatically classified as GMs.
- **Items & demand:** search and category filters, equipment upgrade grades, stock/equipped/listed units, completed sales and median transaction unit prices. Acquisition, use, NPC-sale and destruction counts are explicitly **log records**, not consumption units. Select an item to inspect its sources and uses in Item Explorer.
- **Activities & drops:** Metin/boss kill records and saved drop definitions, target-type/search filters, deduplicated target/pool relationships, and direct links to the drop editor. Configured source counts are not output/hour or production shares. Monster kill counts are unavailable.
- **Save snapshot:** collects fresh data and saves aggregate history only in `<stateDir>/economy.sqlite`. Wallet charts and item stock changes use matching population/stage/period/boundaries and GM-classification version. Earlier mixed snapshots remain accessible under **Earlier snapshots · previous mixed definitions**, but are excluded from the new charts and stock comparisons. A baseline must be at least one minute old. Stock changes can reflect transfers, character stage movement or transformations, not only production/consumption. Studio can collect local snapshots while open; the schedule can be changed in Economy. It does not collect while closed.
- **Event journal:** timestamped local notes for a change, hypothesis and expected result. This does not launch events or alter drops.
- **Export report:** download a **CSV pack** (ZIP, for Excel/LibreOffice) or a complete **JSON report**. The CSV pack includes metrics with units/definitions, every item row in the selected economy view, progression bands, bank balances, mixed global Yang logs by source/day, activity, upgrade methods, saved drop-source definitions, all matching saved snapshots and item stocks, and all journal notes. It also contains the JSON report and a README. Exports include history beyond the chart's 90 points and journal's 50-note display. Earlier mixed definitions have separate legacy tables and retain their original scope. Exports use the selected population/stage/period/boundaries, independent of item search/category/grade/pagination; progression bands, banks, global logs, definitions and journal state their wider scope explicitly. Exporting reads the latest available observation (up to 60 seconds cached) and does not save a snapshot or change game data. With the database offline, saved history/notes remain exportable and live measurements are unavailable.
- **Data coverage:** explains each source and missing measurement, including unknown storage ownership, partial currency logs, trade sampling and missing farming/consumption instrumentation.

The collector uses the existing local Docker Compose MariaDB service. Credentials are expanded inside that container and never returned to the browser or saved in Studio. Queries run in a read-only consistent-snapshot transaction, use a per-statement timeout and a 45-second process limit, and require no database schema changes. A report is cached in memory for up to 60 seconds; **Refresh** bypasses it. Unsupported source schemas are marked unavailable. When the database is stopped, the dashboard still exposes saved history and configured drop definitions, with live figures unavailable.

The **Mixed global Yang logs** panel always includes possible GM activity: `money_log` has no actor identity, so its flows cannot be reliably separated. Signed currency logs have partial coverage and do not establish total inflation. Account and shop banks follow the selected population but remain across all levels. Wallet Yang excludes Won; Won balances are shown separately. Won-denominated sales are excluded from Yang prices/turnover.

Regular, human and bot market statistics exclude a transaction if either its buyer or seller belongs to a GM account. GM-only market statistics include transactions involving either GM party; their stage follows the GM seller if present, otherwise the GM buyer. Every transaction counts once. Everyone includes both. BUY_ITEM shop settlement records are limited to the latest 20,000 entries across the current and preceding equal-length periods; any truncation is reported. Direct trades, historical equipment bonus quality and the origin of past GM gifts now held by regular accounts are not reconstructed.

The commodity comparison uses exact IDs in materials, potions (excluding variable blends), bonus items and scrolls; excludes equipment, books and stones whose quality can vary within one ID; requires five transactions per ID in each period and three matching IDs; and computes an equal-weight geometric price change. It is **not a fixed-basket inflation index**. Upgrade attempts exclude downgrade detail rows; successful-refine item conversions are never counted as destruction. A scroll method alone does not prove protection or exact scroll consumption. Exact net item creation, consumption units, stock coverage days, farming profit/hour, listing sell-through and hours-to-upgrade remain unmeasured rather than being inferred from unsuitable logs.

CSV files use UTF-8 with BOM, comma separators, UTC timestamps and unrounded numeric values. Missing measurements are blank in CSV and `null` in JSON; availability columns and coverage explain the gaps. Formula-like catalog/journal text is escaped for spreadsheet safety; JSON retains the original text. New saved snapshots record available sources; older snapshots without this metadata are labelled accordingly, so stored zeros are not proof of source availability. Snapshot tables join by `snapshot_id`. Downloads contain aggregate data and user-entered journal text, without raw player/account records, logins or credentials.

## Save and apply

1. Edit a target, recipe, quest, setting or file.
2. Select **Review changes** and inspect the exact diff.
3. Select **Save changes**. Studio backs up every original file, checks that it has not changed since review, then replaces it atomically. Multi-file saves roll back completed writes if an ordinary write error occurs. An interrupted save is detected on startup and requires reviewed recovery before further saves or Apply.
4. Select **Apply to server → Build & restart** when ready. This affects saved files only and disconnects players at the restart.

Follow the persistent operation panel for the current stage and elapsed time, even
when moving to another tab. **View progress** opens the stage card and optional
technical log. Failed or unverified operations expose the log; a lost connection
stays unconfirmed until Studio reconnects. The last result remains accessible
through **View last operation** even with no pending changes. Validation results
explicitly leave changes pending and do not restart the game.

Apply builds the game image first. The package’s Linux `qc` compiler checks custom quest source during that build. A failed image build leaves the running game untouched. After building successfully, Studio ensures MariaDB is available, stops the game, recreates the settings migrator, checks that it completed successfully, and recreates the game container. A later migration/start failure can leave the game stopped; inspect the output and the normal launcher before restarting. Wait for the normal launcher to report the game healthy before logging in.

Backups are in `<stateDir>/backups/<change-id>/`, with a manifest and before/after files. An `.env` backup contains the original credentials, so keep this local data folder private. The web app does not serve backups or credential fields, and its `.env` review hides unrelated settings. Configuration backups do not back up characters or the database; use the package’s world-backup feature for that.

## Backups and recovery

Keep two separate backups before the beta:

| Backup | Protects | How to retain it |
| --- | --- | --- |
| Game/world backup | Accounts, characters, inventories and other game/database state | Use the game's own backup tools and restore instructions; confirm you can restore it |
| Studio private state | Drafts, change history, original configuration, applied crafting reconciliation, add-on baselines and journals | Stop Studio after critical work finishes, then preserve its complete `data/` folder; setup prints the selected state path |

Studio's individual configuration/pack backups are useful for their recorded
operations. They are not a database snapshot or a complete game installation.
Retain both the game backup and Studio state when an update or Apply fails.

### Interrupted server save

If Studio closes or loses power during Save, reopening detects incomplete save
journals. **Drafts & changes → Interrupted save recovery → Review recovery**
previews **Restore interrupted save**. Saving, validation and Apply wait for recovery.
Read the proposed file changes before confirming.

Recovery restores original bytes only where the file still matches that save's
attempted replacement. Files changed externally, including a subsequent game
update, are kept. The review checks the observed hashes again before writing.
Original before/after data remains in the backup; do not delete it. If the save
already committed to SQLite, Studio can finish the journal without rewriting game
files. An unresolved/corrupt journal needs private support, not manual database
editing or a guessed rollback.

### Interrupted server Apply

Normal **Stop Studio** and Ctrl+C refuse during critical Apply, game-update or
add-on work; Stop also refuses while a mutation or repository job is active.
An operating-system shutdown or forced process
termination can still interrupt it. On reopening, Studio marks an unfinished
deployment interrupted and shows a warning until a later verified Apply. This
warning is kept separately from the current operation: a successful validation
does not clear it. Studio does not silently retry or restart the game.

Inspect the recorded operation/output, game launcher, any still-running build
commands and current game health before retrying. A failed build may leave the
old game running; interruption after a stop/migration may leave it stopped.
Studio blocks validation and retry while the previously recorded build process
is still running. Wait for it to finish and inspect the outcome; do not launch a
second build from the game's launcher to bypass that guard.

Keep backups and review the saved pending files. Before retrying Apply, the
dialog requires **I checked the game launcher and confirmed that no previous
build command is still running. Retry this interrupted deployment.** Select this
only after doing that check, then deliberately choose **Build & restart**.
The process guard cannot establish what unrelated/external commands are doing,
so this confirmation is still required. If the game/database needs restoration, use its
own backup tools. Do not clear a journal or pending record to make a status look
successful. Contact the supplying maintainer if the last completed step is unclear.

### Interrupted client add-on Apply

Close the selected game client before recovery. **Activity** and add-on settings
show transaction/recovery state. Review the available recovery action and its
target; preserve `<stateDir>/addons/`, including pack baselines and journals.
Recovery must not overwrite a game update with an older pack. External or mixed
pack changes require inspection; clean updated packs use **Review reinstall**.
The game server may stay running because this is a separate client operation.

### Another Studio is already managing this game

A game-installation lock prevents a second Studio from managing the same server
through a different data folder. Close the first Studio after its critical work
finishes and reopen the intended version. Changing the port or creating another
state folder is not a workaround. Do not delete lock files to bypass a live owner.
The game's own launcher remains independent of Studio's locks.

## Package-specific limits

- Item/mob definitions come from the live database and client names/icons from the installed packs. Studio retains a private cache when offline and uses bundled seed/exports before the first successful live read. A definition does not prove in-game obtainability or capture runtime overrides.
- Some Metins drop from shared pools such as `s8001`. **Edit pool contents** opens the actual weighted rewards. Changing a shared pool affects every target that references it. Pool IDs are a separate namespace from item IDs, even when their numbers match.
- Some base percentages exceed 100 in the shipped tables. Studio keeps the parser’s accepted values; those figures are base parameters, not a guarantee of the final in-game probability.
- Existing native-panel drop overrides on Docker’s shared volume can supersede image tables. Resolve those overrides in that panel if the game differs from Studio’s on-disk sources.
- The Dockerfile applies additional package transformations. For example, Moonlight/starter/hexagonal contents and selected Hwang drops can override base files. Use the dedicated chest source in the drop editor for those chests.
- `M2_RATE_EXP`, `M2_RATE_DROP`, and `M2_RATE_YANG` seed a **new world only**. Studio displays them as read-only. Use the package’s current-world Rates page to change the running world’s rates.
- `M2_INVENTORY_SLOTS` describes the panel’s inventory search range; it does not add inventory pages to the client. `M2_MAX_ITEM_COUNT` limits panel writes; it does not change the database column or engine.
- Except for supported native crafting, NPC shop inventory, equipment refinement, item/monster stats, bonuses and most skill definitions use the game package's existing database editor.
- New client models, maps, UI, icons or engine features require client assets or engine work. A config editor cannot create those assets or remove protected engine limits.
- The builder supports hunt, inventory turn-in and exchange templates with optional repeat cooldowns. It does not generate arbitrary dungeon logic, branching stories or translated dialogue. Advanced source editing remains available.
- Launcher updates can replace Dockerfile hooks or package additions. Keep Studio’s backups. Review custom quest integration after updating the package; creating another quest reinstalls a missing hook.
- Advanced file editing preserves the source’s newline convention and legacy bytes, but does not validate every table or arbitrary Lua/quest logic. Review carefully and retain backups. A successful Docker build is not a complete in-game test of every configuration.

## Workspace and update protection

Studio now retains editor drafts across navigation and reload, and offers named **Drafts & changes** sets. Reviewed edits can be staged without touching the installation. Review the complete set to save all its files together, then Apply separately. Use **Review against current files** to rebase a set after an update. **Recover to change set** reconstructs a preserved draft from its cached original source when available; a missing original leaves the draft intact and blocks automatic recovery.

Every new Studio save records original bytes, custom intent and last saved bytes in `<stateDir>/workspace.sqlite`, outside the game directory. Existing edits made before tracking need **Update protection → Track an existing edit from its original backup**. This registers a reviewed difference without rewriting the file. An arbitrary current file cannot reveal its unmodified original.

The game update takes priority initially; Studio then lets you decide how to merge your custom work. Use **Update protection** to check the official package manifest, stage its ZIP, or import a ZIP with its published SHA-256. Staging does not install anything. For example, original scroll parameter 50, custom 100 and game update 80 installs 80 first, while preserving 50/100/80 for the later merge review. Files absent from a package are left alone.

After review, **Install reviewed game files** archives affected original/custom/current files under `<stateDir>/updates/update-custom-*/`, then calls the installation's existing `Invoke-M2PackageUpdate` with the exact staged ZIP and SHA-256. Native validation, protected-package rules and native backups remain in use. Studio verifies the game files and saves a persistent pending custom-merge review. **Apply** can build/run the game update before that merge is decided, using the native launcher's full-stack Start path and without reapplying Studio native-crafting overrides. A failed installation verification still requires recovery; retain Studio state and native backups.

After an external launcher update, use **Scan installed files / pending merges**. **Keep game; decide later** keeps the installed files unchanged and stores the custom merge for later, allowing the game build to proceed. Pending reviews survive Studio restarts and further package updates.

In the later review, conflicting values default to **Use game value**. Choose **Keep my custom value** for selected changes you want back, then **Review selected merge** and save. Unrelated game updates are retained. You can accept the game values instead, or leave the review pending. Resolve a file's pending merge before making another direct edit to that file; use the normal editor afterwards to adapt the selected customisation before Build/Apply. Native crafting has its own review against the updated database. Unsupported add-on integrations can wait for adapter support. Replaced clean client packs can be reviewed as the new baseline for installed add-ons; version coverage warnings alone do not block review. Refresh Pocket Wiki data after content changes. Builder transformations and persistent native-panel drop overrides can affect effective values; runtime drop checks cover accepted active customisations and do not expect deferred custom values to be deployed.

For client add-ons, **Compatibility unverified** means the current version or
profile is outside the publisher's declared coverage, or independent in-game
testing is still pending. It does not mean the add-on is known to be broken.
You can review and apply it to an owned supported test target without changing
version declarations. Details compare current and declared versions. Matching
declarations show **Declared compatible**; **Known incompatibility** needs a
specific recorded problem. Actual package, adapter and ownership failures still
block installation with their reasons.

Saving a reviewed merge leaves its file changes pending **Build/Apply**, even when
the saved contents match an older Studio build. The game launcher may have built
different files since that deployment. Pending saves survive Studio restarts and
clear only after a verified Apply includes them; validation, failed builds and
unverified runtime checks leave them pending. Accepting game values without
rewriting files does not create extra deployment work.

**Validate build only** checks image/quest compilation without restarting the game. Apply records source fingerprints, stage logs and actual game health. Runtime checks also compare saved Studio quest sources with the running image and require their compiled states, using the game account. A healthy Docker daemon alone does not mean the game is healthy. Configuration backups remain separate from database/world backups. All review tokens expire, and stale files are checked again before writes.

The Apply dialog shows current pending changes first. Opening it puts earlier
build results in a collapsed **Previous operation** section. A current validation
result says explicitly that nothing was applied; pending changes require
**Build & restart**. Reopening the dialog refreshes the pending list and resumes
the progress display if an operation is still running.

## Additional editing tools

- **Search everything / Ctrl K:** catalog items, targets, recipes, settings, filenames and optional file contents. Content results open at their matching line.
- **Drops:** source and level filters, contains-item filtering through shared pools, combined configured paths, target comparison, distinct target impact for pools, and reviewed bulk changes to matching direct entries. Weights and base parameters are labelled separately; valid values over 100 remain supported.
- **Quests:** hunt, inventory collection/turn-in and material exchange templates, optional repeat cooldown, player dialogue preview, a source library, template editing and cloning. Changing a saved quest's template requires a new ID to preserve state names. Existing character flags are retained. All three generated templates were compiled with the installed `qc` in a disposable isolated container; rewards and progression still need an in-game play test before use on a live population.
- **Crafting:** table, NPC and output filters; cloning; per-attempt ingredient/Yang comparisons; discovery of additional Lua crafting definitions. Failure material consumption is unverified, so no expected-cost estimate is presented as an engine fact.
- **Items:** effect and restriction details beside references, favourites, recent items, effect comparisons, watchlist actions and current economy detail.
- **Settings:** On/Off controls, numeric input ranges, units, package defaults and custom-difficulty dependencies. New-world rates stay read-only.
- **Files:** in-file search, line numbers, line jump and guided fishing/spawn tables. Guided edits replace selected tokens only, preserving legacy label bytes, delimiters, comments and line endings. Unsupported rows remain read-only in the guided view; advanced source and build validation remain available.

## Economy history and experiments

The Studio service collects a regular-economy/all-levels seven-day observation every 60 minutes by default, with 180 days of retention. Change or disable this under **Economy → History & watchlist**; saving a schedule uses the currently selected scope. Studio must stay running, but its browser can close. Failed observations retain an error and are not replaced with zero. History belongs to Studio's local SQLite database and never changes game data.

Snapshots now retain aggregate item stock, listings, prices, sales, account-owner counts, upgrade-grade access and progression bands. Older snapshots remain compatible and unavailable fields remain blank. Watchlists show matching-scope item history. Saved observations can be compared, while the review queue flags specific evidence (stock growth without sales, substantial commodity price movement, concentrated ownership) for investigation. These are review thresholds, not automatic economic diagnoses or game changes.

The event journal supports structured experiments: save a hypothesis, matching filters, watched items and an optional related change set with a baseline. Capture an outcome after one complete log period to avoid overlapping before/after windows. Activity context is retained; results are associations, not proof that the change caused the result. Current-level cohorts can move between stages.

Owner IDs are used only transiently for aggregate calculations; snapshots/exports contain owner counts and shares, not identities. GM account separation remains in every attributable view. Retained-log coverage shows earliest/latest records and counts, without claiming uninterrupted logging. Native item GET/USE records still do not prove exact production or consumption. New generated quests emit `STUDIO_Q_ITEM` v1 logs measuring inventory count changes around turn-ins and rewards. These cover those quests only; ordinary loot, crafting and refining quantities remain unverified. The protected engine's item hint/step semantics could not be established with the available ELF analysis providers; no speculative parser is enabled.

CSV/JSON exports include ownership, instrumented quest flows, watchlist history, review queue, refinement raw labels, equipment access and experiment baselines/outcomes. Units and missing-data definitions travel with the report. Nothing automatically changes drop rates or rarity.

## Guided editing of normal quests

Open **Quests → Edit quest** to use fields instead of editing Lua. The editor recognises supported literal values in existing quest sources. Coverage varies: some quests have only a level gate or target available as fields. The **Quest section** selector and field search keep large quests manageable. Item and monster selectors use the existing searchable catalog, filters and item descriptions.

- **Biologist research:** required/quest-drop item IDs, successful submission total, submission success, direct completion reward items/quantities and bonus values in the matching `m2_biologist.lua` entry. Item checks/removals/grants/displays share recognised IDs; completion and remaining-count expressions change together. Completion reward edits also affect companion rewards.
- **Hunting:** every active stage from level 2 to 80 has its actual target alternatives, kill counts, Yang, percentage EXP and item rewards. Class-specific armour/helmet options remain available. The final level-999 sentinel and commented stages are preserved.
- **Other native quests:** literal item operations, inventory thresholds, direct Yang/EXP grants, kill targets/counter thresholds, minimum-level gates and constant saved-flag cooldowns. Required quantities link matching stage-local inventory checks and removals. Drop caps and unrecognised calculations may need separate changes; check the review.
- **Shared Biologist wait:** explicitly shared and editable only when world difficulty is custom. Other modes direct you to World settings; Studio never silently switches difficulty.

**Coverage & source files** explains unsupported values. Database-backed `give_reward` tables and computed/random values are not presented as editable file constants. Translated dialogue can contain fixed objective/reward text; changing a field does not automatically rewrite translations. Existing player flags, accepted hunting counts and previously awarded bonuses are not migrated.

Preview re-analyses the current sources and checks every source/dependency hash. Token-span edits preserve other bytes, original encoding and newlines. Changes use the same review, backups, named sets and custom-diff update protection as other editors. Guided drafts retain their original dependency versions and can be recovered into a change set after an update. No game files are written until Save; no game restart happens until Apply.

## Economy while the game is offline

The dashboard reads the running database; game files do not contain live balances. If Docker or the world database is stopped, the banner explains how to reconnect. Overview displays the latest **saved snapshot for exactly the selected population, stage, period and boundaries**, with its capture time. Items & demand provides a searchable saved item table. Missing observations remain unavailable and stale figures are never represented as live. Journal, history, configured drops and exports remain accessible. Start Docker Desktop and the world in the game launcher, then **Refresh** for live data. Studio does not start/restart the game automatically.

## Item icons

Economy’s live and saved item tables, watchlist and review queue use the shared item icon renderer and hover descriptions. Numeric IDs observed in the database can display icons even when the web item catalog does not name them.

Studio reads the installed client's explicit `gamedata/item_list.txt` aliases and original icon pixels from its packs. It converts supported TGA icons into private PNGs and can recover an unambiguous icon through the client's exact original proto name. Explicit missing assets and ambiguous mappings stay labelled **Icon unavailable**. Names, descriptions, mappings and images share the installation-bound `<stateDir>/catalogue/` cache; live item/mob definitions use its server snapshot. Background checks refresh changed sources while keeping the last readable snapshot during interrupted updates or outages. Client packs and game files are unchanged. See [catalogue sources, refresh and offline use](ITEM_CATALOG.md).

An icon that truly has no local image shows a labelled placeholder. Image failures that happen before event listeners attach are handled too, so cached failures cannot leave a broken image in the table.

## Quest hover explanations

Hover a quest row in the library, or focus/click its title, for a plain-language purpose and recognised objectives, required items, targets, rewards, levels and waiting times. Custom Studio quests use their saved template values; native quests reuse the guided field recogniser. Biologist previews include linked submission totals/chances and completion rewards from the matching shared helper. Hunting previews explain target alternatives and percentage EXP, with the first stage as an example. Database-backed or calculated rewards are labelled as incomplete; intermediate item grants are not promised as completion rewards.

Descriptions read saved sources plus the active change set, not unsaved drafts or character progress. They are cached briefly and refreshed when returning to the library. The card supports keyboard focus, scrolling and Escape dismissal; title clicks also work without hover. This feature changes only Studio and needs no game Apply.

## Configuration navigation

The sidebar groups gameplay editors under **Game configuration** and history, drafts and update protection under **Studio tools**. Groups can collapse; Studio remembers their state for each installation and opens the active group when following a link.

**World settings** opens a topic menu: World & features, Progression & difficulty, Drops & economy, and Bots & population. **Config files** groups sources into drops, crafting/shops, maps/spawns, items/fishing/alchemy, quests/helpers, skills/events and other overrides. Each topic has counts, search and quick topic navigation; All settings/All files remain available. Maps additionally filter by map folder. Search from a topic menu searches every topic. Unknown file categories remain reachable under Other and All files.

Switching topics preserves settings together in one draft and review; file drafts are restored when reopening their file. Deep links, browser Back/Forward, global search and draft resume open the appropriate editor. These navigation changes require refreshing Studio, with no game Apply.

## Quest file permissions

Apply verifies compiled quest files as the game account. Unreadable files leave a deployment unverified even when Docker health passes. The custom-quest build hook preserves readable/executable directory permissions.

## Guided custom quest flow

Generated hunts, inventory turn-ins and exchanges now use the package's native `target.vid` and quest letters. Eligible players receive an availability letter and giver marker; accepting removes that marker. Hunt dialogue and the progress letter use `mob_name(target)` and the saved kill count. Turn-ins name the required item with `item_name` and show the current inventory count. Return letters name the selected return NPC, show the objective/reward and add its marker. Markers resolve when that NPC exists on the player's current map, matching native quest behavior.

Markers support the same target-click and ordinary NPC-chat routes as game quests. Return guidance appears on entering the reward state and on subsequent logins/letters, so finishing a hunt immediately directs the player back. Hand-in clears the target and letter. Repeated quests schedule their availability again after the saved cooldown; one-time completions stay complete. No character flags are reset by upgrading a template.

The builder's Player dialogue preview now presents availability, objective/progress and return stages. Saving an older Studio quest regenerates this guidance while preserving its ID and existing state names. An already completed character will not receive it again; clone with a new ID or use another character to test from the beginning. Engine and client binaries are unchanged.

Validation compiled all three templates with/without cooldowns and the existing saved quest using the installed Linux `qc`. The actual compiled handlers were then exercised with `tests/quest_guidance.lua` in an isolated Lua 5.1 runner with mocked quest APIs: level eligibility, decline/accept, named objectives, target clicks, unrelated kills, inventory guards, rewards, marker cleanup and cooldown reavailability. This does not visually verify NPC/minimap rendering in the game client. The existing quest's compiled state IDs were identical before/after.

## Crafting access, removal and rollback

The recipe editor supports both existing systems: **Cube** and native **`crafting.open(...)`** windows. New recipe creation starts with an NPC chooser and automatically selects the system behind that NPC's existing dialogue. In the inspected 2.2.106 installation there are 26 identified NPCs: Seon-Pyeong (20091) uses Cube and 25 NPCs use native windows, including the Blacksmith, Baek-Go, Octavio, Heuk-Young, Stable Boy, Battle Bailiffs, Min-Sun, Nakajima and alchemists. The General Store Saleswoman (9003) has no crafting menu identified and is excluded. NPC access conditions such as herbalism, level, story or guild ownership are retained. A route does not prove that the NPC is spawned in the player's current map or that their character meets its requirements.

The default list shows active crafting recipes. **Legacy Cube · menu unconfirmed** exposes old table entries separately; these are not proof of an accessible game menu. They are retained, can be removed/reviewed, and can be cloned to an active NPC. Search and filters work across both systems. The installed item definitions supplement the compact catalog so native potion and scroll items have searchable names too.

Assigning Seon-Pyeong uses his separate appended recipe table. The native Docker build forbids his recipes in the base `cube.txt`, so moving an existing recipe reviews both table changes and checks both original hashes. New recipes default to a compatible NPC/table. Discovery does not prove that a player's level, quest gates or map make every dialogue available; reload Studio's catalog after external package/compiled-object updates.

Native recipes come from the current `world.crafting_proto` and `world.crafting_window` tables, rather than database seeds. Ingredients, one reward item type, quantities, chance, Yang cost, minimum level and learning requirements have guided controls. `recipe_vnum` is a learning-progress key, not an item ID. Higher existing `crafting_price<recipe>` event flags can set a price floor. NPCs sharing a window share its list; a definition used in multiple windows shows a warning. Clone it for an independent definition. **Remove from NPC** removes only that window link, retaining other windows and existing game definitions. A Studio-created definition is removed when its last window is removed; creating then removing it before Apply leaves no pending change. Native creation allocates an unused recipe ID at review, checked again at Apply.

Saving native edits writes only `linux-port/docker/game/share-add/studio-crafting.json`, a Studio-owned data configuration with backups, drafts, change sets, history rollback and update protection. It adds no game script, engine or client functionality. Apply runs the existing build/migration flow, stops the game, merges only customised database columns and window links in an InnoDB transaction, verifies the result, and restarts. For a full native package update, its launcher completes first, then Studio stops/restarts the game around applying native craft customisations. Validation never writes crafting rows. SQL guards lock and compare all observed affected rows before writing; a race or error rejects/rolls back the transaction and leaves the game stopped. Database deployment is recorded separately so a failed restart is safely retryable.

External changes to untouched native fields are retained. Changes to customised fields require **Review crafting conflicts**, choosing **Keep Studio value** or **Accept server value**, then reviewing and saving. Only those conflicts are presented. Studio does not silently overwrite them. A missing externally deleted definition or a new external window referencing a Studio-created recipe blocks automatic destructive recovery with an explanation. Keep `<stateDir>/workspace.sqlite` alongside the Studio configuration and backups; it records the last applied native changes needed for field-level reconciliation and rollback.

The top bar shows **Apply changes (N)** for pending saved files (plus a pending native package update), and **No pending changes (0)** when everything matches the last verified deployment. Unsaved/preserved drafts and staged changes are excluded. Clicking a nonzero counter opens the existing file review/build/restart dialog. Apply is also rejected server-side when there are no saved changes, preventing an unnecessary restart. An in-progress operation remains accessible through the same control.

Open a saved recipe and choose **Remove recipe** to review removal of just its section, preserving all other bytes. Studio-created quests have **Remove** in the library and **Remove quest** in their builder. This removes their saved source; Apply rebuilds without their compiled handlers. Package quests are retained because they can include shared game systems. Existing player flags, earned rewards and previously crafted items remain in the database. Re-creating/restoring the same quest ID keeps its old progress.

Change history defaults to **Gameplay changes** for recipe, quest, drop and EXP/settings edits. **Update reconciliations** holds game-update merges and native crafting conflict resolutions; **All changes** shows both. Existing records are retained. Newer edits in either category can block a rollback.

The **Change type** selector narrows the selected category to quests, crafting,
drops, world settings, maps and spawns, shops, fishing, alchemy, items, skills,
events or other server files. Counts show the matching saves. A save that touches
several types appears under each relevant filter, with its types listed in the
row. This includes older backups. Select **All types** and **All changes** to see
the complete timeline available in history. A type filter does not split a save:
rollback still reviews and restores all of its files.

For rollback, open **Studio tools → Change history → Review rollback**, inspect the diff, then **Revert saved changes**. Apply separately to load the reverted files. Restores operate on all files in that saved change; newer edits in the same files must be reverted first. Blocked rows show the reason. A rollback/removal gets its own backup and can itself be undone. With a working change set selected, the review stages the reversal there instead of writing game files immediately.

Saved rollbacks and removals remain visible as pending Apply even when they eliminate the tracked custom diff or delete a newly created quest. Deployment fingerprints include those paths until successfully deployed. Management checks cover compatible-NPC filtering, table routing and stale guards, byte-preserving recipe removal/restore, custom quest removal/restore, staging, history eligibility and pending-deployment tracking. Browser tests exercised the controls against a disposable installation only.
