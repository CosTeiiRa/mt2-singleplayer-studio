# Beta readiness — beta-1.21.0

An experimental beta for a small group using an existing working game. Start with
5–10 testers, including a fresh installer and an independent add-on creator.
Fresh-machine setup and independent logged-in gameplay acceptance remain open.

## Scope

| Area | Evidence and limits |
| --- | --- |
| Host | Windows 10/11; primary local target is 64-bit Python 3.13 |
| Base Studio | Python 3.10+ standard library; optional client-pack wheels need 64-bit Python 3.11+ |
| Latest dashboard/catalogue observations | Server 2.2.123 / client 2.0.125 |
| Recorded add-on adapter verification | Client 2.0.125 / server 2.2.123; exact executable identity and pack hooks are checked before writes; older recorded profiles remain available |
| Legacy Mount Support | Inspected activation and narrow client-data corrections, isolated quest compilation and recovery fixtures; connected riding/expiry acceptance pending; combat excluded |
| Ownership | One local owner; loopback only |
| Human acceptance still pending | Fresh machine, independent logged-in gameplay, broader resolutions/languages, independent creator trial |

Version observations are not guarantees for other distributions or updates.
Publisher compatibility declarations remain separate from adapter/integrity
checks. The [recorded client evidence](ADDON_TESTING.md#client-20125-evidence--24-october-2026)
covers isolated pack roundtrip, four-add-on coexistence, settings, removal and
native widget/lifecycle checks; it does not establish logged-in gameplay.

## Validation

On 24 October 2026 the local release regression run reported 550 Python tests:
549 passed and one Windows symlink-permission skip. All 156 JavaScript tests,
syntax checks and Windows launcher parsing passed. GitHub Actions runs the
release checks on Windows/Linux with Python 3.10/3.13 and builds the portable ZIP.
Game-dependent suites need the configured local game
and optional codecs; CI skips unavailable integrations instead of claiming to
exercise a complete game installation.

The portable release is built from the reviewed allowlist and supplied with
`SHA256SUMS.txt`. Packaging checks extract it outside the development directory,
run entry points and validate all five bundled packages (four client add-ons and
Legacy Mount Support). Private settings,
databases, game packs, caches, logs, test artifacts and optional wheels are excluded.

Earlier disposable-fixture rehearsals covered setup/start/reuse/stop, retained
state, conflicting Studio instances, interrupted saves, external edits during
recovery, incomplete deployments and pack restoration. Repeat those rehearsals
when their implementation changes; do not force failures against a real world.

The earlier atlas work was checked against 422 monitored game files without any
changes. The mount review and isolated compilation also retained all nine watched
live server/client files. Preparing this release does not deploy game changes.

## Tester checklist

Keep a restorable world/database backup from the game's own tools and a copy of
Studio's private data folder. Use a disposable world for recovery rehearsals.

1. Extract the latest ZIP into a permanent Studio folder. Install/select the
   existing server, start through the shortcut, reopen, stop and restart Studio.
   Check that the game remains independent and history is retained.
2. Review and save a small server edit. Validate, then Apply and verify its actual
   gameplay result. Review and Apply a rollback.
3. Close the client and install the bundled add-ons together. Log in and check
   Add-on Menu, Pocket Wiki, Boss Atlas and Atlas Legend, including map changes,
   logout/login, shortcuts and the usual screen resolution.
4. Review an add-on update, settings changes, disable/enable and removal with the
   client closed. Confirm other add-ons and preferences remain intact.
5. During a normal game update, let game values take priority. Inspect deferred
   custom merges and any clean-pack reinstall before applying them.
6. An independent creator follows the creator guide to scaffold, package,
   import, install, update and remove an original API v2 add-on.
7. Report passed, skipped and failed steps with versions through
   [Support](../SUPPORT.md). Keep private game files out of attachments.

## Before making a repository public

The publication audit reviewed all 21 original commits, 578 historical file
versions, ten screenshot versions, both original release ZIPs and 18 available
CI log archives. One older CI log was unavailable. No embedded credentials,
personal installation paths, player records, databases or game packs were found.
Personal names and a Gmail address were present in commit/tag metadata and are
removed from the rewritten published history using a GitHub noreply identity.
At that publication, beta-1.20.0 was the only retained release and tag. A local
recovery bundle remains private under ignored data; never upload the working
folder wholesale.

Before changing visibility, verify the rewritten remote history, tag, current ZIP
and checksum. GitHub or existing clones may retain older commit objects; a history
rewrite cannot erase copies already held elsewhere. Keep the repository private
until the intended publication checks are complete.

Bug reports use [GitHub Issues](https://github.com/CosTeiiRa/mt2-singleplayer-studio/issues).
When making the repository public, enable and test GitHub private vulnerability
reporting, then use the route in [SECURITY.md](../SECURITY.md). Visibility changes
and community invitations require their own maintainer decision. Studio's MIT
license covers original Studio work; see [third-party notices](THIRD_PARTY.md)
for dependencies and game-material boundaries.
