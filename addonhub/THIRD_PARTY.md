# Third-party software and game material

The Hub's original source and example add-ons are covered by `LICENSE`. That does not relicense dependencies or the user's game installation.

## Installed Python wheels

`requirements.txt` pins:

| Distribution | Version | License | Use |
| --- | --- | --- | --- |
| lzokay | 2.1.0 | MIT | LZO compression/decompression for supported client pack objects |
| NumPy | 2.3.4 | BSD 3-Clause for NumPy itself; additional bundled-component notices apply to wheels | Acceleration for pack cryptographic word operations |

The Windows installer downloads binary wheels into `.vendor`. It retains wheel metadata and licenses. The lzokay notice is at `.vendor/lzokay-2.1.0.dist-info/licenses/LICENSE` or the wheel's equivalent recorded location. NumPy's full notice is at `.vendor/numpy-2.3.4.dist-info/LICENSE.txt`. Consult installed wheel metadata for the exact artifact and all bundled component notices; NumPy wheels may carry additional library licenses in their combined license file. Do not discard these notices when redistributing a runtime containing those wheels.

This source release excludes `.vendor` and therefore does not bundle those binary dependencies. Install them locally using the pinned requirements. Their upstream project identities are recorded in their installed `METADATA` files.

## Metin2 and the Singleplayer distribution

No game client executable, root pack, extracted game source, artwork, map image, server data, installation key/configuration, or full source export belongs to the source release. The Hub reads such material from an existing installation at runtime and can copy selected root packs/configuration into a private project-owned sandbox for local validation. Those copies are not covered by the Hub's MIT license and must not be shared as part of a Hub source release.

Metin2 and related names/material remain with their respective rights holders. The Singleplayer distribution's own terms remain applicable to its content. This alpha claims no official endorsement, partnership, public distribution permission, or verified runtime compatibility.
