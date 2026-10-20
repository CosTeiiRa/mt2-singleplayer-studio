# Small beta support

Studio is an unofficial local tool for an existing Metin2 Singleplayer
installation. The initial beta targets Windows and the versions listed in the
[beta checklist](docs/BETA_REVIEW.md). It does not include the game.

Report reproducible bugs in [GitHub Issues](https://github.com/CosTeiiRa/mt2-singleplayer-studio/issues/new/choose).
Repository access is required while the beta remains private. Use
[SECURITY.md](SECURITY.md) for sensitive reports; do not post security details or
private game files in an issue.

## Report a problem

Include Studio version, Windows and Python versions, game server/client versions,
the affected page or add-on, the steps, expected result and actual result. Say
whether the problem happened during Review, Save, server Apply or add-on Apply.
Include an error message or a redacted screenshot when useful. Mark whether you
have a current world backup and whether the game still starts.

For add-on issues, **Add-on settings** provides an allowlisted support report.
It omits paths, tokens, settings, repository URLs and game content. Review any
attachment before sharing it. Apply logs and screenshots can contain local paths
or user-entered text and need separate review.

Never share `.env`, `data/`, Studio SQLite files, full backups, account/player
records, credentials, session tokens, game archives or client packs. Studio's
private data can include original `.env` credentials even when the UI hides them.

## When an operation is interrupted

Preserve the complete Studio data folder and the game's own backups. Do not delete
journals, edit SQLite records, reset pending changes or repeatedly Apply to clear
an error. The [operator recovery guide](docs/USER_GUIDE.md#backups-and-recovery)
explains which recovery belongs to a file save, server deployment or client pack
transaction. If the UI blocks recovery because files changed externally, retain
both versions and report it privately.

Use the game's backup/restore tools for world and database recovery. Studio's
configuration history and pack backups are not a character/database backup.
Security-sensitive reports follow [SECURITY.md](SECURITY.md).
