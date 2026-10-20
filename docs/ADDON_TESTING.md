# Merged verification

## Current beta verification

The current workflow installs into a supported normal game client with reviewed
pack writes, backups and recovery. It does not require another playable copy.
Test code that mutates packs or simulates failures uses disposable fixtures;
native harnesses use an explicitly prepared test client. Preserve normal game
packs and private Studio state when collecting evidence.

Run the commands in [Development and verification](DEVELOPMENT.md#development-and-verification)
for the complete current test list. Optional codec checks require **Install Add-on
Support.bat**. Game-dependent suites need the supported installation; skips must
be recorded rather than counted as successful gameplay checks. Current beta
scope and human acceptance are in [BETA_REVIEW.md](BETA_REVIEW.md).

Server recovery/shutdown/game-lock fixtures separately exercise interrupted
saves, completed SQLite receipts, newer external files, interrupted deployments,
critical-operation Stop refusal and two Studios with different state folders
targeting the same game. These checks must not force-crash a real world.

The 18 October 2026 extracted beta-1.11.0 regression run passed 411 Python tests
with one Windows symlink-permission skip, and all 86 JavaScript tests. Fresh
setup/start/reuse/stop and private-state retention passed on a disposable server
fixture. This is historical evidence; the [current validation record](BETA_REVIEW.md#validation)
records the latest checks and remaining acceptance work.

### Client 2.0.114 evidence — 18 October 2026

The current recorded profile is
[`src/metin2_studio/addons/profiles/tieru-2.0.114.json`](../src/metin2_studio/addons/profiles/tieru-2.0.114.json),
id **tieru-mt2009-client-2.0.114**, observed with server **2.2.110**. Its exact
executable SHA-256 and observed source-pack fingerprints are recorded there.

An isolated actual-pack rehearsal passed codec roundtrip, coexistence of all four
default add-ons, settings, disable/enable and exact uninstall restoration. The
native harness imported the shipped game/atlas lifecycle hooks, exercised
Ctrl+U → Pocket Wiki, Add-on Menu → Pocket Wiki, reference navigation and window
lifecycle, and constructed/disposed 12 Boss Atlas widgets plus one Atlas Legend
widget.

Atlas geometry uses synthetic dimensions and installed spawn configuration.
These are native startup/widget/input/lifecycle checks in an owned isolated
fixture. No character login, server connection, independent human trial,
cross-resolution acceptance or interactive gameplay is claimed. They establish
bounded adapter evidence, not a guarantee for arbitrary pack or game changes.

The historical evidence below records the versions tested then. In particular,
alpha-1.7/1.8 read-only-source tests describe that earlier sandbox workflow;
normal-client installation has been supported since alpha-1.9.0. Historical
timings, counts and browser availability are not current compatibility claims.

## Pocket Wiki (alpha-1.8.0)

`test_pocket_wiki.py` verifies structured parsing, saved-file isolation, current
native rows, search/upgrade cycles, attempt totals, bookmarks/history, preference
recovery, lifecycle/input handling, playable-copy guards, stale reviewed data and
exact removal. The HTTP tests also request every imported add-on module, including
`addon_jobs.mjs`, which was missing from the static route allowlist.

The copied-client harness `tools/check_pocket_native.py --run` recorded all three
bundled add-ons, the actual shipped game-module bootstrap, native windows,
bookmarks, scrollable pinned cards, native-wiki deep links and close/reopen. A live
read-only snapshot exported 273 recipes / 2,662 upgrades for the inspected world;
the labelled seed fallback exported 246 recipes. Native first-open timing was
approximately 0.3 seconds. Exact timings and reports remain private under data/.

Browser verification exercised bundled discovery, source-data review and the
original-client write block, plus creation/installation into an owned playable
copy. A harness with a synthetic game window is not a connected gameplay test.

The earlier acceptance history follows. Use the current README commands above
when checking a new candidate rather than this historical subset.

Run from the project folder after installing optional pack support:

```powershell
python tools/check_project.py
python -m unittest discover -s tests -t . -v
node --test tests/catalog.test.js tests/icons.test.js tests/navigation.test.js tests/quest_help.test.js tests/addons.test.mjs tests/addons_view.test.mjs tests/addon_jobs.test.mjs
python tools/validate_addon.py src/metin2_studio/addons/catalog/community.boss-atlas src/metin2_studio/addons/catalog/community.map-legend
```

Existing installed-data integration suites run only when `METIN2_STUDIO_SERVER_ROOT` points to the supported existing server. They copy source files into disposable fixtures before mutation. The game assets are not bundled. Optional codec tests skip when its wheel is missing; installing support enables those checks. The symlink-escape test skips on Windows hosts that disallow unprivileged symlinks.

The original merge checks exercised shared Studio-token authorization,
cross-origin refusal, world-bound targets, the then-read-only source-client gate,
pack transactions, exact restoration, missing-dependency atlas access and
persistent activity after target switching. Migration checks validate copied
SQLite records and backup bytes, reject a foreign world and preserve original
source data. Current normal-client lifecycle/reapply checks supplement these
earlier sandbox tests.

With the merged development app running on its separate local port:

```powershell
python tools/check_merged_integration.py --url http://127.0.0.1:8780
```

This checks the actual merged service using only a verified owned, non-playable
fixture of root packs. It inspects normal-client support without applying there,
reviews and installs both atlas examples in the fixture, configures Boss Atlas,
disables/enables Atlas Legend, removes both and compares exact pack fingerprints.
It also verifies atlas-to-file lookup and unchanged server drafts/activity. The
previous connection is restored even on failure. Use `--sandbox` to reuse an
empty owned fixture. Native execution is a separate check. Reports are private
and excluded from releases.

A real run passed the seven-operation lifecycle on the 1,341-entry source packs, with 29 configured maps, exact restoration and source preservation. This is HTTP/API verification, not a browser click-through. Node view tests use DOM boundary mocks; they are not visual browser evidence. Browser layout, keyboard interaction, narrow viewports and dialogs still need visual acceptance because no browser was connected.

The profile in `src/metin2_studio/addons/profiles/tieru-2.0.112.json` records the earlier native startup/import/widget smoke for the unchanged runtime/example source. No interactive play test or new native gameplay test is claimed by this merge. Real map alignment, map transitions and performance remain outstanding.

The source builder uses `config/release-files.txt` and excludes private state, wheels, test copies, game packs, keys and executables. Inspect and validate a fresh extraction before sharing. No public release is created automatically.

## Repository and creator verification

`test_addon_repositories.py` covers artifact reproducibility, traversal/alias/link/case/size rejection, checksum and manifest identity failures, strict JSON, non-execution of payloads, immutable published versions, source changes/collisions, withdrawal, cached offline selection, dependency comparisons and SemVer precedence. Transport fixtures check DNS refusal, pinned public addresses, TLS hostname retention and unsafe redirects. A separate read-only production-fetcher check successfully retrieved public GitHub repository metadata with normal TLS verification; package distribution scenarios use deterministic injected network fixtures, not a live hosted catalog.

The HTTP integration fixture exercises the real shared Handler/session/origin boundary through subscribe → review → download → install → configure → discover/download update → apply update → withdraw → remove source → uninstall. It verifies that download alone leaves installation unchanged, settings survive update, withdrawn code cannot be enabled, server activity remains intact and both source/sandbox packs restore exactly. The new-baseline fixture separately preserves upstream fixes while retaining the previous sandbox; it is a rehearsal of an explicit fresh target, not automatic installed-state rebasing.

Support report tests assert that fixture paths, Studio tokens, settings, repository query secrets, publisher names and raw URLs do not enter the allowlisted report. UI boundary tests verify typed settings parsing, source controls, escaped metadata, retained installed details and the separate support export. These remain DOM mocks, not visual evidence.

Creator tools and remote downloads do not require optional codec wheels. Pack rebuilding does. No automatic public upload, release signing, real community moderation, independent creator trial or in-game acceptance is asserted by these tests.

## Local creator workflow

`test_http_local_creator_import_install_update_and_exact_removal` exercises authenticated binary upload, Unicode filenames, wrong-origin/session/content-type/size refusal, import without installation, review invalidation, settings preservation, service reopening, disable/enable, catalog removal and exact uninstall. Service tests reject incomplete bodies and active server deployments. Archive fixtures also cover local iteration, source switches, stale cache failures and legacy repository records. The generated creator scaffold is explicitly executed in a synthetic runtime test to check map events and settings; imported third-party payloads are not executed by Studio.

With this project’s merged app running, use:

```powershell
python tools/check_creator_workflow.py --url http://127.0.0.1:8780
```

This runs eight creator CLI commands and eight reviewed lifecycle actions against an owned copy of actual packs. It verifies two-addon coexistence, retained settings, exact restoration, unchanged source packs/server drafts/history and cleanup of its catalog selection. It reconnects the previous target after success. Failed rehearsals preserve test state for inspection. This developer rehearsal does not replace an independent creator’s trial or interactive gameplay.

## Direct GitHub workflow (alpha-1.4.0)

`test_addon_github.py` uses controlled responses for GitHub metadata, releases, commit resolution, raw files and source archives. It checks separate release/development channels, commit-pinned downloads, moved-tag observations, unchanged-package branch commits, failed checks, stale reviews, offline caches, source changes, missing/mismatched manifests, bounded responses and declared-file corruption/links/case collisions. Normalization ignores undeclared build scripts; package preparation never imports payload code.

The shared HTTP integration test also exercises wrong-session/origin refusal, review invalidation, update discovery/download/apply, failure retention and reopening with installed revision/settings intact. It removes the source before uninstalling and restores both synthetic pack files exactly.

Run `python tools/check_github_workflow.py` against the selected world's actual packs (or pass `--server-root`). It launches its own temporary loopback service, injects controlled GitHub responses only in that process, and creates a fresh private state directory and owned pack sandbox. It does not add a fixture endpoint or alter the normal Studio instance. The actual-pack run passed all eight lifecycle actions in 33.49 seconds, preserving the second add-on, settings, source packs and server workspace. Private evidence is in `data/github-workflow-result.json`.

A separate live production-transport probe read `octocat/Hello-World` metadata, resolved its default branch, retrieved a pinned raw README and source ZIP, and rejected the repository's unsupported add-on layout. This validates the real GitHub endpoints/TLS independently from fixture installation; it does not claim installation from a live hosted add-on repository. Browser layout, interactive gameplay and an independent human creator trial are still pending.

## Background repository jobs (alpha-1.5.0)

`test_addon_jobs.py` deliberately stalls fixture network reads and checks that add-on state/catalog and the Studio lock remain available. The real HTTP boundary accepts a job with 202, refuses foreign origins/sessions, serves read-only pages and a server preference mutation while a request is stalled, and permits cooperative cancellation. Other fixtures cover cancellation after cache validation without selecting that payload, stale external metadata, failed enqueue/checks, cached catalog selection, review expiry, interrupted restart and bounded persisted history. Transport callbacks report actual byte counts and close the connection when cancellation is raised.

`addon_jobs.test.mjs` checks polling through terminal outcomes, navigation during requests/intervals, reconnect errors and unknown-size transfers. DOM fixtures check returning to an active job, mutation controls/cancellation and escaped interruption errors. These are not visual browser checks; no browser was connected.

`tools/check_github_workflow.py` now submits all nine network operations through the background job API. Its actual-pack rehearsal passed the eight install/settings/update/coexistence/disable/enable/remove actions in 33.65 seconds, retained settings/revisions across reopening and restored the source/sandbox pair exactly. The original game and server workspace were unchanged. Cache cleanup and independent setup/gameplay acceptance remain pending.

## Manual update notices (alpha-1.6.0)

`test_addon_updates.py` covers read-only changelog computation, multiple skipped versions, explicit selection versus installed state, source/channel matching, local same-version changes, stale offline results and development notes/content comparison. Job fixtures verify that all-source checks skip disabled sources, report partial errors and discard prepared metadata on cancellation. DOM tests verify update counts, escaped notes, Not now, separate review actions and that the Check button only submits metadata work.

The actual-pack background HTTP rehearsal now checks `/updates` before a remote check, asserts no network request occurs from that read, and verifies the manual batch check adds no archive request. Changelogs become available while the installed revision stays unchanged, the notice remains after explicit download, and it disappears after explicit installation apply. All nine network jobs and eight lifecycle actions passed in 33.82 seconds with retained settings, source revisions, coexistence, unchanged source/server workspace and exact copied-pack restoration. No visual/browser or new in-game gameplay acceptance is claimed.

## GitHub collection repositories (alpha-1.7.0)

`test_addon_collections.py` covers two members sharing a commit, equal versions at different commits, independent release notes/updates/settings/enabled state, development snapshots that change one member, selected-only normalization, historical folder moves/offline cache selection, README fallback, removed members, root-to-collection conversion and immutable version observations after subscription removal. Invalid ids, ambiguous/case-colliding folders, traversal, declaration/archive mismatches and undeclared sibling sentinels exercise the format boundaries. The creator collection validator reads package bytes without executing code.

The integration suite submits collection operations through the shared HTTP/background-job routes and verifies independent lifecycle actions and exact synthetic-pack restoration. DOM fixtures show two member cards and folder labels, and review only the selected member. These are boundary tests, not visual browser checks.

Run `python tools/check_collection_workflow.py` with the selected server (or `--server-root`). It creates a fresh private state directory and sandbox of actual game packs and injects controlled GitHub responses only into its temporary local service. The actual-pack rehearsal passed eight install/configure/disable/enable/update/remove actions in 33.29 seconds. It verified separate cache records at a shared commit, no sibling auto-selection/install, per-member settings/enabled state, metadata-only manual update/changelog behavior, retained paths/revisions across reopening, removal after unsubscribing and exact pack restoration. Source packs and server workspace remained unchanged. Private evidence is in `data/collection-workflow-result.json`. No live hosted collection installation, independent human trial or new gameplay/visual acceptance is claimed.
