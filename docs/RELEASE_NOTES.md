# beta-1.20.0 — readable maps and creature icons

Studio reads English map labels from the installed client and game translations.
Original configured names remain under Sources & coverage. Names without an
English source use readable directory labels where possible.

Dungeon backgrounds prefer the client's atlas artwork. Monkey Dungeon uses the
game's walkable navigation drawing because its terrain texture is almost black.
Map copies share a drawing only when their navigation files match exactly. Areas
without artwork are explicitly labelled as spawn diagrams.

NPCs and mining deposits have distinct category icons when portraits are absent.
Available mining artwork and client map images join the shared offline cache.
Client and server assets are read only; no game files or engine behavior change.
The release checks also fix Python 3.10 test-fixture compatibility and run every
JavaScript test file.

This beta also includes quick atlas category filters and list-side previews,
custom crafting/quest filters, catalogue sync, and Economy shortcuts to the game
dashboard in place of Studio's duplicate collector. Previous Studio economy
history and notes remain available as an archive download.

The publication package uses GitHub noreply author identities, updated setup and
support guides, and a source-only ZIP with a SHA-256 checksum. Earlier development
changes remain in [CHANGELOG.md](../CHANGELOG.md); this is the only retained beta
release.

Start with [How to start](../README.md#how-to-start). This is an experimental beta
for existing Windows/Linux-Docker game installations. Automated checks do not
replace fresh-machine and logged-in gameplay acceptance; see
[beta scope and testing](BETA_REVIEW.md).
