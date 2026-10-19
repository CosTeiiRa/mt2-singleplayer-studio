# Contributing to Studio

The project is preparing a small private beta. No repository publication or
community invitation is implied by these files. Agree on a proposed change with
the maintainer through the private beta conversation until contribution channels
are announced. Use [SUPPORT.md](SUPPORT.md) for bugs and [SECURITY.md](SECURITY.md)
for sensitive reports.

## Development scope

Studio is optional tooling beside the game. Game updates take priority; retain
custom intent for later user review rather than restoring old customisations over
an update. Server Save, server Apply and client add-on Apply have separate review,
backup and recovery responsibilities. Preserve those boundaries.

Use disposable fixtures for destructive, interrupted-operation and pack tests.
Do not commit game assets, executable binaries, database data, local state,
credentials or generated support reports. Do not require a new playable client
copy for ordinary users. Explain compatibility evidence separately from publisher
declarations and from logged-in gameplay acceptance.

Run the [developer checks](README.md#development-and-verification) for the affected area and
document game-dependent checks that were skipped. A passing build or mocked UI
test does not prove connected gameplay. Include the problem, resulting behavior,
validation and limits when submitting a change.

## Licensing and dependencies

Original Studio code and documentation use the root [MIT license](LICENSE).
Retain existing notices, including [Add-on Hub's notice](addonhub/LICENSE).
Game code, assets, trademarks and separately licensed third-party dependencies
are not relicensed by Studio. Add only material you have permission to contribute;
record new dependency licenses and keep game assets out of distributable fixtures.

Creators of client extensions should start with the [README developer
requirements](README.md#developer-package-requirements) and [API v2
reference](docs/ADDON_API_V2.md). Add-ons have their own license and release notes.
