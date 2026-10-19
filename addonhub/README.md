# Create and install Metin2 Studio add-ons

Studio lists **Add-on Menu** first, alongside Boss Atlas, Atlas Legend and **Pocket Wiki**. Install Add-on Menu to get one in-game **Add-ons** button listing installed extensions and opening their windows or atlas overlays. It is an ordinary optional add-on and can be disabled or removed independently.
Its [usage guide](../docs/POCKET_WIKI.md) covers crafts, upgrades, sources/uses and
reference-data refresh. [API v2](../docs/ADDON_API_V2.md) adds standalone windows
and preferences while retaining API v1. Add-ons apply to your normal supported
game client, with backups of changed pack files. Extra development targets are
optional under **Add-on settings → Advanced testing tools**.

An add-on is original client Python code with an `addon.json` manifest and declared payload files. Studio uses that common format to validate files, compose add-ons, manage settings and apply reviewed updates/removals. Users choose which authors and sources to trust.

This guide describes **alpha-1.10.0**. Public GitHub repositories, local ZIP import and Studio-format HTTPS catalogs work today. GitHub sources use the same manifest/payload format; creators do not need to upload an add-on ZIP or maintain a catalog. Arbitrary projects still need to adopt this layout. The local ZIP importer accepts creator-tool packages, not generic GitHub “Download ZIP” archives.

**Compatibility unverified** is a warning, not a declaration that an add-on is
broken. A new game/client version outside its publisher's list can still use the
normal review and Apply workflow on an supported game client. Details show
the current and declared versions. **Declared compatible** records publisher
coverage; **Known incompatibility** requires a specific recorded problem. Actual
adapter, integrity, dependency and ownership checks remain blocking.

## Install from GitHub

1. Set up Studio and optional pack support as described below, then select **Normal game client** in **Add-on settings** and close that client.
2. Open **Repositories**, paste the public `https://github.com/owner/repository` URL and choose **Stable releases**. Adding reads metadata and the README; it does not install code.
3. Open **Discover → Repository releases → Review download**. Review the version, source reference, full pinned commit, manifest checksum and README. README content is shown as text.
4. Choose **Download and verify**. Studio fetches the pinned source archive, verifies the manifest and declared payload hashes, and stages a normal package. It ignores undeclared development files and never runs repository build/install scripts.
5. Review and apply the separate installation plan. For later versions, **Check for updates**, review/download the release, then review/apply an update. Downloading alone leaves installed code and settings unchanged.

For a repository without a published release, explicitly choose **Development branch (GitHub)** and check the repository. Development snapshots track the default branch; they remain separate from stable/prerelease updates. The review pins one commit even if the branch advances before download. Installed details retain the installed revision until you apply a changed package.

Only public GitHub repositories are supported; no account or access token is used. GitHub API limits can require retrying later. Failed checks retain the last valid metadata, installed code and settings; already cached versions can be selected offline. Read the [repository guide](../docs/ADDON_REPOSITORIES.md) for limits and source controls.

## See updates and read the changelog

Add-on updates are always manual. Open **Installed add-ons → Check for updates** to check enabled sources. The background job fetches metadata only, reports individual source failures and never downloads an add-on archive or applies code. Disabled sources are skipped. No startup timer, remote polling or automatic update option is enabled.

Available updates show installed/available versions and **Read changelog**. Studio also shows a count in its overview and add-on toolbar. The changelog contains known release notes since the installed version, or the notes of an imported/selected package. Read it and choose **Not now**, **Review download**, or—after selecting the package—**Review installation changes**. Downloading alone keeps the notification and installed code/settings unchanged. Apply the reviewed plan separately when ready.

Notifications follow the installed repository source and selected channel. Competing, disabled or blocked sources are not advertised as repository updates. Failed checks retain last-known notes with a warning and block uncached downloads. Development snapshots compare package content, so a README-only commit does not create a reinstall notice. Imported same-version changes are shown as selected package changes for review.

Changelogs are displayed as escaped text. Published GitHub Releases use their release body; development/local packages use manifest `release_notes`. Include useful changes, compatibility changes and migration/removal notes when publishing. A missing changelog is shown as missing; Studio does not invent one. Known release history is limited by the provider/catalog (up to the first 50 GitHub release records).

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

Client payloads must use Python 2.7-compatible syntax for the supported game profile. Studio's Python 3 requirement applies to the manager/tools. The current runtime entry point is `register(context)`, with atlas update/map/destroy events, saved settings, generated world data and logging. See the [API v1 reference](../docs/ADDON_API_V1.md) and the bundled [Boss Atlas](catalog/community.boss-atlas/payload/boss_atlas.py) and [Map Legend](catalog/community.map-legend/payload/map_legend.py) examples.

## Edit and build

1. Edit the generated `.py` file in `creator/example/payload/`.
2. Update the description, version, release notes, settings and compatibility in `addon.json` as appropriate. The scaffold defaults to `UNLICENSED`; choose licensing deliberately before sharing.
3. Refresh payload hashes after edits. From the Studio folder, paste this block into PowerShell; it uses Python and Studio's existing path/hash helpers:

```powershell
@'
import json
from pathlib import Path
from addonhub.hubcore.packages import confined_file, sha256, validate_manifest

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

`example.org` is a placeholder. Replace it with your real public HTTPS release location. The command writes local metadata; it does not upload or create hosting. Serve the exact archive at its generated URL and the JSON file at the URL your users subscribe to. Multiple artifacts can be supplied when generating a catalog; use unique filenames and keep earlier published bytes unchanged. See the [catalog guide](../docs/ADDON_REPOSITORIES.md) for channels, caching, source changes and withdrawal.

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

List 1–20 unique ids in distinct, non-overlapping relative folders. Do not keep a root `addon.json` beside root `addons.json`. The editor [collection schema](schemas/collection.schema.json) assists with authoring; the CLI also checks confined paths and package bytes. The latest default-branch declaration controls discovery membership; the selected release's own declaration supplies its historical folder path. Keep `addons.json` at every release commit and never move an already published tag. When converting a root add-on to a collection, retain its id and publish a new version with a scoped tag.

The first 50 GitHub Release records are shared across the whole repository. Source ZIP limits apply to the whole repository snapshot, even though only the selected member is normalized into an add-on package. Removing a member from the declaration stops new use after the next successful check; it leaves installed settings, disable/removal controls and recovery data available. See the [repository details](../docs/ADDON_REPOSITORIES.md#github-collections) for cache and review behavior.

## What an add-on's own README should explain

- What it does, its stable id and supported manager/client/server versions.
- How to build the package and where to find a ready release.
- Current Studio import instructions and any required dependencies/settings.
- Evidence and limitations: distinguish package validation, pack tests and actual gameplay.
- How to update, disable and remove it, plus source/license/support information.

## Current limits and next acceptance

GitHub supports a root single add-on or an explicitly declared collection with independent add-on folders. Private repositories, undeclared project layouts, arbitrary build systems and automatic dependency downloads are unsupported. Source archives are limited to 66 MiB; declared payload is limited to 64 MiB and the README to 256 KiB. No publisher registration, certification or signing is required.

The [roadmap](../docs/ADDON_ROADMAP.md#direct-github-repositories--implemented) records the implementation and its evidence. Browser/gameplay acceptance and an independent creator trial remain pending. Automated pack tests do not establish in-game compatibility.
