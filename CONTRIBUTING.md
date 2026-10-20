# Contributing to Studio

Studio is an experimental beta. Use [GitHub Issues](https://github.com/CosTeiiRa/mt2-singleplayer-studio/issues)
to discuss a proposed change and submit focused pull requests. Repository access
is required while the beta remains private. Use [SUPPORT.md](SUPPORT.md) for bugs
and [SECURITY.md](SECURITY.md) for sensitive reports.

## Development scope

Follow the [project layout](docs/DEVELOPMENT.md#project-layout): Python application code
belongs in `src/metin2_studio/`, frontend files in `web/`, and Windows helpers in
`scripts/windows/`. Use package imports under `metin2_studio`; keep private state
in the ignored `data/` folder. Add distributable files to
`config/release-files.txt` so a fresh portable ZIP includes them.

Studio is optional tooling beside the game. Game updates take priority; retain
custom intent for later user review rather than restoring old customisations over
an update. Server Save, server Apply and client add-on Apply have separate review,
backup and recovery responsibilities. Preserve those boundaries.

Use disposable fixtures for destructive, interrupted-operation and pack tests.
Do not commit game assets, executable binaries, database data, local state,
credentials or generated support reports. Do not require a new playable client
copy for ordinary users. Explain compatibility evidence separately from publisher
declarations and from logged-in gameplay acceptance.

Run the [developer checks](docs/DEVELOPMENT.md#development-and-verification) for the affected area and
document game-dependent checks that were skipped. A passing build or mocked UI
test does not prove connected gameplay. Include the problem, resulting behavior,
validation and limits when submitting a change.

## Licensing and dependencies

Original Studio code and documentation use the root [MIT license](LICENSE).
Retain existing notices, including [Add-on Hub's notice](src/metin2_studio/addons/LICENSE).
Game code, assets, trademarks and separately licensed third-party dependencies
are not relicensed by Studio. Add only material you have permission to contribute;
record new dependency licenses and keep game assets out of distributable fixtures.

Creators of client extensions should start with the [add-on package
requirements](docs/ADDONS.md#developer-package-requirements) and [API v2
reference](docs/ADDON_API_V2.md). Add-ons have their own license and release notes.
