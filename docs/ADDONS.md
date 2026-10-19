# Add-on guide

[Back to the overview](../README.md#see-what-you-can-do) · [All documentation](README.md)

This guide covers **beta-1.12.0**: installing, configuring, updating and removing
client add-ons, plus creating and sharing your own. Choose authors and sources
you trust; add-ons run with the game client's permissions.

For players: [bundled add-ons](#bundled-add-ons) · [install and manage](#install-and-manage) · [GitHub sources](#install-from-github) · [updates](#see-updates-and-read-the-changelog).

For creators: [package requirements](#developer-package-requirements) · [API v2 windows](#api-v2-windows-shortcuts-and-add-on-menu) · [first add-on](#create-your-first-add-on) · [edit and build](#edit-and-build) · [collections](#publish-a-collection-from-one-repository).

## How add-ons work

An add-on extends the game's client interface with Python modules, a manifest and
declared files. Studio checks the package, shows the proposed changes, and installs
its files and shared runtime integration into the client's root packs. The game
loads that code when you launch it. **Installed add-ons work with Studio closed**;
Studio is needed again to manage them or refresh their generated reference data.

## Bundled add-ons

These examples are bundled with Studio; you choose which to install:

| Add-on | What it adds inside the game | How to open it after installation |
| --- | --- | --- |
| **Add-on Menu** | One in-game list of installed add-ons, with actions to open windows or atlas overlays. Disabled and unavailable entries are identified. It is listed first and can be disabled or removed like any other add-on. | Click **Add-ons** near the top-left of the game screen after entering a character. No shortcut is required. |
| **Boss Atlas** | Boss and optional Metin spawn areas, names and base respawn ranges from the installed server's configuration. These describe configured zones, not live boss presence or a live countdown. | Open the game's normal atlas map; enabled overlays appear on it. |
| **Atlas Legend** | A compact atlas label explaining that the displayed zones come from configuration. It demonstrates independent add-ons sharing the same atlas hooks. | Open the game's normal atlas map; the label appears at the bottom. |
| **Pocket Wiki** | Searchable crafts, upgrade chains, ingredient sources and reverse uses, plus bookmarks, history, attempt-cost totals and pinned recipe cards. See [usage and data coverage](POCKET_WIKI.md). | Enter a character, then click **Pocket Wiki** near the top-left of the game screen or press **Ctrl+U** with chat closed. |

Install **Add-on Menu** to open your installed extensions from one in-game button. It is optional: other add-ons retain their own controls when it is disabled or removed.

The **World atlas** page in Studio is also available in the browser. It links
configured spawns to the corresponding drop editor and saved map files. Installing
an in-game atlas add-on is a separate choice.

## Install and manage

1. Run **Install Add-on Support.bat** once and restart Studio if pack support is not installed.
2. Open **Add-on settings**, select **Normal game client**, and close that client. The game server can stay running; no extra playable copy is required.
3. Open **Discover add-ons**, choose an add-on, and select **Review install**. Read its source, compatibility notes and file changes, then **Apply** that plan.
4. Launch the game using your usual shortcut, enter a character, and use the add-on's button, shortcut or existing game window listed above. Studio retains backups of the changed pack files.

Use **Installed add-ons** to review settings changes, enable/disable an add-on,
update it or remove it. Removing the last add-on restores the current captured
game-pack baseline. **Repositories** manages package sources; **Activity** shows
operations and recovery records. Optional pack sandboxes and playable copies are
under **Add-on settings → Advanced testing tools**.

**Opening Pocket Wiki:** first install and enable **Pocket Wiki** itself; installing
Boss Atlas or downloading a package does not install it. After Apply, launch the
selected client again and use the **Pocket Wiki** button or **Ctrl+U** in-game.
Change **Shortcut** or **Show button** under **Installed add-ons → Pocket Wiki →
Details**, then review/apply with the client closed and launch it again. Game key
bindings and focused chat/input take priority over add-on shortcuts.

**Add-on Apply changes client packs. Server Apply builds and restarts the server.**
Each has its own review. Installing a client add-on does not deploy a quest or
restart the server. API v1 provides atlas callbacks; API v2 also supports standalone
windows, shortcuts and local preferences. Add-ons run with the game client's
permissions, so choose packages you trust.

World and Pocket Wiki data are generated from local game sources during a reviewed
operation. They are snapshots, not a live connection to Studio or a complete view
of every engine rule. Refresh reference data after content changes. If a game
update replaces the managed packs with clean game files, **Review reinstall** uses
the new files as the proposed baseline and retains your installed add-on settings.
Nothing is reapplied automatically; see [game updates](UPDATES_AND_BACKUPS.md#updating-the-game-or-studio).

## Missing add-ons and reinstalls

Studio checks client pack fingerprints against the last successful installation.
The **Client files** column shows **Needs reinstall** when saved add-on files or
loading hooks are missing. The enabled switch remains your saved preference;
it does not prove that the files are still present in the game.

Add-on pages check every 15 seconds while visible and when you return to Studio.
A notice also appears on the main screen when files need attention. These checks
read local files and never download or reinstall automatically.

Choose **Review reinstall**, close the game client, review the proposed changes,
and apply. A clean game update becomes the new baseline. Isolated deleted add-on
files or hooks reverted to the known baseline can be repaired from the saved
installation, keeping settings and pack backups. Unexpected manual changes are
shown for review and block repair. If whole game packs are missing or unreadable,
repair the game through its launcher first, then return to Studio. The server can
stay running throughout add-on repair.

## Install or update several add-ons together

In **Discover add-ons**, select the packages you want and choose **Review selected**,
or choose **Review all** for every bundled or downloaded package ready to install
or update. The installed page also offers **Review all ready updates**. Repository
releases need to be downloaded and verified before they join an installation batch.

The preview lists each add-on and the combined file changes. Dependencies and
ownership are checked for the whole group, and existing settings and disabled
preferences are preserved. One **Apply batch** builds the client packs once and
uses one transaction with backups; a failed write rolls back the whole group.

Close the game client once before applying. Tick **Open the game client once
after all changes succeed** to reopen the supported normal client or playable
copy after the complete batch succeeds. This option starts unchecked. Studio
does not close a running game for you. A client that is already open is not
started a second time. If reopening fails, the successful installation is kept
and Studio reports the separate launch error. The server can stay running.

After a clean game update, **Review reinstall** already covers all saved add-ons
in one transaction. You can also combine newly selected packages with that
updated baseline through the batch workflow.

## Package sources

| Installation source | Available now? | What you provide |
| --- | --- | --- |
| Local package | Yes | A `.m2addon.zip` built with the creator CLI |
| HTTPS catalog | Yes | The URL of a Studio-format catalog JSON file |
| Public GitHub repository | Yes | A public repository URL with root `addon.json`, or `addons.json` listing separate add-on folders |

GitHub sources use the same manifest/payload format; creators do not need an uploaded add-on ZIP or a hosted catalog. Arbitrary projects must adopt this layout. The local ZIP importer accepts creator-tool `.m2addon.zip` packages, rather than generic GitHub Download ZIP archives.

## Install from GitHub

1. Set up Studio and optional pack support as described below, then select **Normal game client** in **Add-on settings** and close that client.
2. Open **Repositories**, paste the public `https://github.com/owner/repository` URL and choose **Stable releases**. Adding reads metadata and the README; it does not install code.
3. Open **Discover → Repository releases → Review download**. Review the version, source reference, full pinned commit, manifest checksum and README. README content is shown as text.
4. Choose **Download and verify**. Studio fetches the pinned source archive, verifies the manifest and declared payload hashes, and stages a normal package. It ignores undeclared development files and never runs repository build/install scripts.
5. Review and apply the separate installation plan. For later versions, **Check for updates**, review/download the release, then review/apply an update. Downloading alone leaves installed code and settings unchanged.

For a repository without a published release, explicitly choose **Development branch (GitHub)** and check the repository. Development snapshots track the default branch; they remain separate from stable/prerelease updates. The review pins one commit even if the branch advances before download. Installed details retain the installed revision until you apply a changed package.

Only public GitHub repositories are supported; no account or access token is used. GitHub API limits can require retrying later. Failed checks retain the last valid metadata, installed code and settings; already cached versions can be selected offline. Read the [repository guide](ADDON_REPOSITORIES.md) for limits and source controls.

## See updates and read the changelog

**Compatibility unverified** means the current version/profile is outside the
publisher's declared coverage, or in-game verification is still pending. It is a
warning: you can review and apply the add-on to a supported game client
without editing its version lists. Details show your current versions and the
publisher's declarations. **Declared compatible** records a matching declaration,
not independent proof. **Known incompatibility** requires a specific recorded
problem. Actual adapter, package, dependency and file ownership checks still
block operations they cannot safely perform.

Add-on updates are always manual. Open **Installed add-ons → Check for updates** to check enabled sources. The background job fetches metadata only, reports individual source failures and never downloads an add-on archive or applies code. Disabled sources are skipped. No startup timer, remote polling or automatic update option is enabled.

Available updates show installed/available versions and **Read changelog**. Studio also shows a count in its overview and add-on toolbar. The changelog contains known release notes since the installed version, or the notes of an imported/selected package. Read it and choose **Not now**, **Review download**, or—after selecting the package—**Review installation changes**. Downloading alone keeps the notification and installed code/settings unchanged. Apply the reviewed plan separately when ready.

Notifications follow the installed repository source and selected channel. Competing, disabled or blocked sources are not advertised as repository updates. Failed checks retain last-known notes with a warning and block uncached downloads. Development snapshots compare package content, so a README-only commit does not create a reinstall notice. Imported same-version changes are shown as selected package changes for review.

Changelogs are displayed as escaped text. Published GitHub Releases use their release body; development/local packages use manifest `release_notes`. Include useful changes, compatibility changes and migration/removal notes when publishing. A missing changelog is shown as missing; Studio does not invent one. Known release history is limited by the provider/catalog (up to the first 50 GitHub release records).

Opening Installed, the add-on toolbar or Studio overview reads cached metadata; it does not contact publishers.

## Progress, cancellation and interrupted requests

Repository checks, download reviews and downloads run in the background. The status panel shows the current step and received bytes when available; **Cancel** requests cancellation. Navigation, server editors and read-only add-on views remain available. Studio allows one repository job at a time and pauses other add-on changes until it finishes, so reviews and selections stay consistent.

Cancellation waits for the current network read to return (up to the transport timeout), then discards prepared metadata/selections. Already validated cache files may remain on disk; no installation is applied. Starting a job invalidates older installation plans and consumes its download review. Make a fresh review after a cancelled download.

Reopen an add-on page or use **Refresh** to reconnect to running work. If Studio itself stops, unfinished jobs are marked interrupted on startup and are never automatically retried. Check the source/current selection and review again. The last 20 job summaries are retained privately; review bodies and request inputs are not persisted in job history. Completed download reviews expire on restart or repository changes.

## Install a package someone shared

1. Set up Studio beside your existing supported game with **Install Studio.bat**, then **Start Studio.bat**.
2. To enable pack rebuilding, run **Install Add-on Support.bat** once and restart Studio. It requires 64-bit Python 3.11+ and installs optional dependencies into Studio's own `.vendor` folder.
3. Open **Add-on settings**, select **Normal game client**, and close that client before applying changes.
4. Open **Discover add-ons → Import package** and choose the creator's `.m2addon.zip`. Inspect the description, author, version, compatibility, package filename and checksum.
5. Choose **Review install**, inspect the proposed file changes and any conflicts, then apply that plan.

Import validates and adds the package to the local catalog. Installation is a separate action. Changes apply to the selected normal game client with pack backups. Open the game as usual afterwards. If a game update replaces clean packs, review reapplying installed add-ons against the new baseline; Studio never automatically restores old game packs.

In **Installed add-ons**, open **Details** to review settings changes, use the switch to review disable/enable, or choose removal to review an uninstall. Import a newer build to expose **Review update**; installed code stays unchanged until you apply it, and compatible saved settings are retained. A changed settings schema can require adjusting settings before the update is valid.

**Remove from catalog** forgets a local package selection. It retains installed code, cached bytes and recovery data; uninstall remains a separate action in Installed. Existing installed settings remain editable after the catalog selection is removed. To select that local package again, import its ZIP again.

## Developer package requirements

Studio reads an `addon.json` manifest and the payload files it declares. The
current package type is **client-python**: Python extensions loaded inside the
game client. Server quests use Studio's separate server-editing workflow.

For a single add-on, use this layout at the source repository's root:

```text
my-addon/
  addon.json
  README.md          # recommended: usage, opening controls and tested versions
  payload/
    my_addon.py
```

| Requirement | What to provide |
| --- | --- |
| Manifest format | `schema_version: 1`. `api_version` accepts `1` or `2`; omission means API v1. Use API v2 for standalone windows and Add-on Menu window actions. |
| Identity and metadata | A stable unique lowercase id such as `yourname.example`; `name`, `version`, `description`, `author` and `category`. Use a SemVer version such as `0.1.0` for packaging and releases. Explain how to open the add-on and its shortcuts in the description. |
| Package and entry point | `kind: "client-python"` and an `entry` such as `m2hub_addons.my_addon`. Include that module in the declared files and implement `def register(context):` in it. |
| Declared files | A nonempty `files` array. Each entry has `source` relative to `payload/`, `target` below `m2hub_addons/`, and the lowercase SHA-256 checksum of those exact source bytes. For example, `my_addon.py` installs as `m2hub_addons/my_addon.py`. Refresh hashes after every payload edit. |
| Dependencies and capabilities | Supply `requires`, `conflicts` and `capabilities` arrays, even when empty. Dependencies name add-on ids; optional `dependency_versions` constrains required versions. Required add-ons must be installed and enabled separately. |
| Client code | Use Python 2.7-compatible syntax for the supported embedded client. Studio's Python 3 requirement applies to its manager and creator tools. Use the runtime context for shared hooks; Studio owns the game integration. |
| Optional configuration | `settings` and `settings_schema` describe reviewed installation settings. `compatibility` declares client/server versions and profiles covered by the publisher. Include a license and release notes before sharing. |

Use unique module and asset names. Packages cannot replace game/framework files
or an entire root pack. Paths must be relative, use `/`, and avoid traversal,
symbolic links and case collisions. Limits are 16 MiB per payload file, 64 MiB of
payload, 2,048 declared files and a 256 KiB manifest. The [manifest schema](../src/metin2_studio/addons/schemas/addon.schema.json)
helps editors; the creator CLI/package loader performs the authoritative checks.

Compatibility declarations describe coverage. An unlisted version/profile or
`experimental: true` produces **Compatibility unverified**, which still permits
reviewed installation on a supported client. Matching declarations mean
**Declared compatible**, not independently proven compatibility. Actual adapter,
API, dependency, integrity and file-ownership failures can still block an install;
**Known incompatibility** requires a concrete recorded problem.

## API v2: windows, shortcuts and Add-on Menu

The scaffold below starts with API v1 atlas events. For an independent game window,
set these fields in its existing `addon.json` (this is a manifest fragment):

```json
{
  "api_version": 2,
  "capabilities": ["ui.window"]
}
```

Implement your window using the game's UI controls, then register a lazy factory
in your entry module. Here `ExampleWindow` is your own window class, accepting the
runtime context and game window:

```python
def register(context):
    context.register_window(
        'main',
        lambda game: ExampleWindow(context, game),
        shortcut='NONE'
    )
```

- The factory runs when the player opens the window. Its result must provide
  `IsShow()`, `Open()`, `Close()` and `Destroy()`. Window names are unique within
  an add-on. `Destroy()` must clean up owned widgets and references; the host calls
  it when the game session closes or a created window fails.
- With **Add-on Menu** installed and enabled, a successfully loaded add-on's
  registered window appears as an opening action automatically. The menu is
  optional. Keep a visible route in your add-on when players do not use it;
  `register_window` returns a handle whose `toggle()` can be wired to your button.
- Supported shortcut values are `NONE`, `CTRL_U` and `F12`. Start with `NONE` to
  avoid competing for a shortcut. Duplicate add-on shortcuts are refused; game
  bindings and focused chat/IME inputs take priority.
- Use `context.on('game.open', callback)` and `context.on('game.close', callback)`
  for your launcher widgets; callbacks receive the game window. The host owns
  shared lifecycle and input hooks, so add-ons should register callbacks rather
  than patching those methods themselves.
- API v2 also provides `context.load_state()` / `save_state(object)` for up to
  32 KiB of personal preferences per world/add-on, `context.reference()` for the
  generated local knowledge snapshot, and `context.module(...)` for namespaced
  helpers. Add the descriptive `preferences.local` or `knowledge.read`
  capabilities when using those services. Manifest settings remain a separate
  reviewed pack operation.

Capabilities describe integration needs; they do not sandbox Python permissions.
See the [API v2 reference](ADDON_API_V2.md) for the full contract and launcher
APIs, and [Pocket Wiki's entry module](../src/metin2_studio/addons/catalog/community.pocket-wiki/payload/pocket_wiki.py)
for a complete window, launcher button and registration example.

## Create your first add-on

Run from the Studio folder with Python 3.10+. Scaffolding, validation, packaging and inspection do not need optional pack dependencies.

```powershell
python tools/addon.py new yourname.example --name "Example atlas extension" --author "Your name" --output creator/example
```

Choose a stable lowercase id such as `yourname.example`. The generator creates the manifest, payload checksums, an original atlas-event example, settings and an experimental compatibility declaration. It prints the unique generated entry-module name. Keep that module filename, `entry` and the manifest file mappings consistent.

Each add-on has its own manifest and payload folder. A single-add-on repository uses this layout:

```text
my-addon/
  README.md       # author supplies usage and compatibility instructions
  addon.json      # identity, API/version, settings, compatibility, payload hashes
  payload/
    example.py    # the scaffold generates a unique filename here
```

The scaffold creates `addon.json` and `payload/`; add your own README. This source folder can be the root of a GitHub repository. Direct repository installation reads this layout at the selected commit. Current ZIP packaging includes only the manifest and declared payloads, so you can keep source documentation and development files beside them.

Client payloads must use Python 2.7-compatible syntax for the supported game profile. Studio's Python 3 requirement applies to the manager/tools. The current runtime entry point is `register(context)`, with atlas update/map/destroy events, saved settings, generated world data and logging. See the [API v1 reference](ADDON_API_V1.md) and the bundled [Boss Atlas](../src/metin2_studio/addons/catalog/community.boss-atlas/payload/boss_atlas.py) and [Map Legend](../src/metin2_studio/addons/catalog/community.map-legend/payload/map_legend.py) examples.

## Edit and build

1. Edit the generated `.py` file in `creator/example/payload/`.
2. Update the description, version, release notes, settings and compatibility in `addon.json` as appropriate. The scaffold defaults to `UNLICENSED`; choose licensing deliberately before sharing.
3. Refresh payload hashes after edits. From the Studio folder, paste this block into PowerShell; it uses Python and Studio's existing path/hash helpers:

```powershell
@'
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path('src').resolve()))
from metin2_studio.addons.hubcore.packages import confined_file, sha256, validate_manifest

package = Path("creator/example")
path = package / "addon.json"
manifest = json.loads(path.read_text(encoding="utf-8-sig"))
for item in manifest["files"]:
    item["sha256"] = sha256(confined_file(package / "payload", item["source"]).read_bytes())
manifest = validate_manifest(manifest)
path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
'@ | python -
```

4. Validate, build and inspect:

```powershell
python tools/addon.py validate creator/example
python tools/addon.py pack creator/example --output creator/releases/yourname.example-0.1.0.m2addon.zip
python tools/addon.py inspect creator/releases/yourname.example-0.1.0.m2addon.zip
```

5. Import the resulting ZIP in Discover and follow the reviewed installation flow above.

Outputs refuse overwriting existing scaffold directories, archives and catalog files. Use a fresh archive filename for another build. Keep published repository versions immutable: new distributed bytes need a new package version. During local development you may explicitly import a changed build with the same version; Studio still detects the changed content and requires an update plan.

Only declare original payload files intended for installation. Targets must be below `m2hub_addons/`; the manager owns its shared runtime and game integration. Do not package a whole game/root pack, executable, installation key or extracted game source. Validation/import read payload bytes without executing them. Add-ons run with the game client's permissions when loaded by the game.

## Share a release today

For a small test group, share the generated `.m2addon.zip` and the add-on's source/README. Explain the exact tested manager/client/server versions, limitations, settings and removal steps.

For a single-add-on public GitHub release, commit the root `addon.json`, declared `payload/` files and your README. Validate the package locally, then publish a GitHub Release whose tag matches the manifest version, such as `v0.1.0` for `0.1.0`. A bare Git tag does not appear as a published release. Keep published tags/versions immutable; use a new version for new release bytes. Users subscribe to the repository URL. Studio reads up to the first 50 GitHub release records and orders valid SemVer versions; drafts are excluded. A missing root README is allowed, though a useful README is strongly encouraged.

For another host, or to distribute prepared packages through a catalog, you can publish a static HTTPS catalog instead. Generate one from the actual release archive:

```powershell
python tools/addon.py catalog creator/releases/yourname.example-0.1.0.m2addon.zip --name "My add-ons" --publisher "Your name" --base-url https://example.org/releases/ --output creator/releases/catalog.json
```

`example.org` is a placeholder. Replace it with your real public HTTPS release location. The command writes local metadata; it does not upload or create hosting. Serve the exact archive at its generated URL and the JSON file at the URL your users subscribe to. Multiple artifacts can be supplied when generating a catalog; use unique filenames and keep earlier published bytes unchanged. See the [catalog guide](ADDON_REPOSITORIES.md) for channels, caching, source changes and withdrawal.

For catalog distribution, users add the **catalog JSON URL** in **Repositories**, check releases in Discover and review a download before reviewing an installation. GitHub users instead add the repository URL directly.

## Publish a collection from one repository

A collection makes several independent add-ons discoverable through one public GitHub URL. It does not bundle their installation. Users choose which add-ons to download, install and enable; each retains its own settings, version, dependencies and changelog. Updating one does not update its siblings. Explicit dependencies still need to be installed/enabled separately before a plan can apply.

```text
my-addons/
  addons.json
  README.md
  addons/
    atlas/
      addon.json
      README.md
      payload/...
    legend/
      addon.json
      README.md
      payload/...
```

Create two original scaffolds and generate the collection declaration from them:

```powershell
python tools/addon.py new yourname.atlas --name "My atlas extension" --author "Your name" --output creator/my-addons/addons/atlas
python tools/addon.py new yourname.legend --name "My map legend" --author "Your name" --output creator/my-addons/addons/legend
python tools/addon.py collection creator/my-addons --name "My add-ons" --publisher "Your name" --addon addons/atlas --addon addons/legend
python tools/addon.py validate-collection creator/my-addons
```

The `collection` command creates this root `addons.json`, refusing to overwrite an existing declaration:

```json
{
  "schema_version": 1,
  "name": "My add-ons",
  "publisher": "Your name",
  "addons": [
    {"id": "yourname.atlas", "path": "addons/atlas"},
    {"id": "yourname.legend", "path": "addons/legend"}
  ]
}
```

Edit each package and refresh its payload hashes using the normal [edit and build](#edit-and-build) workflow, with `package` set to that member's folder. Run `validate-collection` before publishing: it validates every listed manifest, id, file and checksum. Add per-add-on READMEs with usage/compatibility instructions. Studio reads the member README at its pinned commit, falling back to the root README when it is missing. These tools only write local files; publishing remains your own GitHub workflow.

Commit the collection root and its folders. Publish separate **GitHub Releases**, using the full add-on id followed by `/v` and that member's manifest version:

- `yourname.atlas/v0.1.0` releases only Atlas.
- `yourname.legend/v0.1.0` releases only Legend, even when both tags point to the same commit.
- `yourname.atlas/v0.2.0` updates Atlas without requiring a new Legend release.

A lowercase `v` is optional after the slash. Put that add-on's changelog in its GitHub Release body. Bare Git tags and unscoped `v0.1.0` releases do not publish collection members. Users add the repository URL once, then choose members individually in Discover. Stable/prerelease/development channel selection belongs to the repository; versions, selected packages and installed state belong to each add-on. Unreleased members are available only through the explicit Development channel.

List 1–20 unique ids in distinct, non-overlapping relative folders. Do not keep a root `addon.json` beside root `addons.json`. The editor [collection schema](../src/metin2_studio/addons/schemas/collection.schema.json) assists with authoring; the CLI also checks confined paths and package bytes. The latest default-branch declaration controls discovery membership; the selected release's own declaration supplies its historical folder path. Keep `addons.json` at every release commit and never move an already published tag. When converting a root add-on to a collection, retain its id and publish a new version with a scoped tag.

The first 50 GitHub Release records are shared across the whole repository. Source ZIP limits apply to the whole repository snapshot, even though only the selected member is normalized into an add-on package. Removing a member from the declaration stops new use after the next successful check; it leaves installed settings, disable/removal controls and recovery data available. See the [repository details](ADDON_REPOSITORIES.md#github-collections) for cache and review behavior.

## What an add-on's own README should explain

- What it does, its stable id and supported manager/client/server versions.
- How to build the package and where to find a ready release.
- Current Studio import instructions and any required dependencies/settings.
- Evidence and limitations: distinguish package validation, pack tests and actual gameplay.
- How to update, disable and remove it, plus source/license/support information.

## Current limits and next acceptance

GitHub supports a root single add-on or an explicitly declared collection with independent add-on folders. Private repositories, undeclared project layouts, arbitrary build systems and automatic dependency downloads are unsupported. Source archives are limited to 66 MiB; declared payload is limited to 64 MiB and the README to 256 KiB. No publisher registration, certification or signing is required.

The [roadmap](ADDON_ROADMAP.md#implemented-platform) records the implementation and its evidence. Browser/gameplay acceptance and an independent creator trial remain pending. Automated pack tests do not establish in-game compatibility.
