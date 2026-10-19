# Add-on integration architecture

## Game authority and updates

The game and its updates are authoritative. Studio and add-ons are optional
layers that must adapt to the game; keeping an add-on working is never a reason
to hold back an official update. The game's original client, server launcher and
update path remain independent of the add-on service and optional pack codecs.

Package updates archive affected tracked files and install the game's values
first. Original/custom values remain in `tracked`, with the installed game bytes
as `expected` and a `deferred_merges` marker. This preserves a three-way merge
review across restarts and further updates without restoring old overrides.
Public scans include deferred reviews; build guards and runtime verification
exclude accepted deferred intent. External-update scans can explicitly defer
their review through Keep game; decide later. New edits to a pending file require
resolving that file's merge first, so old custom intent cannot be lost silently.

Conflicts default to game values in the later review. Explicit merge Save updates
the game file, rebases custom intent onto the game baseline and clears the pending
marker atomically in Studio state. Files absent from a package are left alone.
A pending native package build does not run Studio's native-crafting override
step; review those changes separately against the updated database. Full world
backups remain separate.

An unknown executable or changed integration point can make an add-on unavailable
until the adapter is updated. Original game updates are still possible through
the game's own launcher. The normal client remains the default add-on target;
updates never require another playable copy. Refresh generated
reference data after content changes; it never overrides authoritative game data.

## Normal client updates and restoration (alpha-1.9.0)

A successful first apply captures logical and exact physical baseline objects.
Transactions back up only changed pack files, rather than copying a playable
client. Removing the final add-on restores the current physical baseline exactly.

When externally replaced packs contain no Hub runtime, configuration, namespace
or bootstrap markers, Studio offers a game-update review. It composes the stored
add-on payloads and settings over the current game files. Only explicit Apply
commits the new baseline. Stale reviews fail before writing; a failed reapply
restores the new game files captured by that transaction. Mixed changes retaining
Hub files remain conflicts for inspection. No automatic client modifications run
on startup or update detection. Unknown executable profiles and changed hook
structures require integration support without blocking the game's own updater.

## Pocket Wiki and standalone windows (alpha-1.8.0)

The catalog now also contains `community.pocket-wiki`. API v2 preserves atlas
callbacks and adds game Open/Close, guarded shortcuts, owned window handles,
helper-module loading and bounded preferences. The adapter adds a bootstrap to
the current `game.py` baseline when v2 packages are enabled. Removing the last
v2 package removes that integration through normal baseline composition.

`knowledge.py` produces structured item/recipe/refinement/source relations from
captured saved bytes and current native rows where available. It excludes drafts,
staged source views and pending native overrides. Seed and configuration
provenance is retained; effective build-time/engine rules are not inferred.
Generated data is world-local, cached privately and bound to reviewed logical
hashes. `refresh-data` uses the existing journal/recovery transaction.

Owned playable copies use `m2hub-playable-copy-v1` markers beneath the world's
`addons/playable-clients`. Their executable must match the recorded profile and
captured hash. These are optional developer targets; normal supported clients
also accept reviewed changes. Pack sandboxes still reject executables. Creation
copies assets without starting a client. See
[Pocket Wiki](POCKET_WIKI.md) and [API v2](ADDON_API_V2.md).

The service boundaries below are shared by normal clients and optional testing targets.

`src/metin2_studio/server.py` remains the only HTTP entry point. Existing server endpoints and web scripts continue to serve the server workspace. `/api/addons/*` delegates to `metin2_studio.addons.integration.AddonService`; the same Studio session token, localhost Host/Origin checks and CSP protect both modules. Add-on JSON mutations are limited to 64 KB. The authenticated local-package import endpoint separately accepts a bounded raw ZIP of at most 66 MiB; it rejects incomplete uploads before selecting a package.

`Studio.addons` initializes lazily. Its manager is `metin2_studio.addons.hubcore.manager.Manager`, using `metin2_studio.addons.client_adapter.ClientAdapter` and original package examples in `src/metin2_studio/addons/catalog`. Installed pack keys and game material are read locally and are never distributed. Optional wheel imports stay inside the add-on package; base Studio startup does not require them.

The selected server fixes the world. Its normal sibling client is writable when its executable matches a recorded integration profile and the hash captured at connection. The exact client must be closed at review/apply; the server can stay running. Optional testing targets require valid world-owned markers. Another world's target is rejected. A state-folder lock prevents competing merged Studio instances using that state; separate state folders do not coordinate external tools editing the same game.

Server state remains in its existing schema. Add-on state lives beneath `state/addons`, retaining independent desired state, immutable package payloads, file ownership, baselines, reviewed fingerprints and transaction recovery. Removing all add-ons restores the exact captured pack pair. Shared activity reads event metadata without rewriting old transaction or backup formats. Imported Hub history is explicitly legacy metadata, not adoption of its installed state.

`web/addons.mjs` is a module mounted in Studio's content area. It shares Studio's API helper, notifications, route ownership and draft-preserving editor navigation. Its delegated events, control IDs and CSS are scoped so surrounding editors keep their own controls. There is no second service, iframe or embedded standalone navigation.

World atlas data always comes from the selected server's saved configuration. Region paths use portable forward slashes so they match Studio file IDs. Mob/group resolution supplies the drop target. Client runtime data is generated through the original reviewed pack composition, and changes after review invalidate apply. A later saved map edit needs a new reviewed add-on configuration/install operation to refresh generated client data; no automatic live injection occurs.

The recorded executable profile remains evidence of native startup/import/widget checks on the unchanged runtime. It is not interactive gameplay certification. Original Hub code licensing is retained in `src/metin2_studio/addons/LICENSE`; dependency notices are in `docs/THIRD_PARTY.md`.

`RepositoryStore` supplies the manager's composed catalog from bundled packages and the explicitly selected verified release cache. Metadata checks and archive downloads are user-requested mutations; GET routes/startup do not fetch remotely. `transport.py` pins validated public DNS addresses and verifies the original TLS hostname on every hop. `artifacts.py` validates bounded archive members, strict JSON, declared contents and checksums without importing payload code. `versions.py` supplies SemVer precedence and a limited explicit comparator grammar.

Subscriptions, last valid metadata, observed immutable release hashes, archive bytes and selected-release pointers live under the world's private add-on state. Installed payloads remain per-target objects, independent of catalog availability. The service binds installation reviews to the repository-state fingerprint as well as the manager's existing target/source fingerprints; subscription/download changes invalidate reviews. Disabling a source or withdrawing a release blocks new installs/updates/enables while preserving configuration, disabling, uninstall and recovery. A source change needs separate explicit acknowledgement. Trust decisions belong to the user. The platform exposes source/checksum information and validates files; it has no publisher certification or mandatory signature layer.

The creator CLI builds deterministic ZIPs from validated original manifest/payload bytes, scaffolds API v1 and generates static index metadata. Typed settings use the installed schema. `support-report` uses an explicit allowlist rather than serializing private diagnostics; raw paths, settings, URLs, tokens, errors and game content are excluded. Repository network operations currently hold the Studio mutation lock; background download jobs/cache pruning are future improvements.

Local imports and repository downloads share the same archive cache and selected-release catalog provider. Local records include `source_kind: local`, filename, hash and manifest digest. Older repository records without a source kind remain supported. Import does not install or execute code. Forgetting a local selection leaves per-target installed objects and recovery data intact. The browser uploads the selected File using Studio’s shared token/API helper; no local absolute path is accepted by the import route.

## Optional in-game launcher (alpha-1.10.0)

Add-on Menu is an ordinary API-v2 package using the existing game lifecycle. It
owns its button/window and is listed first; disabling or removing it retains other
extensions. The host exports installed metadata separately from active modules,
so disabled entries can be shown without loading their code. Registered windows
open without toggling an existing window closed. Atlas-capable extensions use the
game's native atlas object. The menu does not change installation state in-game.
