# Add-on Menu

A bundled optional API-v2 add-on that provides one **Add-ons** button in-game.
It is listed first in Studio and first in its own menu.

## How to use

1. Install and enable **Add-on Menu** in Studio with the game client closed.
2. Launch your normal client and enter a character.
3. Click **Add-ons** near the top-left, above the Pocket Wiki button.
4. Choose an installed add-on and click **Open** or **Open atlas**.

No shortcut is required. Escape or the close button closes the menu. Existing
extension shortcuts remain available. Use Previous/Next for additional entries.

## Availability

Disabled add-ons stay listed and can be enabled in Studio. Extensions with no
window run automatically; failures are marked unavailable. Atlas availability
depends on the current map. Multiple registered windows get separate actions.
Already visible windows are brought forward rather than closed.

Disabling/removing Add-on Menu removes its launcher and leaves other extensions
installed. It does not modify server data or provide in-game installation controls.
The installed menu works with Studio closed. Source: `payload/addon_menu.py`.
