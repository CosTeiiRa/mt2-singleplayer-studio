# Add-on roadmap and acceptance status

Current scope: **Studio beta-1.20.0**, an experimental beta. Implemented features
and automated/native checks are distinct from independent human acceptance.
Hosted catalogs and community invitations are separate maintainer decisions.
The [beta checklist](BETA_REVIEW.md) records release evidence and pending trials.

## Implemented platform

| Area | Current behavior |
| --- | --- |
| Studio integration | One local launcher/service/world for server tools, add-ons, activity and the browser atlas |
| Normal game client | Reviewed install/update/settings/enable/disable/removal with pack backups; no extra playable copy required |
| Game updates | Clean replacement packs can become the new baseline through Review reinstall; no automatic reapply or restoration over a game update |
| Packages | Root manifest, declared checksummed payload, namespaced destinations, API/dependency/ownership checks and immutable installed payloads |
| Sources | Local ZIPs, explicit HTTPS catalogs and public GitHub repositories/collections; no repository build/install scripts run by the manager |
| Updates | Manual metadata checks, escaped changelogs and distinct download/install reviews; no automatic add-on updates |
| Network work | Cancellable background jobs, progress, cached offline results and interrupted-job notices |
| Runtime | API v1 atlas hooks and API v2 windows, shortcuts, local preferences, local reference data and launcher actions |
| Default add-ons | Add-on Menu, Boss Atlas, Atlas Legend and Pocket Wiki, each independently managed |
| Development | CLI scaffold/validation/deterministic packaging, local import, schema and API documentation |
| Recovery | Journalled pack/state transactions, exact baseline restoration, stale-review/external-drift checks and private recovery files |

Normal-client writes have been supported since alpha-1.9.0. Optional nonrunnable
pack sandboxes and owned playable copies remain under **Advanced testing tools**.
The original alpha-1.7/1.8 sandbox-only policy is historical and no longer describes
the normal installation workflow.

## Compatibility and trust

The initial beta target is server 2.2.110 / client 2.0.114 on Windows. Exact
executable identity and hook structure are checked before pack writes. Unknown
executables/integrations require adapter work; the game can update and launch
independently while add-on work waits.

Publisher version/profile declarations describe coverage. Unlisted versions show
**Compatibility unverified**, permitting reviewed installation on a supported
client. **Declared compatible** is a matching publisher claim, not independent
gameplay proof. **Known incompatibility** requires a specific recorded problem.
Integrity, dependencies and file ownership remain enforceable requirements.

Users choose trusted code and sources. Client Python executes with the game's
permissions; capabilities are descriptive, not a sandbox. Publisher certification,
account infrastructure and mandatory signing are outside the current scope.

## Existing evidence

Controlled package/API/HTTP/UI fixtures cover manifest/path/hash failures,
dependencies, settings, source identity, release/development channels, pinned
commits, moved tags, offline caching, cancellation, stale metadata and independent
collection members. Checks/downloads do not install code.

Actual copied-pack rehearsals cover coexistence, settings, disable/enable,
update/removal, state reopening, new-baseline reapply and exact physical
restoration. Private state and game content are excluded from release artifacts.
Native-client harnesses exercise import, widgets and lifecycle. Pocket Wiki data
tests retain source/seed coverage labels and do not infer unavailable engine rules.
See [integration testing](ADDON_TESTING.md) and [Pocket Wiki](POCKET_WIKI.md).

These are developer checks. They do not establish an independent creator's
success, connected gameplay on every profile, map/resolution alignment or a
performance ceiling. Earlier fixture counts describe the release tested at that
time; current pass/skip evidence belongs with the candidate validation record.

## Small beta acceptance still required

| Acceptance | Required evidence |
| --- | --- |
| Fresh installation | A tester follows the extracted ZIP instructions, including optional pack dependencies |
| Connected gameplay | A logged-in character opens all default add-ons, changes maps, logs out/in and checks normal controls |
| Display/input | Usual resolutions, keyboard/chat/IME behavior, window positioning and language combinations |
| Recovery | Disposable independent setup/recovery rehearsal, including disk/permission failures and external game changes |
| Creator workflow | A creator makes, packages, installs, updates and removes an original API v2 add-on using only the docs |
| Game update | Updated game remains authoritative; deferred custom merges and explicit pack reapply behave as documented |

The complete [tester checklist](BETA_REVIEW.md#tester-checklist) includes server
editing and rollback too. A small trial can use the bundled/local packages and
existing repository sources; a hosted discovery catalog is not a prerequisite.

## Later work

Broader executable adapters, cross-version state migration policy, cache
inspection/pruning, a packaged Python runtime and measured long-session
performance remain separate engineering work. Cache cleanup must preserve
selected/installed payloads, baselines, journals and recovery objects.

Before a public invitation, establish repository ownership/support/security
routes, inspect the actual Git history and CI artifacts, agree community and game
distribution boundaries, and complete independent acceptance. Optional catalog
hosting/moderation can follow a working repository experience. The
[community guide](ADDON_COMMUNITY.md) records the user-trust model.

Other game distributions, server add-on execution, Studio extensions, launcher
cooperation and live boss telemetry require different adapters and deployment
models. Client Python does not gain server deployment access through this API.
