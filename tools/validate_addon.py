#!/usr/bin/env python3
"""Validate local add-on packages without importing or executing their payload."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROJECT), str(PROJECT / 'src')]

from metin2_studio.addons.hubcore.packages import PackageError, load_package


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packages', nargs='+', type=Path, help='Package directories containing addon.json and payload/')
    parser.add_argument('--json', action='store_true', help='Print machine-readable validation results')
    args = parser.parse_args(argv)
    results = []
    for path in args.packages:
        try:
            package = load_package(path)
            results.append({'ok': True, 'path': str(path), 'id': package.manifest['id'],
                            'version': package.manifest['version'], 'files': len(package.files),
                            'package_digest': package.digest})
        except (PackageError, OSError, ValueError) as exc:
            results.append({'ok': False, 'path': str(path), 'error': str(exc)})
    if args.json:
        print(json.dumps({'ok': all(item['ok'] for item in results), 'results': results}, indent=2))
    else:
        for item in results:
            if item['ok']:
                print('VALID %s %s (%s files)\n  %s' % (item['id'], item['version'], item['files'], item['package_digest']))
            else:
                print('INVALID %s\n  %s' % (item['path'], item['error']), file=sys.stderr)
    return 0 if all(item['ok'] for item in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
