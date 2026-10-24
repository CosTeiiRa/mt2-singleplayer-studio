# Getting started

[Back to the overview](../README.md) · [All documentation](README.md)

Detailed requirements, setup choices, your first server edit and common startup problems.

## Requirements and compatibility

- **Windows 10/11** and **Python 3.10+** for base Studio. The initial small-beta target uses 64-bit Python **3.13**; optional add-on pack support needs 64-bit Python **3.11+** and matching binary wheels. Download Python from [python.org](https://www.python.org/downloads/windows/); enable its launcher/PATH option if offered.
- An existing, working **Metin2 Singleplayer Linux/Docker server package**, with a `Serwer` directory containing `files/`, `linux-port/docker/` and `VERSION`. The latest dashboard/catalogue checks used server **2.2.111** / client **2.0.115**. Recorded add-on pack/lifecycle verification used client **2.0.114** with server **2.2.110**; exact executable identity and integration support are checked before pack writes. These observations do not guarantee every game/client version. Other Metin2 distributions, remote servers, WSL-only paths and standalone client folders are unsupported.
- The game's normal Docker Desktop / Docker Compose setup. Keep using its launcher to start the game. Docker is needed for native crafting and Apply; file-based editors remain usable with Docker stopped.
- Write access to the selected server and Studio folders.

**Base Studio needs no pip/npm packages, Node.js or separate database server.**
Client pack rebuilding uses the optional pinned dependencies installed by
**Install Add-on Support.bat**. Node.js is only used for developer checks. No game
reinstall or engine/executable patch is required; reviewed add-on Apply does
change client packs. The package contains Studio code, not the game or its assets.

## Install on a computer where the game already works

1. Download the portable source ZIP and `SHA256SUMS.txt` from the [latest beta release](https://github.com/CosTeiiRa/mt2-singleplayer-studio/releases/tag/beta-1.21.0). Extract it fully into a permanent folder, for example `C:\Tools\Metin2Studio`. Do not run the files from inside the ZIP or place Studio inside `Serwer`.
2. Confirm Python is installed. If a terminal is available, `py -3 --version` or `python --version` should show Python 3.10 or newer.
3. Double-click **Install Studio.bat**. Choose the **existing `Serwer` folder** in the folder picker. You can also select its `Metin2 Singleplayer` parent folder. Setup validates the package files, saves your choice locally and creates a desktop shortcut. It does not copy or replace game files, start Docker, build images or restart the game.
4. Double-click **Start Studio.bat**, or the **Metin2 Studio** desktop shortcut. The dashboard opens at **http://127.0.0.1:8765**. Starting an already running matching instance reuses it.
5. For native crafts and the game dashboard, start the world with its **existing game launcher**, wait until it is healthy, then refresh the relevant page in Studio.

If you skip step 3, **Start Studio.bat** opens setup on its first run. No administrator launch is normally necessary. **Stop Studio.bat** stops only Studio; the game remains running. The batch files use a process-local PowerShell execution policy; no system-wide policy change is needed.

Your first launch uses the current game files as its starting point. It does not import someone else's world, recipes, quests, credentials or economic history. Existing manual customisations remain present, but earlier custom differences cannot be reconstructed without an original backup; see **Update protection → Track an existing edit**.

### Configure from PowerShell instead

Run these commands from the extracted Studio folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts/windows/Setup-Studio.ps1 -ServerRoot "D:\Games\Metin2 Singleplayer\Serwer" -NoShortcut -NonInteractive
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts/windows/Launch-Studio.ps1 -NoBrowser -NonInteractive
```

Choose another local port by adding **`-Port 8766` to scripts/windows/Setup-Studio.ps1**; then use `http://127.0.0.1:8766`. Setup remembers the port. To check configuration without changing any files:

```powershell
python studio.py setup --check
```

For a terminal-only session, you can run `python studio.py serve --root "D:\Games\Metin2 Singleplayer\Serwer" --port 8766`. Stop it with Ctrl+C. The advanced `--state` option selects an existing Studio data folder; do not share one folder between different worlds. `METIN2_STUDIO_SERVER_ROOT` is also supported for developer/integration-test sessions. Explicit CLI arguments take precedence.

## Your first edit

1. Open **Drop editor**, **Quests**, **Crafting recipes** or a configuration submenu.
2. Find items by name, ID, category or function. Hover to read descriptions; **Where used** shows existing references.
3. Make a small edit and click **Review changes**. Check the before/after values and source diff.
4. Choose **Save & apply…** to save with a backup and continue to the shared apply screen, or **Save for later**. A working change set stages the edit until the whole set is saved.
5. **Review & apply (N)** groups saved files, a pending game package build and add-ons that need reapplying. Choose either group or both, then apply once. **Players disconnect when server files are applied.** Add-on-only runs keep the server running. Unfinished drafts and staged changes are excluded. Optional **Advanced → Validate build only** checks compilation without deployment.

The Apply dialog leads with the current pending changes. Earlier build/validation
results appear under a collapsed **Previous operation** section. A successful
validation leaves saved changes pending; it does not apply them or restart the game.

For an existing working world, use the game's backup feature before your first Apply. Studio's configuration history does not replace a world/database backup. A build failure keeps the running game; a later migration/database/start failure can leave it stopped, with a diagnostic in the Apply log. See [backups and recovery](USER_GUIDE.md#backups-and-recovery) before testing interrupted operations.

## Troubleshooting

| Problem | What to do |
|---|---|
| Python not found / Store alias opens | Install Python from python.org with its launcher/PATH option, reopen the terminal and rerun Install Studio.bat. Both `py -3` and `python` are supported. |
| Missing `files/items.json`, SQL dump or Cube files | Select the server's **Serwer** folder, not the game client. Setup lists missing files. Arbitrary Metin2 distributions are unsupported. |
| Docker/game dashboard/native crafting unavailable | Start Docker Desktop and the world using the existing launcher, wait for healthy services, then Refresh. No new Docker stack is installed by Studio. |
| Port already in use / wrong world opens | Close that Studio instance, or configure another port with `scripts/windows/Setup-Studio.ps1 -ServerRoot "...\Serwer" -Port 8766`. The launcher checks the world/data identity before reusing an instance. |
| Data belongs to another server | Choose the correct game folder or a new data folder. Do not overwrite another world's binding/history. |
| Studio fails to start | Read `studio.err.log` in the data folder printed by setup. Run `python studio.py setup --check` to verify the remembered paths. |
| An update conflicts with my edit | Review Update protection or **Crafting → Review crafting conflicts**, select the desired values, save and Apply separately. |
| Cannot apply a client add-on | Close the selected game client and review again. Check Add-on settings for missing pack support or an unsupported integration; the server may stay running. |
| A game update replaced my add-ons | Use **Review reinstall** to review them on the new game baseline. Adapt unsupported integrations when support is available; the game update takes priority. |
| I want to undo an edit | **Studio tools → Change history → Review rollback → Revert saved changes**. Review newest related edits first; Apply loads the rollback. |

## Small beta scope

This is an **experimental beta for one local owner on Windows**, with 64-bit
Python **3.13** as the primary local target. Current dashboard observations and
recorded add-on verification cover different game/client versions, as described
above. See the [beta checklist and evidence](BETA_REVIEW.md); automated and
isolated native-client checks do not establish gameplay acceptance on every machine.

Back up your world/database with the game's own tools before testing. Studio's
configuration and pack backups cover different data and do not protect character
progress. Preserve Studio's complete private `data/` folder too. Use
[Support](../SUPPORT.md) for reports and [Security](../SECURITY.md) for private issues.
Repository visibility and any community invitation remain separate maintainer decisions.
