# Changelog

## Unreleased

- Keep atlas hover details beside the creature list without covering the map.
- Add one-click mobs, bosses, Metins, mining ores and NPC filters with counts.
- Include installed mining spawn additions and prevent duplicate ore zones.

## beta-1.18.0

- Replace Studio’s Economy analytics with shortcuts to the game dashboard.
- Remove the duplicate collector and disable old schedules; preserve existing
  history and notes with a read-only SQLite archive download.
- Remove retired analytics UI, exports, tests and CSS; detach native crafting
  database access and stop adding economy-only logs to new quest templates.

## beta-1.17.0

- Reduce explanatory copy and collect Economy methodology under one disclosure.
- Speed up Economy’s active-account query by deduplicating logged characters;
  retain the last matching observation while refreshing, including after reload.
- Sync creature portraits and category badges from the installed client wiki pack.
- Filter crafting and quests by custom content, including edited game definitions.
- Filter the atlas by creature type, name or ID. Hover or focus to isolate a
  creature’s zones and preview its level, portrait and configured drops; click to pin.
- Include regular and random-group spawns in Studio’s atlas, keep the spawn list
  tall, and retain the existing boss/Metin scope of in-game atlas exports.

- Use one item identity renderer across search, drops, crafting, quest rewards,
  saved items and economy tables, with shared icon fallback and hover/focus help.
- Keep Server Apply progress visible across tabs, expose observed deployment
  stages and elapsed time, and retain clear results with optional technical logs.
- Keep error notifications above dialogs until dismissed. Preserve unknown
  operation status on connection loss and expose the last result without a new save.

- Open Item explorer directly into the catalogue. Keep favourites/recent items
  under Saved items and preserve the current search, filters, pagination, scroll
  and focus when returning from item details.
- Show configured weapon damage, armour defence and fixed bonuses in hover,
  item details and comparisons. Read English bonus labels and native point
  mappings from the installed package.
- Read/cache the deployed Dragon Stone balance and client quality labels. Show
  calculated base effects separately from possible random rolls, with quality,
  strength, scaling and coverage notes; never substitute the stale host table.

- Load the shared item/mob catalogue from the live server database and installed
  client packs at startup. Refresh stable client/package updates automatically
  and poll live definitions without restarting the game.
- Keep installation-bound server/client caches and generated icon PNGs for
  offline use. Report live, cached and bundled fallback sources in Studio.
- Use the same snapshot for Studio editors, Pocket Wiki exports and atlas names.
  Mark installed wiki reference data when its catalogue revision is outdated.
- Read original client icon pixels directly, including true-colour and RLE TGA,
  without requiring another package or modifying game files.
- Retry brief Windows folder sharing locks when promoting verified add-on
  downloads into the local cache; persistent permission errors still fail.

- Prefer installed English item names over stale catalogue labels and label
  unresolved names explicitly. Preserve previous names as searchable aliases.
- Default item pickers to installed seed definitions, with full catalogue,
  catalogue-only, missing-icon and unnamed-item filters. Exact ID searches remain
  available within the field's allowed items.
- Recover unambiguous shared-name icons from client proto data, support icon
  paths containing spaces and stop substituting obsolete icons when the client
  explicitly names a missing asset. Known missing icons render placeholders.
- Document catalogue sources and limits without changing game definitions.

- Added combined add-on install/update reviews, selected/all package controls,
  one pack rebuild and one recoverable transaction, with an optional client
  reopen after the complete batch succeeds.
- Added live installed-file checks, missing-file/reinstall statuses and a main
  Studio notice. Reviewed repair preserves settings and current game updates.
- Added the installed add-on manager screenshot to the main README.

- Focused the main README on startup, architecture and feature examples. Detailed
  add-on, setup, storage, update/backup and development guides are linked from it.

- Organized Python application code under `src/metin2_studio/`, Windows helpers
  under `scripts/windows/`, and release configuration under `config/`.
- Added the shared `studio.py serve` / `studio.py setup` entry point while keeping
  the familiar Windows launch buttons and the existing private data location.
- Updated creator tools, documentation links, portable packaging and CI for the
  new layout; added launch checks from an unrelated working directory and a
  freshly extracted ZIP.
- Brief Windows sharing locks during add-on state replacement and legacy data
  migration now receive a bounded retry. Failed writes still preserve the previous
  file and report the error; unrelated permission failures are returned immediately.

Older entries describe behavior at that release. See the README and latest entry
for the current normal-client and game-update workflow.

## beta-1.11.0

- Added a recorded exact-executable adapter profile for client 2.0.114, observed
  with server 2.2.110. Isolated actual-pack and native atlas/menu/wiki/input
  lifecycle checks passed; logged-in gameplay remains independent acceptance.
- Added journalled interrupted-save detection and reviewed recovery, retaining
  external/game-update edits and blocking further saves/Apply until resolved.
- Stop Studio refuses during critical deployment/update/add-on work. Startup
  records unfinished deployments as interrupted instead of silently losing them
  or replaying a build/restart. Warnings survive validation; a recorded running
  build blocks retry/validation, and retry requires a launcher/build confirmation.
- Added game-installation locking across Studio copies using separate state
  folders, while retaining existing state-folder locks.
- Prepared a small-beta scope, operator recovery/tester checklist, current
  normal-client documentation, root MIT license and private support/security/
  contribution guidance. Public repository/history review and independent human
  acceptance remain separate gates; no publication or invitation is performed.

## alpha-1.10.1

- The Apply dialog now leads with current pending changes. Previous build results
  have a separate collapsed section; validation explicitly leaves changes pending
  and does not restart the game. Both actions are blocked while an operation starts.
- Added a Change type filter alongside history categories, including quests,
  crafting, drops, world settings, maps, shops and other content areas. Mixed saves
  appear under every affected type. Existing backups and full-save rollback guards
  are preserved.

## alpha-1.10.0

- Added Add-on Menu as the first bundled add-on. Its in-game Add-ons button lists
  installed extensions and opens windows or the native atlas, with paging and
  disabled, automatic and unavailable states. Removing it retains other add-ons.
- Added read-only installed metadata and open actions to client API v2. Opening
  an already visible window raises it without toggling it closed.
- Default descriptions now have readable usage, shortcut, settings and coverage
  sections with safe headings and lists.
- Change history separates gameplay edits from game-update reconciliations, with
  an All changes view. Existing backups are classified without rewriting them;
  rollbacks retain their category and guards against newer edits in either group.


## alpha-1.9.0

- Add-ons now apply to the normal supported game client, with reviewed changes,
  pack backups and transaction recovery. No extra playable copy is required.
- Moved optional sandbox/copy creation under Advanced testing tools. Exact
  client process and executable checks protect pack writes while it is open.
- Clean game-pack replacements offer a manual reapply review against the new
  game baseline. Settings survive; removal restores that updated baseline and
  failed reapply restores current game files. Mixed external changes stay blocked.
- Added normal-client lifecycle, update/reapply, stale-review, failure recovery
  and UI coverage.

## alpha-1.8.4

- Version/profile declarations now describe compatibility coverage. Unlisted
  versions show Compatibility unverified and permit reviewed installation;
  missing declarations and experimental integrations carry the same warning.
- Added separate compatibility badges, current-versus-declared version details,
  and clear distinctions between publisher declarations and recorded failures.
  Existing adapter, package, dependency and ownership blockers remain.
- Updated installed compatibility after game updates without trapping disable
  or removal. A target changing during review still requires a fresh review.
- Added manager, pack integration and UI tests for version differences, warnings,
  installation/removal, evidence-based labels and retained safety checks.

## alpha-1.8.3

- Saved merges remain pending until a verified Apply deploys them, including
  merges that restore bytes from an older Studio build after a game update.
  Validation, failed builds and unverified runtime checks do not clear that work.
- Runtime verification now checks saved Studio quest source hashes and compiled
  quest states as the game account. Missing or stale custom quest output leaves
  Apply unverified. Deferred game-first quest integration remains optional.
- Added regressions for external updates, restart persistence, unsuccessful
  deployment attempts, accepting game values and compiled quest verification.

## alpha-1.8.2

- Corrected update priority to install the game first and let the user merge
  preserved custom work afterwards. Package installation never restores a merge
  automatically, and no longer discards custom intent.
- Pending merges retain original/custom/game values across restarts and further
  updates. Conflicts default to the game value; explicit review can select custom
  changes while keeping unrelated updates. Added Keep game; decide later.
- Deferred merges do not gate the native game build or runtime verification.
  A pending package build does not reapply Studio native-crafting overrides.
- Added deferred-state, repeated-update, explicit-merge, game-build and UI tests.

## alpha-1.8.1

- Made the game authoritative during package updates and installed-file recovery.
  Supplied game files retain their update values; old Studio overrides are retired
  instead of being restored. Files absent from a package are left alone.
- Archived displaced original/custom/current files privately before invoking the
  native updater. Separate compatibility review can recover prior work later.
- Removed custom-value restoration controls from game-update reviews. Staged new
  work retains its own explicit merge review. Added regression and UI coverage.

## alpha-1.8.0

- Bundled Pocket Wiki with in-game crafting, upgrade chains, configured sources
  and uses, native wiki links, bookmarks/history, pinned cards and attempt costs.
- Added API v2 lifecycle, independent windows, guarded shortcuts, world-local
  preferences and reference data, preserving API-v1 atlas add-ons.
- Added structured reference snapshots with provenance and reviewed refresh.
  Current native snapshots exclude pending Studio overrides; configuration and
  seed references retain their coverage labels.
- Added owned playable test copies for the recorded executable. Original client
  installations remain read only; executable drift blocks test-copy writes.
- Added correctness, lifecycle, refresh/removal and native UI checks. Native
  harness results remain distinct from connected interactive gameplay.

## alpha-1.3.0

- Added local add-on ZIP import directly in Discover, using the shared package cache and reviewed install/update flow.
- Added filename/checksum details and removal from the local catalog while retaining installed code and recovery data.
- Added creator runtime/HTTP fixtures and an actual-pack creator-workflow rehearsal with exact restoration.
- Adopted user-selected source trust; removed publisher verification badges and certification/signing launch requirements.
- Live client writes, browser/gameplay acceptance, independent creator trials and optional shared catalog hosting remain separate work.

## alpha-1.2.0

- Added explicit HTTPS repository subscriptions, stable/prerelease channels, manual update discovery and separate download/install reviews.
- Added bounded archive validation, immutable archive checksums, cached offline selection, withdrawal checks and explicit source-switch acknowledgement.
- Added creator scaffolding, artifact creation/inspection, static catalog generation, experimental API v1 and dependency version comparisons.
- Added typed settings controls and retained installed details/settings when a source disappears.
- Added a redacted support report and a fresh-upstream-baseline fixture rehearsal.
- Documented precise acceptance status and drafted community launch/maintenance responsibilities.
- Public catalog hosting, browser acceptance and interactive gameplay remain pending. Live client packs remain read only.

## alpha-1.1.0

- Integrated Add-on Hub into the existing Studio service and navigation.
- Added world-bound sandbox management, shared session authorization, atlas-to-editor links and combined activity.
- Added optional local pack dependencies, safe history-copy migration and authenticated shutdown.
- Preserved server deployment and add-on recovery as separate workflows.
- Live client writes and interactive gameplay validation remain unavailable.

## beta-1.0.0

First distributable beta of Metin2 Singleplayer Studio.

- Portable setup for an existing supported Linux/Docker server installation, with a folder picker, package checks, remembered port and per-world data.
- Windows start/stop launchers, optional desktop shortcut, Python launcher detection and safeguards when a port belongs to another world.
- Searchable item catalog, descriptions, icons and item-usage exploration.
- Drop/chest editors, configuration submenus, quest library and guided/custom quest builders.
- Cube and native crafting at existing NPCs, automatic system selection and guarded database application with conflict review.
- Economy views, GM separation, local history, journal and CSV/JSON exports.
- Drafts, change sets, backed-up saves and rollbacks, custom-difference update protection and a pending Apply counter.
- Installation/operator documentation, tests, CI and a clean portable release ZIP with SHA-256 checksum.

Game package compatibility was locally checked on 2.2.106. The game, client assets, credentials, world data and local Studio history are not distributed.
