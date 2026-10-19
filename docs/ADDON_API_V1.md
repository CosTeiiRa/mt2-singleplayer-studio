# Client API v1 and compatibility policy

Studio supports [API v2](ADDON_API_V2.md), used by Pocket Wiki and Add-on Menu.
The v1 atlas interface below remains supported in beta-1.11.0. Managers accept
versions 1 and 2; unknown versions are refused.

Set `api_version: 1` for this interface. Omission means v1 for existing schema-1 packages. This is a small documented experimental interface, not a claim of a stable public SDK or security isolation.

An entry module exports `register(context)`. It is imported by the embedded game client only when enabled. Studio validates and packages its bytes without importing it.

| Member/event | v1 behavior |
| --- | --- |
| `context.id` | Manifest add-on id |
| `context.settings` | Validated saved configuration for the enabled package |
| `context.on(name, callback)` | Subscribe to `atlas.update`, `atlas.map`, `atlas.destroy`; callback receives the atlas instance |
| `context.world(map_name)` | Saved configuration data generated during the reviewed pack transaction, or no matching entry |
| `context.log(message)` | Client diagnostic prefixed by add-on id |
| Update/map events | Dispatched after the original atlas method |
| Destroy event | Dispatched before the original atlas method |

Register only your own listeners, keep references to your own widgets and dispose of them on destruction/map changes. Do not patch the shared methods again. Treat game widget internals as profile-specific: v1 does not make the game's entire Python/UI API stable. Cache geometry and avoid filesystem/network work on every frame.

Registration failure removes that add-on's listeners. A failing callback is disabled for its event and logged. This limits callback failures; it does not restrict the privileges of Python running in the game.

## Version and dependency rules

New distribution artifacts and repository releases require [SemVer 2.0.0](https://semver.org/). Increment the package version whenever published bytes change. Build metadata does not change version precedence. For an archive already observed at a repository/id/version, a different checksum is refused.

`requires` lists add-on ids. Optional `dependency_versions` adds a constraint for a required id:

```json
{"requires": ["creator.shared"], "dependency_versions": {"creator.shared": ">=1.2.0 <2.0.0"}}
```

Supported expressions are up to eight whitespace-separated comparisons using `=`, `>`, `>=`, `<`, `<=`, or a bare exact version. All comparisons must pass. Carets, tildes, wildcards, OR expressions and a space between comparator and version are unsupported. Prerelease values use literal SemVer ordering; there is no npm-style prerelease exclusion inside a constraint. Required packages must already be installed and enabled. Studio reports conflicts and does not automatically download/install dependency chains.

`conflicts` declares mutually incompatible ids. Exact
`compatibility.client_versions`, `server_versions` and `profile_ids` describe the
publisher's tested coverage. Missing/unlisted versions or profiles and
`experimental: true` show **Compatibility unverified**; this permits reviewed
installation on a supported client. Matching declarations show **Declared
compatible**, not independent proof. **Known incompatibility** requires a
specific recorded problem. Adapter/executable structure, API, dependency,
integrity and ownership checks can still block installation independently of a
coverage warning.

## Evolution and evidence

An incompatible host contract must use a new API version and explicit migration guidance. The current manager rejects unknown versions rather than guessing. Additive v1 proposals should preserve existing callback behavior and receive coexistence/lifecycle tests before adoption. API changes and native-profile changes are separate: a stable callback name cannot guarantee an untested client layout or executable.

Manager state currently retains schema 1 and can reopen existing local state; immutable installed payloads remain available independently of the active catalog. There is no general future-state downgrade/migration mechanism. Preserve the private state folder and original backups when changing manager versions. Test upgrades against copies first.

The bundled runtime/examples have recorded copied-client native startup/widget evidence. Interactive gameplay, alignment across resolutions and frame cost remain unverified. The creator scaffold has fixture/package validation; it has not been independently authored or gameplay-tested by another creator.
