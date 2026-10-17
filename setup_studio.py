"""Configure an existing game, or inspect setup without starting any service."""
import argparse
import json
from pathlib import Path
from installation import load_settings, resolve_settings, save_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-root', type=Path)
    parser.add_argument('--port', type=int)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--check', action='store_true', help='Validate and print current setup; do not write files.')
    args = parser.parse_args()
    try:
        # An explicit folder repairs an invalid settings file without discarding
        # any world history. The old file is retained as a recovery copy.
        try:
            saved = load_settings()
        except ValueError:
            if not args.server_root or args.check:
                raise
            from installation import SETTINGS_PATH
            backup = SETTINGS_PATH.with_suffix('.json.previous')
            backup.write_bytes(SETTINGS_PATH.read_bytes())
            saved = {}
        settings = resolve_settings(args.server_root, args.port, args.state, saved=saved)
        if not args.check:
            save_settings(settings)
        print(json.dumps(settings, ensure_ascii=True))
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    main()
