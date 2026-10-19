# beta-1.16.0 — consistent items and visible operation feedback

Search, drops, crafting, quest rewards, saved items and economy tables share one
item renderer, catalogue names, icon fallback, and hover/focus help. Combined drop
sources, recipe comparisons and guided quest fields now show the same identities.
Inspecting an editor item returns to its source; explorer Back retains its results.

Server Apply has a persistent status banner and a progress card at the top of its
dialog. Stages come from the running commands, with elapsed time and a completed
stage count rather than an estimated percentage. Results remain available while
switching tabs; failures expose their logs, lost connections stay unconfirmed,
and newer saved changes remain explicitly pending. Last results remain accessible
even with no new changes. Error notifications stay above dialogs until dismissed.

The deployment commands, validation boundary and game update review remain the
same. See [shared interface patterns](INTERFACE_PATTERNS.md) for implementation
and verification boundaries.

## beta-1.15.0 — direct item exploration and configured effects

Item explorer opens the catalogue immediately. Saved items opens favourites and
recent history when wanted. Selecting an item leaves the results beneath its
details; Back, Close and Escape return to the same search and scroll position.
Header and footer Back controls remain available on long reference pages.

Hover cards, details and comparisons show configured weapon attack ranges, armour
defence and fixed item bonuses. English bonus labels and native point mappings
come from the installed package. Dragon Stone effects use the deployed server
table, rather than the older host copy that this game's build replaces. Calculated
base effects, quality/strength and possible random bonus rolls are shown separately.
The shared catalogue caches the last successfully read table for offline use and
exports the same description data to add-on references. Previews are not rolled
inventory items; unsupported balance entries remain explicitly unavailable.

## beta-1.14.0 — shared live catalogue and offline cache

Studio reads current item and mob definitions from the running server in a bounded
read-only transaction at startup. Installed client packs supply English names,
descriptions and original icon pixels. The same snapshot feeds Studio editors,
search, Pocket Wiki reference exports and atlas names.

Stable local file changes are checked every 15 seconds; live definitions are
checked every minute. Open dashboards receive changed data through the regular
status refresh while retaining editor drafts. Interrupted client updates keep
the previous readable snapshot. A last successful installation-bound cache keeps
names, properties and generated icons available when the server or client packs
are unavailable. Without a cache, bundled exports/seed definitions are labelled
as fallback data. No check starts or restarts the game.

Pocket Wiki installations retain their in-client snapshot until a reviewed
reference-data refresh. Its details show when the catalogue revision has changed;
new reviews use the shared current catalogue. Client pack writes still require
closing the game and follow the existing recovery and transaction rules.

## beta-1.13.0 — clearer item names and catalogue coverage

Item pickers start with the definitions bundled with the installed server. The
full catalogue and direct numeric ID search remain available; catalogue-only,
missing-icon and unnamed-item filters make incomplete entries easy to inspect.
This scope reads the seed definitions, not the running database or player inventory.

Installed English names replace stale catalogue labels. Previous labels remain
searchable, and unresolved names display their numeric ID. Icon resolution now
handles paths containing spaces and unambiguous original-name mappings in the
client proto. Explicit missing client assets cannot silently borrow obsolete
catalogue icons. Missing assets keep a labelled placeholder.

These changes affect Studio's display and private derived cache. Game files,
item IDs, add-ons and saved crafts are unchanged. See the
[item catalogue guide](ITEM_CATALOG.md) for sources and remaining limits.

## beta-1.12.0 — batch add-on installation and one client reopen

Discover add-ons supports selecting several packages or reviewing every ready
bundled/downloaded package together. Installed add-ons can review all ready
updates in one step. One combined preview checks dependencies and ownership for
the final group; one Apply builds the packs once and commits one recoverable
transaction. Saved settings and disabled preferences are preserved.

The review can optionally open the supported game client once after all changes
succeed. This starts unchecked, never closes a running game and avoids opening
a second copy. A launch failure is reported separately from the successful
installation. The server can stay running.

The main README includes a real add-on manager screenshot.

## beta-1.11.1 — detect missing add-ons and review reinstalls

Studio checks the current client pack fingerprints against the last successful
add-on installation. Missing payloads or loading hooks show **Needs reinstall**;
unexpected edits and unreadable packs show their own status. Saved enabled
preferences and settings remain available independently of the file status.

The main Studio screen shows when add-on files need attention. Add-on pages
check local files every 15 seconds while visible and when returning to the page.
The main screen checks alongside its regular status refresh and on window focus.
Checks inspect local files only and never automatically install or download.

**Review reinstall** uses updated clean game packs as the new baseline after a
game update. For isolated missing owned files or loading hooks reverted to the
known baseline, a reviewed repair restores the saved installation. Unexpected
manual edits remain blocked. Missing or unreadable game packs require repair
through the game launcher first. The client must be closed before applying;
the game server can stay running. Pack backups and transaction recovery remain
in effect.

## beta-1.11.0 — small beta candidate

This candidate adds recovery for interrupted server saves, visible interrupted
deployment state, critical-operation shutdown guards and a lock shared by Studio
instances targeting the same game installation. Recovery keeps subsequent game
updates/external edits and requires a fresh review before restoring attempted
writes. Startup never silently retries an interrupted Apply.

An interrupted-deployment warning survives validation and later Studio restarts.
Validation/retry wait while the recorded previous build process is running.
Before retrying Apply, confirm in the dialog that you checked the game launcher
and that no previous build command is still running.

The initial game target is server **2.2.110** / client **2.0.114** on Windows with
64-bit Python **3.13**. A recorded exact-executable client profile is included,
with isolated pack roundtrip, all-four-add-on coexistence, exact restoration and
native atlas/menu/wiki/window/input checks. Exact adapter checks remain required.
This is distinct from logged-in gameplay and independent tester or creator
acceptance; see the [beta checklist](BETA_REVIEW.md).

The README, operator guide and roadmap now describe normal-client installation,
API v2, current compatibility wording, recovery and backup boundaries. Root MIT
licensing covers original Studio material; game and third-party rights remain
separate. Support, security reporting and contribution guidance are included.

Preserve the complete private Studio data folder when updating and retain a
separate game/world database backup. Stop Studio after critical work completes,
update the Studio files and restart it. Updating Studio does not automatically
deploy server configuration, reapply client add-ons or restart the game.

No repository has been published, release tag pushed or Discord invitation sent
as part of preparing this local candidate. Actual repository history/CI logs and
public reporting channels must be reviewed before a later public launch.

# alpha-1.10.1

The entries below are release history. Older sandbox-only/read-only policies
describe those versions; current normal-client behavior is documented above and
in the README.

The Apply dialog shows whether current saved changes are still pending. Previous
build and validation results are separate and collapsed when opening the dialog.
Validation clearly reports that it did not apply changes or restart the game.

Change history has a **Change type** filter for quests, crafting, drops, world
settings, maps, shops, fishing, alchemy, items, skills, events and other server
files. It combines with the existing Gameplay changes / Update reconciliations
views. Mixed saves appear under each affected type; rollback still covers every
file in that save and checks newer changes across all filters. Existing backups
are classified when read without rewriting them.

These are Studio changes. Refresh Studio; no game rebuild or client add-on
reinstallation is required.

# alpha-1.10.0

Install **Add-on Menu**, the first bundled add-on, to get an **Add-ons** button
inside your normal game client. Click it after entering a character, then open
Pocket Wiki or an atlas overlay from the list. The list shows installed, disabled,
automatic and unavailable extensions and supports paging. The menu itself is an
ordinary optional add-on; disabling/removing it leaves other add-ons installed.
Client API v2 now exposes read-only launcher metadata and registered open actions.

Default add-on descriptions have separate usage, shortcut, settings and coverage
sections. Change history now has **Gameplay changes**, **Update reconciliations**
and **All changes** views. Recipe/EXP/settings edits stay distinct from game-update
merges. Existing records and backups are retained; rollback checks newer edits
across both groups and retains the original operation's category.

# alpha-1.9.0

Apply client add-ons to the normal game client you already launch. Close the
client, review the file plan, apply it and start the game as usual. The server
can remain running. Studio retains pack-file backups and journalled recovery;
no extra playable client is needed. Optional development copies and sandboxes
remain under Advanced testing tools.

When a game update replaces the managed packs with clean game files, Studio
shows Review reapply. Your current game files become the proposed baseline;
installed add-on code/settings are composed over it only after explicit review
and Apply. Removing all add-ons restores the updated baseline, and failed
reapply restores the new game files. Mixed external edits remain conflicts.
Unknown executable integrations or changed hook structures need adapter support;
the game's own update and launch paths remain independent.

# alpha-1.8.4

Compatibility unverified replaces the incorrect incompatibility claim when a
game/client version or profile is absent from the publisher's declared lists.
That warning does not block reviewed installation on an owned supported target.
Manifest versions need not be changed merely to try an add-on after a game update.
Details explain current and declared versions; installed compatibility is shown
separately from enabled/disabled state. Matching declarations are labelled
Declared compatible, with no claim of independent in-game verification. The
Known incompatibility label requires a recorded specific reason.

Package integrity, adapter structure, executable identity, dependency and file
ownership checks remain in force. Game/client changes during an open review
invalidate it so the current warnings can be reviewed before applying. Version
differences alone no longer prevent disabling or removing installed add-ons.

# alpha-1.8.3

Fixed a pending-Apply count that could drop to zero after reviewing a game update.
Saving a merge can restore exactly the bytes used by an older Studio deployment,
but the native launcher may have rebuilt the game without that customisation in
the meantime. Saved file changes now remain pending until a verified Apply
includes them. The record survives Studio restarts; validation, failed builds and
unverified runtime checks retain it. Accepting game values without rewriting
files does not create extra deployment work.

Runtime checks verify saved Studio quest source hashes and nonempty compiled
states as the game account. Healthy containers with missing or stale custom quest
output no longer count as successful deployments. Deferred integration does not
gate the game's own update build.

# alpha-1.8.2

Corrected the update policy: install and run the game update first, then decide
how to merge custom work in Studio. Original/custom/game values remain in a
persistent pending review instead of discarding custom intent. Conflicts default
to the game value; an explicit later merge can restore selected custom changes
while preserving unrelated game updates. Keep game; decide later leaves the
updated files intact and keeps the review available across restarts and further
updates. The overview links to pending merges.

Deferred merges do not gate the native game build or runtime verification. A
pending game-package build does not reapply Studio native-crafting overrides.
Those changes can be reviewed separately against the updated database. Existing
package validation, backups, file guards and original-client protection remain.

# alpha-1.8.1 (superseded update policy)

Game updates take priority over Studio customisations and add-ons. Package
installation uses the game's supplied values and archives affected custom files
under the world's private `updates/update-custom-*/` folder before invoking the
native updater. Studio does not restore old custom values over the installed
package. Files absent from a package are left alone. Installed-file recovery
accepts current game values and retires affected override intent.

Client integration remains optional and confined to owned copies. Unknown client
executables need a compatible Studio adapter before add-on writes can resume;
the original game and its launcher remain independent. Native crafting conflicts
pause Studio writes rather than overwrite changed game data. Prior custom work
can be reviewed later as a separate edit against the updated game.

# alpha-1.8.0

Added bundled Pocket Wiki, API v2 windows, locally generated reference snapshots
and owned playable test copies. Native startup/widgets were checked separately
from connected character gameplay, which remains pending.

# alpha-1.7.0

One public GitHub repository can now expose several independent add-ons through root `addons.json`. Each listed folder keeps the existing `addon.json`/payload format and appears separately in Discover. Download, installation, settings, enabled state, removal, update notices and changelogs belong to each member. Selecting one never selects or installs its siblings; updates remain manual.

Creators can scaffold member folders, generate/validate collections with the CLI and publish per-add-on GitHub Releases tagged `<full-addon-id>/v<version>`. The README documents the complete workflow. Reviews show the selected folder, pin its commit/declaration/manifest, and normalize only that member's files. Separate cache keys support members sharing a commit/version; historical release paths and installed provenance remain intact. Root single-add-on repositories and local ZIP/catalog sources continue working.

Controlled fixtures, UI DOM tests and a real shared-HTTP/background-job rehearsal on actual copied packs verify independent lifecycle/update behavior and exact restoration. Original game packs and the server workspace remain unchanged. No live hosted collection installation or public publication occurred. Browser visual acceptance, gameplay, independent creator/setup trials and cache inspection/pruning remain pending.

# alpha-1.6.0

Available add-on updates now appear in Installed, the add-on toolbar and Studio overview. Read the cached changelog with installed/available versions and source revisions before choosing whether to download. Known intermediate release notes are included, development/local packages use manifest notes, and missing notes are shown explicitly. Notes render as escaped text.

Updates are always manual. Check for updates only reads metadata from enabled sources and reports partial failures; it never downloads an add-on archive or changes installed code. Reading a changelog is read only. Download and installation remain separate choices, and notifications remain until explicit apply. Source/channel matching prevents unrelated repository packages from being advertised as installed updates.

Unit/DOM/concurrency/HTTP and copied-pack checks cover this policy, changelog access and staged-versus-installed behavior. Original game files remain unchanged. Cache inspection/pruning, browser visual acceptance, gameplay and independent creator/setup trials remain pending. This is a local source release; no public hosting/publishing occurred.

# alpha-1.5.0

Repository checks, download reviews and downloads now run in background jobs from the interface. See the current step and transfer byte counts, request cancellation, and keep navigating Studio while network requests wait. Returning to add-on pages or refreshing reconnects to the current job. One job runs at a time; other add-on changes wait for consistent reviews/selections.

Prepared metadata is published only if repository state still matches. Cancelled work discards selections, failed checks retain existing code/settings, and restarting marks unfinished work interrupted without replaying it. Twenty private job summaries are retained without request inputs or result bodies. Download reviews remain temporary, and installation still requires a separate reviewed sandbox plan. Existing synchronous API routes remain compatible.

Concurrency, real loopback HTTP and UI polling fixtures passed. The actual-pack background GitHub rehearsal passed nine network jobs and eight lifecycle actions, preserving settings, the second add-on, original game packs and server workspace, with exact copied-pack restoration. Browser visual acceptance, gameplay and independent creator/setup trials remain pending. Cache inspection/pruning is the next engineering item.

# alpha-1.4.0

Add a public GitHub repository directly in Repositories. Studio discovers matching SemVer GitHub Releases, offers the default branch through an explicit Development channel, and shows a commit-pinned download review with the source README. Creators keep root addon.json and declared payload files; separate ZIP uploads and catalog JSON are optional.

Source snapshots are normalized through the existing package validator/cache without running build scripts or payloads. Installation and updates still require their own reviewed sandbox plan. Installed records retain their applied revision and settings until an update is applied. Failed checks/downloads retain existing payloads; moved published tags, source switches and cached offline selections use the existing repository controls. Users decide which sources/publishers to trust; no verification or account service was added.

Controlled provider/API fixtures and an actual-pack HTTP rehearsal passed install, coexistence, settings, update, service reopening, disable/enable and exact removal. Production HTTPS separately read public GitHub metadata, pinned raw content and a pinned archive. No public add-on repository was created or installed in that probe. The original game remains unchanged.

The creator README and repository guide now explain direct GitHub installation, release tags, layout, limits and offline behavior. Browser visual acceptance, interactive gameplay and independent creator/setup trials remain pending. Live client packs remain read only. This is a local source release, with no public hosting or publishing.

# alpha-1.3.0 (earlier)

Import a locally built add-on ZIP directly from Discover, inspect the package source/checksum and use the same reviewed install/update flow as repository releases. Importing never installs automatically. Local iteration preserves installed settings and previous payloads until an update is applied. Remove from catalog forgets only the selection and retains installed code, cached bytes and recovery data.

The platform standardizes packages, integration and file changes. Users decide which publishers and sources to trust. Publisher certification, verification badges and mandatory signing are outside scope. No account or repository hosting is needed to try a local add-on.

Creator runtime/HTTP fixtures and a copied-pack workflow rehearse import, coexistence, settings, update, disable/enable and exact removal. Browser visual acceptance, interactive gameplay and independent creator/setup trials remain pending. Live clients remain read only; pack sandboxes are not runnable games. Public discovery hosting is optional future work.

Use Install Studio.bat and Start Studio.bat beside an existing supported game installation. Preserve private state/backups when updating. This source ZIP excludes game packs, keys, databases, caches and runtime wheels. See docs/ADDON_ROADMAP.md for acceptance status.

# alpha-1.2.0 (earlier)

Merged Metin2 Studio with an add-on repository client and creator toolkit. This is a local source package; no public catalog or release has been published.

Subscribe to creator HTTPS catalogs, choose stable/prerelease channels and manually check updates. Review source/version/archive checksums before downloading. Downloads are verified and cached without running code; installing or updating an owned pack sandbox requires its own reviewed plan. Installed payloads/settings survive source removal and can still be configured, disabled or removed. Publisher names describe the source; trust decisions belong to the user.

Creator commands scaffold API v1, validate original payloads, build/inspect deterministic archives and generate static catalog metadata. Typed settings, dependency comparisons, immutable release checks, withdrawal controls, offline cached selection and an allowlisted support report are included.

Regression, HTTP fixture and copied-pack lifecycle checks passed with exact restoration and source preservation. Browser visual acceptance, interactive gameplay/performance and independent creator/setup trials remain pending. Live clients remain read only; pack sandboxes are not runnable games. See `docs/ADDON_ROADMAP.md` for the full acceptance status and remaining community/trust work.

Use Install Studio.bat and Start Studio.bat beside an existing supported game installation. Server editors/atlas and creator tools use standard Python; pack rebuilding needs the optional pinned-wheel installer. Preserve private Studio state and backups when updating. The source ZIP excludes game packs, keys, private databases, caches and runtime wheels. `SHA256SUMS.txt` identifies its exact bytes.

# beta-1.0.0 (earlier standalone Studio)

First distributable beta: a local Studio for your existing Metin2 Singleplayer Linux/Docker server.

Download and extract the portable ZIP, install Python 3.10+, run **Install Studio.bat** and choose your existing **Serwer** folder. Then use **Start Studio.bat** or the desktop shortcut. Setup does not install the game or modify/restart it. No pip/npm packages are required.

Includes drop/chest editing, item search/descriptions/usage, existing and new quests, Cube/native NPC crafting, economy views/exports, backups/rollback, custom update conflict review and pending Apply counts.

Compatibility: Windows 10/11; game package 2.2.106 was used for local integration checks. This is not a universal editor for arbitrary Metin2 distributions. Keep a game backup and preserve Studio's private `data/` folder when updating. New quest scripts and actual game changes remain opt-in through Review, Save and Apply.

The ZIP contains Studio source only. Game assets, credentials, databases and local history are excluded. `SHA256SUMS.txt` lists the portable ZIP checksum. Full installation steps, troubleshooting and limitations are in README.md.
