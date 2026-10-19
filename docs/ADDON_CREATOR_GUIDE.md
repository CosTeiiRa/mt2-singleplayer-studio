# Creator guide

Studio alpha-1.8.0 also supports [client API v2](ADDON_API_V2.md), used by the
bundled [Pocket Wiki](POCKET_WIKI.md). The package layout below is shared by both
API versions. The default scaffold remains an API-v1 atlas example.

This is the schema-1 **alpha** package format for client APIs v1 and v2. The client interface is experimental and no public package-submission service exists. Normal supported game clients accept reviewed add-on changes with pack backups. For development, optional pack sandboxes and playable copies are under Advanced testing tools.

For the step-by-step start, read the [Add-on README](../addonhub/README.md). This document is the detailed format/runtime reference. Public GitHub repository URLs, local ZIP imports and Studio-format HTTPS catalogs are available. All use the same manifest and payload format.

## Scaffold and release tools

Run from the Studio project folder; these commands need Python 3.10+, without the optional pack wheels:

```powershell
python tools/addon.py new yourname.example --name "Example atlas extension" --author "Your name" --output creator/example
python tools/addon.py validate creator/example
python tools/addon.py pack creator/example --output creator/releases/yourname.example-0.1.0.m2addon.zip
python tools/addon.py inspect creator/releases/yourname.example-0.1.0.m2addon.zip
python tools/addon.py catalog creator/releases/yourname.example-0.1.0.m2addon.zip --name "My catalog" --publisher "Your name" --base-url https://example.org/releases/ --output creator/releases/catalog.json
```

The scaffold generates a unique namespaced module, an original event example, checksums, typed settings, API version and experimental client-version declaration. Its default license is `UNLICENSED`: deliberately choose a license and release notes before distribution. After editing payload bytes, update their hashes in `addon.json` before validation/packing. Outputs refuse overwriting existing artifacts, catalogs or scaffold directories; use a fresh destination for a new build.

For single-add-on GitHub distribution, keep this layout at the repository root and publish a GitHub Release tagged with the manifest version (an optional lowercase `v` prefix is accepted). Users add the public repository URL directly; no catalog or uploaded ZIP is required. Bare tags alone do not enter the release channel. Default-branch snapshots are an explicit Development option. See the [GitHub workflow](../addonhub/README.md#install-from-github).

The optional catalog command accepts several versioned artifacts and generates URL/size/hash metadata from the actual ZIPs. The newest version supplies package display metadata. Use unique artifact filenames and preserve previously published bytes. No upload occurs. When hosting is selected, serve the exact ZIPs at the generated HTTPS URLs and the index at the subscribed URL. See [repository workflow and limits](ADDON_REPOSITORIES.md), [API v1 policy](ADDON_API_V1.md) and [community launch preparation](ADDON_COMMUNITY.md).

## Several add-ons in one GitHub repository

Use root `addons.json` to list 1–20 independent package folders, each with its own manifest and declared payload. The [collection tutorial](../addonhub/README.md#publish-a-collection-from-one-repository) includes the complete tree, JSON and scaffold commands. Generate the declaration with `python tools/addon.py collection <root> --name "My add-ons" --publisher "Your name" --addon addons/atlas --addon addons/legend`, then run `python tools/addon.py validate-collection <root>`. Existing declarations are never overwritten. After edits, refresh payload hashes and revalidate the collection.

Publish per-add-on GitHub Releases tagged `<full-addon-id>/v<version>`, matching that member's manifest version. The release body is that member's changelog. Members can share a commit and version number without sharing artifacts or installation state. A new Atlas release need not change Legend. Only downloaded members enter the local selection, and installing/enabling one leaves its siblings alone. Dependencies remain explicit and manual.

Root `addon.json` and `addons.json` cannot coexist. Keep declarations at release commits; the current default branch lists discoverable ids while each pinned release supplies its folder path. Member READMEs fall back to the root README. Channel selection and the first 50 GitHub release records are shared across the repository. See the [collection schema](../addonhub/schemas/collection.schema.json) and [repository behavior](ADDON_REPOSITORIES.md#github-collections). Individual member folders can still be packed into ordinary `.m2addon.zip` artifacts with the existing CLI.

## Try a built package in Studio

Open Discover, choose **Import package**, select your generated `.m2addon.zip` and inspect its details. Select the normal game client in Add-on settings and close it, then review/apply the install plan. Optional development sandboxes remain available under Advanced testing tools. For a later build, import its ZIP and review an update; the installed settings are retained. Remove from catalog only forgets the selection; uninstall remains a separate action in Installed. This path needs no hosting, publisher registration or certification.

For a repeatable developer rehearsal, start the merged app and run `python tools/check_creator_workflow.py --url http://127.0.0.1:8780`. It creates original CLI fixtures, imports two versions, exercises coexistence/settings/update/disable/enable/removal on an owned copy of actual packs, checks exact restoration, removes its catalog fixture and reconnects the previous target. It does not run the game or represent an independent human trial. Private fixtures/reports remain under `data/`.

## Package structure

```text
your-addon-repository/
  README.md
  addon.json
  payload/
    example.py
```

An example manifest:

```json
{
  "schema_version": 1,
  "api_version": 1,
  "id": "yourname.example",
  "name": "Example atlas extension",
  "version": "0.1.0-alpha.1",
  "description": "Demonstrates an independent atlas subscriber.",
  "author": "Your name",
  "category": "Interface",
  "kind": "client-python",
  "entry": "m2hub_addons.example",
  "requires": [],
  "conflicts": [],
  "capabilities": ["atlas.overlay"],
  "files": [
    {
      "source": "example.py",
      "target": "m2hub_addons/example.py",
      "sha256": "REPLACE_WITH_THE_64_CHARACTER_LOWERCASE_SHA256"
    }
  ],
  "settings": {"show_labels": true},
  "settings_schema": {
    "type": "object",
    "properties": {"show_labels": {"type": "boolean", "default": true}}
  },
  "compatibility": {"client_versions": ["2.0.112"], "experimental": true},
  "release_notes": "Local alpha; in-game play-test pending.",
  "license": "MIT"
}
```

The checksum placeholder intentionally fails validation. After creating this manual example in `creator/example`, refresh the payload hashes with the [README checksum block](../addonhub/README.md#edit-and-build), then validate:

```powershell
python tools/addon.py validate creator/example
```

The validator reads and hashes payload bytes; it does not execute them. A valid package is not proof of safe behavior or working in-game compatibility.

The scaffold generates a unique filename rather than `example.py`. The [README checksum block](../addonhub/README.md#edit-and-build) refreshes every declared payload hash without assuming a particular filename.

`addonhub/schemas/addon.schema.json` can be used for editor assistance. The CLI/package loader is authoritative and checks additional path, file, checksum, and namespace rules not represented by the editor schema.

## Compatibility declarations

`compatibility.client_versions`, `server_versions` and `profile_ids` describe
publisher-declared coverage. They are not exclusion lists. A version/profile
outside them shows **Compatibility unverified**, with the current and declared
values explained in the installation review. Users can still apply that reviewed
plan to a supported game client without changing your manifest.

Matching coverage is **Declared compatible**, not proof of independent in-game
testing. Missing coverage or `experimental: true` remains unverified. A **Known
incompatibility** label requires a specific recorded reason; an unlisted version
alone is insufficient. Actual adapter, API, dependency, integrity and ownership
checks still block unsupported or conflicting operations. Test new versions and
expand declarations when you have evidence, rather than bumping them solely to
unlock installation.

## Naming and payload rules

- Use a stable lowercase `namespace.name` id. Letter/digit/underscore/hyphen segments are supported; begin each segment with a letter.
- Use a unique importable Python module below `m2hub_addons`. Your entry module must be one of the declared payload files.
- `source` resolves inside `payload/`. `target` is a logical pack path below `m2hub_addons/`, using `/`, not a Windows absolute path.
- Do not target `uiminimap.py`, `m2hub_runtime.py`, `m2hub_config.py`, or other game/framework files. The manager owns generated integration files.
- Use namespaced assets and module filenames. Do not distribute an entire replacement root pack.
- Omit shared namespace initializers unless needed. A supplied `m2hub_addons/__init__.py` must contain only a docstring or `pass`; executable shared initialization is rejected.
- Each payload file is limited to 16 MiB, total payload to 64 MiB, and the manifest to 2,048 files. Symbolic links, traversal, case-colliding destinations, and Windows-special paths are rejected.
- Supply only original code/assets or material you have the right to distribute. Do not bundle game packs, executables, game artwork, installation keys, or extracted game source.

## Runtime interface

Client payloads must remain compatible with the game's embedded Python; use Python 2.7/3-compatible syntax. The local manager and tools require modern Python, but that does not change the embedded client interpreter.

```python
def register(context):
    owned_widgets = {}

    def update(atlas):
        # Create/update only your own widgets. Cache stable calculations.
        # The Atlas Legend and Boss Atlas examples show actual UI calls.
        pass

    def destroy(atlas):
        widgets = owned_widgets.pop(id(atlas), [])
        for widget in widgets:
            widget.Hide()

    context.on('atlas.update', update)
    context.on('atlas.destroy', destroy)
    context.log('Registered example')
```

Baseline API-v1 context members (also available in API v2):

| Member | Behavior |
| --- | --- |
| `context.id` | Stable add-on id |
| `context.settings` | Validated saved settings for this enabled package |
| `context.on(event, callback)` | Register for `atlas.update`, `atlas.map`, or `atlas.destroy`; callback receives the atlas instance |
| `context.world(map_name)` | Return generated configured map data, or no entry for unknown names |
| `context.log(message)` | Prefix a client diagnostic with the add-on id |

Update/map events follow the original atlas method; destroy events precede the original destroy method. Preserve base-game behavior and another add-on's widgets. Do not patch the atlas methods again or assume you own the shared UI. Dispose of your own references on destroy and on map transitions. Cache per-map geometry and avoid filesystem work in every frame.

A registration error removes that add-on's registered listeners. A failing event callback is disabled for the event and logged to the client. This is fault containment for callbacks, not a security sandbox. Add-on Python has the privileges of the game client.

### API v2 windows and launchers

Set `api_version: 2` in the same schema-1 manifest for standalone windows, game
lifecycle callbacks, local preferences and generated reference data. The scaffold
does not switch APIs automatically. Follow the [README API-v2 instructions](../README.md#api-v2-windows-shortcuts-and-add-on-menu)
for the manifest fragment and registration example, and the [API-v2 reference](ADDON_API_V2.md)
for the complete context contract.

Register a lazy window factory with `context.register_window(name, factory,
shortcut='NONE')`. The factory receives the game window and returns your own UI
object implementing `IsShow()`, `Open()`, `Close()` and `Destroy()`. The host owns
lifecycle/input hooks and disposes owned windows at game Close. Use `game.open`
and `game.close` callbacks for launcher buttons and release their references on
close. Do not patch the shared game methods yourself.

An installed, enabled **Add-on Menu** exposes successfully registered windows
automatically. The menu is optional; a launcher button can call the returned
handle's `toggle()`. Supported shortcuts are `NONE`, `CTRL_U` and `F12`; duplicate
add-on shortcuts are refused and game bindings/chat input take priority. See
[Pocket Wiki's implementation](../addonhub/catalog/community.pocket-wiki/payload/pocket_wiki.py)
for its full window lifecycle and launcher.

## Settings, dependencies, and compatibility

The manager supports the implemented subset of object/property/type, enum, numeric bounds, string-length, array-item, and required-property validation. This is not a full JSON Schema implementation. Unknown settings keys are rejected. Defaults can come from `settings` and property `default` values.

The UI exposes boolean, string, number, integer and enum controls, with JSON editors for arrays/objects. It uses the installed release's schema even when a newer release has been downloaded. Settings changes use `configure` plans and are applied through the same transaction flow as installation. The backend remains authoritative for bounds, required fields and unknown-key validation.

`requires` and `conflicts` contain add-on ids. Required enabled dependencies must remain available; disabling or removing them may invalidate the desired state. Optional `dependency_versions` adds explicit comparisons such as `>=1.2.0 <2.0.0` for a required id. See the API policy for the deliberately limited grammar. There is no automatic dependency download resolver.

`compatibility.client_versions`, `server_versions` and `profile_ids` record exact
publisher-declared coverage. Missing coverage, an unlisted version/profile or
`experimental: true` produces **Compatibility unverified**, not a version-based
installation block. Users can review and apply the package to a supported client
without changing those declarations. Matching coverage is **Declared compatible**;
**Known incompatibility** requires a specific recorded problem. Actual adapter,
API, dependency, integrity and file-ownership checks remain independently
blocking. A declaration does not establish independent testing: native import
and widget-construction checks must stay distinct from interactive gameplay evidence.

Declare exact client/server versions and native profile ids covered by your
testing. This adapter's `profile_id` comes from an exact executable SHA-256 match
in `addonhub/profiles/*.json`. The current client 2.0.114 record is
[`tieru-2.0.114.json`](../addonhub/profiles/tieru-2.0.114.json), with profile id
`tieru-mt2009-client-2.0.114`; the older recorded profile is retained separately.
An unknown executable has `profile_id: null` and needs validated adapter support
before pack writes. Changing publisher version lists cannot provide that support.
The installation `id` identifies a path and is not the
native compatibility profile. Neither a matching declaration nor an unverified
warning bypasses adapter checks or the user's installation review. Evidence
records describe specific observed checks rather than certifying every
pack/server configuration or interactive behavior.

## Local release checklist

1. Give the package an owned id, description, author, license, and release notes.
2. Finalize payload bytes, update every checksum, and run the validator.
3. Build a ZIP with the creator CLI and import it in Discover; inspect the filename, manifest and checksum.
4. In a newly created pack sandbox, inspect and apply its installation plan.
5. Install the second example, then disable/re-enable/configure/remove yours. Confirm the other package remains intact.
6. Exercise recovery and external-edit conflict handling through the automated test harness, using disposable fixtures. Never fault-test the live game.
7. Record the exact tested manager/client/server versions and limitations. Pack/host checks must be distinguished from in-game evidence.

A new bundled catalog entry is not automatically included in the Studio source ZIP: its builder uses a deliberate allowlist. Creator archives are separate outputs built only from their manifest and declared payloads. Public hosting and optional shared discovery/support arrangements remain roadmap work. Users decide which publishers to trust; the platform does not provide publisher certification or require signatures. An independent creator has not yet completed this guide; that acceptance gate is still open.

## Release changelogs and manual updates

Write clear GitHub Release bodies for published versions. Studio shows those notes before users choose a download; known intermediate release notes are included when skipping versions. Keep manifest `release_notes` useful for local packages and development snapshots. Notes should explain behavior, compatibility and settings/migration changes. Missing notes remain visibly missing. Studio renders notes as text and bounds remote notes to 4,000 characters per release.

Users check metadata manually, read the changelog, choose whether to download, and separately review/apply installation changes. Publishing or checking a release never changes installed code automatically. A selected package may remain unapplied indefinitely.
