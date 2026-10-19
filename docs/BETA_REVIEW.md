# Small beta readiness — beta-1.11.0

This is a local beta candidate, not an announcement or a public release. The
initial trial should involve 5–10 people, including a fresh installer and an
independent add-on creator. Do not expand that group until recovery and normal
gameplay have been exercised on their machines.

## Target and evidence boundaries

| Area | Initial scope / acceptance |
| --- | --- |
| Host | Windows 10/11; initial local target is 64-bit Python 3.13 |
| Game | Existing Metin2 Singleplayer Linux/Docker package; current target server 2.2.110 / client 2.0.114 |
| Client adapter | Recorded client 2.0.114 profile; exact executable identity and supported pack hooks are required, not a version string alone |
| Base Studio | Python 3.10+ standard library; optional pinned codec wheels require 64-bit Python 3.11+ |
| Ownership | One local owner; loopback only; no remote or multi-admin service |
| Automated evidence | Unit/HTTP/UI fixtures, release checks and isolated game-dependent rehearsals; inspect the release validation record for the current run |
| Native client | Import/widget and pack-lifecycle checks are separate from a logged-in session |
| Human acceptance | Fresh-machine setup, logged-in gameplay, broader resolutions/languages and independent creator trial remain pending |

Older 2.2.106–2.2.109 fixtures remain useful regression evidence. They do not
establish every distribution/version combination. A manifest's **Declared
compatible** label records the publisher's claim; **Compatibility unverified** is
a coverage warning and permits review on a supported adapter. Concrete adapter,
integrity, dependency and ownership failures can still block installation.

## Stabilization changes in this candidate

- Incomplete server saves are journalled and detected on startup. Further saves
  and Apply wait for reviewed recovery. Recovery restores only attempted bytes
  still present; external/game changes are retained. A completed SQLite save can
  finish its manifest without replaying game-file writes.
- Stop Studio refuses during critical Apply, game-update and add-on work.
  Startup marks an unfinished deployment interrupted and shows it for inspection;
  validation does not clear that warning. Validation/retry wait while the recorded
  previous build process is still running, and retry requires confirming that
  the game launcher/builds were checked. Studio never silently retries a build or
  restarts the game.
- A lock belongs to the selected game installation as well as Studio's state
  folder, preventing two Studio copies with different state paths managing the
  same game concurrently. The game's own launcher remains independent.
- Root licensing, support/security/contribution guidance and current workflow
  documentation are included. Source-publication review is still a separate step.

The [current client verification record](ADDON_TESTING.md#client-20114-evidence--18-october-2026)
includes isolated actual-pack roundtrip, all-four-add-on coexistence, settings,
disable/enable and exact removal. Native checks cover atlas widgets/lifecycle,
Ctrl+U, Add-on Menu and Pocket Wiki navigation. This is not logged-in gameplay;
independent tester/creator acceptance remains open.

Regression checks must exercise multi-file interruption, completed-save manifest
recovery, external changes during recovery, critical shutdown and separate-state
game locking. The adapter must pass an isolated lifecycle on the current client.
These checks must use disposable fixtures; do not force-crash a tester's world.

## Before supplying the first beta ZIP

- [x] Record the release version and exact target server/client versions; supply
      the generated `SHA256SUMS.txt` alongside the ZIP.
- [x] Run the Python/JavaScript and packaging checks; retain passed/skipped counts
      with reasons. Test the extracted ZIP, not only the development folder.
- [x] Verify optional dependencies from the clean installation instructions.
- [x] Confirm setup, start/reuse/stop, private state retention and recovery paths.
- [x] Review the source allowlist and ZIP for personal paths, game material,
      credentials, local databases, caches, logs and test artifacts.
- [ ] Confirm the beta has a real private contact through the supplying
      maintainer and that testers understand what reports can contain.

### Local validation — 18 October 2026

The extracted **beta-1.11.0** source package passed **411 Python tests** with
one Windows symlink-permission skip (412 reported executions), plus **86
JavaScript tests**. The earlier clean standard-library run, without a configured
game or optional wheels, passed with 318 reported executions and 38 skip entries;
some skips are whole game-dependent classes. These skips cover unavailable game
fixtures, optional codecs and the Windows symlink permission.

The documented optional dependency installer succeeded in the extracted folder
with the pinned `lzokay` and `numpy` binary wheels on 64-bit Python 3.13. Python,
JavaScript and PowerShell syntax checks passed. All 182 portable source files
matched the allowlist and working sources; the ZIP excluded private state, test
fixtures, wheels, game packs and executables. Credential/personal-path scans
passed. This is a current-package check, not an audit of external Git history.

Windows setup, start, reopening the same process, stop/restart, retained private
state and refusal of a second state folder targeting the same game all passed
against a disposable non-playable server fixture. Reviewed recovery tests include
interrupted multi-file writes, malformed receipts, changed game files and build
process/pipe failures.

The live Studio was restarted into this beta. Its pending work, installed add-ons,
backup receipts and private workspace were preserved. Monitored game files,
normal-client executable/root packs and the game container's start time were
unchanged. No server Apply, client reinstallation or game restart was performed.
Native client evidence is linked above. Visual browser acceptance, logged-in
gameplay and independent-machine/creator trials remain pending.

## Tester checklist

Use an existing working game and its normal client. Keep a restorable world
backup from the game's own tools, plus the complete private Studio data folder.
Never test failure recovery against your only world copy.

1. Extract the supplied ZIP to a separate permanent Studio folder. Install/select
   the existing server, launch, reopen through the shortcut and stop/restart
   Studio. Check that the game stays independent and history is retained.
2. Make a small configuration edit. Review and Save; confirm it remains pending.
   Validate once and confirm it is still pending. Apply and check the actual game
   behavior after reconnecting. Review and Apply a rollback.
3. Close the client and install the default add-ons. Enter a character; open
   **Add-on Menu**, **Pocket Wiki**, **Boss Atlas** and **Atlas Legend** using their
   documented controls. Check chat/shortcuts, window close/reopen, logout/login,
   map changes and your usual screen resolution.
4. Change add-on settings, disable/enable and remove an add-on with the client
   closed. Confirm other add-ons and saved preferences remain intact. Test final
   removal/restoration only after retaining the game and Studio backups.
5. During an ordinary game update, let the game update first. Inspect deferred
   custom merges, keep game values or review selected custom values, and confirm
   saved merges need a verified Apply. Review clean-pack reapply if offered.
6. An independent creator follows the README: scaffold an original add-on, use
   API v2 for a window, validate/package/import, install/configure, open it through
   Add-on Menu, update it and remove it without maintainer intervention.
7. Report what passed, skipped or failed, including versions and reproducible
   steps. Use [SUPPORT.md](../SUPPORT.md); keep private files out of attachments.

Forced interruption and database restoration belong in a separate disposable
recovery rehearsal. A successful build does not establish correct quest rewards,
NPC rendering, database migrations or every add-on interaction.

## Before making a repository public

This local source folder has no Git metadata, so a local ZIP scan cannot audit
the intended repository's tracked files, old commits, branches, tags, LFS objects,
releases or CI logs. Their review remains required before changing visibility.

- [ ] Identify the actual repository, owner and intended initial branch.
- [ ] Inspect all tracked files and history for credentials, `.env`, personal
      paths, world/player records, logs, databases, generated artifacts and game
      assets. Ignore rules do not remove material already committed.
- [ ] Review Actions run logs/artifacts, release uploads, LFS and other exposed
      repository content. Remove private material; rotate any exposed credential
      and verify the remediation before publication.
- [ ] If creating a new repository, import only the reviewed source allowlist;
      do not upload this entire working directory or a private game installation.
- [ ] Check license notices for original Studio code and third-party material;
      no game redistribution rights are provided by Studio's MIT license.
- [ ] Establish public bug/support ownership and a working private security
      reporting route, then update SUPPORT.md and SECURITY.md with real details.
- [ ] Agree on any Singleplayer-project distribution/community boundaries and
      obtain permission for an invitation in the intended Discord community.
- [ ] Complete the small trial, triage its issues and separately approve public
      visibility, a release tag and an invitation. None is performed by building
      this candidate.
