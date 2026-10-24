# beta-1.21.0 — simpler Apply and Legacy Mount Support

Review saved server files and client add-ons together, then apply either group
or both from one progress screen. Select all add-ons or choose individual ones;
skipped add-ons retain their settings and pending reapply reminders. Apply now
explains blockers directly, including an open game client and required server
files. A successful server deployment remains recorded if the client step fails.

Game updates show a persistent notice when saved add-ons need reapplying. Review
them against the updated game baseline before applying. Editor reviews also offer
Save & apply, and build-only validation lives under Advanced.

Legacy Mount Support is a new server/client extension in Discover. It coordinates
legacy seal activation with narrowly owned model and seal-data corrections. It
checks the exact engine and installed codec, preserves native/upstream fixes,
refuses unavailable appearances, and supports reviewed reapply, disable and
removal with recovery. Activation requires a server build and restart. Mounted
combat is separate and is not included. No game assets, packs, keys or executables
are distributed in the add-on.

The inspected server 2.2.123/client 2.0.125 target has 98 usable legacy seals,
15 seals refused for missing models, 21 untouched native seals and three needed
client model mappings. Seal 71128 already supplies the data fix. Activation and
cleanup quests compiled with the installed compiler in an isolated container;
connected riding and expiry acceptance remain pending.

The exact client 2.0.125 executable is now supported after isolated startup,
import, widgets, shortcuts and lifecycle checks for all four existing client
add-ons, followed by exact copied-pack restoration. These checks do not establish
logged-in gameplay. See [verification evidence](ADDON_TESTING.md).

Download the portable source ZIP and SHA256SUMS.txt, extract into a permanent
Studio folder outside the game, and follow [How to start](../README.md#how-to-start).
Existing Studio data remains separate from the release files. This is an
experimental beta; fresh-machine and independent gameplay acceptance are still
open in the [beta checklist](BETA_REVIEW.md).
