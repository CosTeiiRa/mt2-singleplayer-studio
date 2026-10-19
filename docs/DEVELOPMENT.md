# Development guide

[Back to the overview](../README.md) · [Contributing](../CONTRIBUTING.md) · [All documentation](README.md)

## Project layout

```text
studio.py                  Portable Python entry point (serve / setup)
Start Studio.bat           Start the dashboard
Install Studio.bat         Connect an existing game installation
Stop Studio.bat            Stop Studio
Install Add-on Support.bat Install optional client pack dependencies
src/metin2_studio/         Python application
  addons/                 Add-on manager, client runtime and bundled examples
web/                      Dashboard HTML, CSS and JavaScript
scripts/windows/          PowerShell launch, setup and maintenance helpers
config/                   Release allowlist and pinned optional dependencies
tests/                    Automated tests and disposable fixture builders
tools/                    Developer, creator and packaging commands
docs/                     User, creator and architecture guides
data/                     Private local settings, history and backups (ignored)
dist/                     Generated portable ZIPs and checksums (ignored)
```

Work on the application in `src/metin2_studio/` and on the dashboard in `web/`.
Follow the [shared interface patterns](INTERFACE_PATTERNS.md) for game items,
notifications and deployment feedback across screens.
Run commands from the project root. Use `python studio.py serve` for the service
and `python studio.py setup --check` to inspect setup. The Windows buttons and
desktop shortcut use the same entry point. The source tree and portable ZIP use
the same layout; private state stays in `data/` when updating.

## Development and verification

Base Studio uses Python's standard library and plain HTML/CSS/JavaScript, with no
frontend build step. Client pack rebuilding additionally needs the optional
dependencies installed by **Install Add-on Support.bat**. Creator packaging tools
do not need those codec dependencies.

```powershell
python -m unittest discover -s tests -t . -v
node --test tests/apply_status.test.js tests/history.test.js tests/catalog.test.js tests/catalogue_sync.test.js tests/icons.test.js tests/item_explorer.test.js tests/item_views.test.js tests/operations.test.js tests/game_dashboard.test.js tests/navigation.test.js tests/quest_help.test.js tests/update_priority.test.js tests/addons.test.mjs tests/addons_view.test.mjs tests/addon_jobs.test.mjs
python tools/check_project.py
```

Self-contained tests run without the game. Integration tests are skipped unless a supported existing installation is configured or `METIN2_STUDIO_SERVER_ROOT` is set. They copy selected game files into disposable, ignored test folders; game assets are not committed. Actual builds, compiled quest behavior, in-game NPC rendering and real database transactions require separate local checks; CI does not claim to test a complete game installation.

The source CI workflow (`.github/workflows/ci.yml`, excluded from portable ZIPs) defines checks for Python 3.10/3.13 on Windows/Linux and JavaScript syntax/tests. `python tools/build_release.py` creates a portable ZIP and SHA-256 file in ignored `dist/`, from the reviewed source manifest. A pushed `beta-*` tag matching `VERSION` triggers a prerelease with that ZIP and checksum after checks pass; creating or pushing that tag is a separate publication decision. See [release notes](RELEASE_NOTES.md), [beta readiness](BETA_REVIEW.md) and [contribution guidance](../CONTRIBUTING.md).

## License and project boundaries

Original Studio code and documentation use the [MIT license](../LICENSE). The
existing [Add-on Hub notice](../src/metin2_studio/addons/LICENSE) and third-party dependency licenses
remain applicable. This does not license or grant redistribution rights for
Metin2 or Metin2 Singleplayer code, assets, executables or trademarks. Studio is
unofficial and requires an independently obtained working game installation.
Keep game material and private data out of source and release archives.
