# beta-1.0.0 project review

The review focused on distributing Studio to an existing supported game installation, protecting existing work, and separating local data from the release.

## Findings addressed

| Finding | Change |
|---|---|
| The game path was fixed to the original developer's computer. | Removed the personal default; added an explicit folder picker/CLI setup, package-file validation and local remembered settings. |
| Downloading the code did not provide a complete first-run flow. | Added Install Studio.bat / Setup-Studio.ps1, Python launcher detection, actionable errors and documented first-use steps. Starting without setup opens it. |
| Launching on a busy port could reuse another Studio/world. | The launcher verifies application, server root and state folder before reusing an instance. |
| Switching worlds could mix customisation history and applied native recipe state. | Default data folders are derived per world and bound to their selected server. An explicit conflicting state folder is rejected. |
| Stop depended on the currently selected game still being valid. | Stop reads the local data path without validating game files or requiring Python, and verifies the recorded process belongs to this Studio. |
| A fresh installation's zero counter implied a verified deployment. | The tooltip now distinguishes no saved changes from a previously verified Studio deployment. |
| An invalid native crafting configuration during background Apply preparation could leave the job marked running. | Command preparation is inside the failure handler; a regression check verifies it fails before any build/restart command. |
| The long README mixed operator guidance with outdated development notes. | Added installation-focused README, an updated operator guide, release notes and compatibility/coverage limits. |
| Game assets, credentials and local history must not be published. | Ignore rules and a tracked-source-only release builder exclude local state, credentials, logs and cached/test/game data. |

## Verification

- Self-contained setup checks cover folder selection, missing files, path/port validation, settings round trips, state isolation, read-only checking and corrupt settings.
- The local game integration suite operates on disposable copies of selected installed files; assets are not bundled in this repository.
- Windows PowerShell 5.1 launcher scripts were parsed and the noninteractive setup/start/reuse/stop workflow was exercised locally at a separate port with fresh Studio state.
- Before tagging, 167 Python tests passed with the local game integration fixture, alongside 19 JavaScript tests and syntax checks. Windows/Linux CI runs self-contained checks; game-dependent groups are explicitly skipped without an installation.
- Native crafting SQL was also exercised against a separate disposable MariaDB, including creation, editing, shared-window preservation, guarded conflicts, transaction rollback and preservation of unrelated updates. No live game Apply is needed for installation verification.
- The extracted release ZIP was installed and started at a separate local port, with zero pending game changes. Instance reuse, rejection of a different state folder and stopping after an invalid game path were checked. Both disposable Studios were then stopped; the existing game was retained.
- The release ZIP is checked for local data and credential files before publication.

## Remaining beta limits

Compatibility was validated on Windows with game package 2.2.106. This release does not claim arbitrary Metin2-distribution compatibility or a full remote-server setup. CI does not include a real game world/client, and unit checks do not prove every quest's in-game rendering or every database migration. Existing native-panel drop overrides can supersede image files; coverage notes and runtime verification report supported discrepancies.

Advanced quest/source edits are powerful and require their normal review/build/play-test workflow. Configuration history does not replace world/database backups. Retain the complete private Studio data folder for applied-native-crafting reconciliation and rollback. Studio is intended for one local owner, bound to loopback.
