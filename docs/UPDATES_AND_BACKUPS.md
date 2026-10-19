# Updates, backups and local data

[Back to the overview](../README.md) · [All documentation](README.md)

Preserve your Studio history and game/world backups separately. For interrupted operations, use the [recovery guide](USER_GUIDE.md#backups-and-recovery).

## Local data, backups and privacy

- Local setup is saved in **`data/studio-settings.json`**. It contains the selected server path, port and data path, not database credentials.
- By default each selected game folder gets its own **`data/worlds/<id>/`**. This holds `workspace.sqlite`, `backups/`, add-on state/backups under `addons/`, cached sources and reviewed update packages. Existing `economy.sqlite` archives are retained when present. Setup prints the exact location.
- Preserve the **whole `data/` folder** when updating Studio. Crafting reconciliation, rollback, drafts and history depend on it. A selected data folder is bound to its server path to prevent using another world's history accidentally.
- Backups can include the game's original `.env`, so treat local data as private. `data/`, databases, logs, credentials and built ZIPs are excluded from Git. The release builder also excludes them.
- Studio listens only on `127.0.0.1`. It is a local owner tool; do not expose it through a public bind, proxy or port forwarding.

If migrating from an older Studio installation, retain its data folder and configure the same game with `scripts/windows/Setup-Studio.ps1 -ServerRoot "...\Serwer" -StateDir "...\old-studio\data" -NoShortcut -NonInteractive`. This preserves the old history instead of beginning a separate one.

## Updating the game or Studio

**Game update:** the game and its updates are authoritative. Studio and add-ons must adapt to the game; their compatibility must never require holding back a game update. The original game launcher can update independently of Studio or the add-on service.

Studio's **Update protection** workflow stages/reviews the package, archives affected tracked original/custom/current files under the world's private `updates/update-custom-*/` folder, and installs the game's values first. It retains original/custom/game values in a persistent pending merge review. The game can be built and played before those choices are resolved. Files absent from the package are left alone. Keep full game/database backups as well.

After an external launcher update, **Scan installed files / pending merges** compares the three versions. **Keep game; decide later** records the current game values without changing game files and retains your custom work for later. When ready, choose each merge value and **Review selected merge**, then save; unrelated game changes remain intact. Resolve a file's pending merge before making another direct edit to that file.

Native crafting has its own conflict review. A pending native game-package build
does not reapply Studio crafting overrides; review them separately against the
updated database. Server Build/Apply remains a separate step.

**Client add-ons after a game update:** when the managed packs are replaced with
clean game files, Studio offers **Review reinstall**. It proposes composing the
installed add-on code and saved settings over the new game baseline. Review and
Apply explicitly; removing the last add-on then restores that updated baseline.
Mixed external changes that still contain Hub files remain conflicts for
inspection. Studio does not restore an old game pack over the update.

An unknown executable or changed integration point can pause add-on changes until
the adapter supports it. Update and play the game normally in the meantime; a new
playable copy is not required. A version outside the publisher's declared list
alone means **Compatibility unverified**, not proven incompatibility. Refresh
Pocket Wiki reference data after game content changes.

**Studio update:** stop Studio, extract the new release over the same Studio folder while preserving `data/`, then start it again. If installing into a new folder, copy your private `data/` folder across before setup/start. Git users can pull a newer version while keeping the ignored data. Updating Studio does not apply game configurations automatically. If moved, run **scripts/windows/Create-DesktopShortcut.ps1** to create a shortcut to the new location.

When upgrading from the older flat source layout, use **Start Studio.bat** and
refresh the desktop shortcut with **scripts/windows/Create-DesktopShortcut.ps1**.
The application now starts through `studio.py`; existing settings and world data
remain in `data/` and require no migration.
