# beta-1.0.0

First distributable beta: a local Studio for your existing Metin2 Singleplayer Linux/Docker server.

Download and extract the portable ZIP, install Python 3.10+, run **Install Studio.bat** and choose your existing **Serwer** folder. Then use **Start Studio.bat** or the desktop shortcut. Setup does not install the game or modify/restart it. No pip/npm packages are required.

Includes drop/chest editing, item search/descriptions/usage, existing and new quests, Cube/native NPC crafting, economy views/exports, backups/rollback, custom update conflict review and pending Apply counts.

Compatibility: Windows 10/11; game package 2.2.106 was used for local integration checks. This is not a universal editor for arbitrary Metin2 distributions. Keep a game backup and preserve Studio's private `data/` folder when updating. New quest scripts and actual game changes remain opt-in through Review, Save and Apply.

The ZIP contains Studio source only. Game assets, credentials, databases and local history are excluded. `SHA256SUMS.txt` lists the portable ZIP checksum. Full installation steps, troubleshooting and limitations are in README.md.
