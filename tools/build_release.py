"""Build a clean portable ZIP from the reviewed source manifest."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PARTS = {'.git', 'data', 'dist', '__pycache__', '.vscode', '.idea', 'node_modules', '.vendor', '.test-tmp', '.venv'}


def release_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '\\' in name or ':' in name or re.search(r'[\x00-\x1f]', name) or '..' in path.parts or any(part in PRIVATE_PARTS for part in path.parts):
        return False
    if any(part == '.env' or part.startswith('.env.') for part in path.parts):
        return False
    return not (path.suffix.lower() in ('.sqlite', '.db', '.log', '.pid', '.pyc', '.lnk', '.before', '.after') or '.sqlite-' in path.name)


def build(root=ROOT, output=None):
    version = (root / 'VERSION').read_text('utf-8').strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', version):
        raise ValueError('Invalid release version.')
    manifest = root / 'release-files.txt'
    names = manifest.read_text('utf-8').splitlines() if manifest.is_file() else subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode('utf-8').split('\0')
    if len(names) != len(set(names)):
        raise ValueError('Duplicate source release paths.')
    files = [name for name in names if name and release_path(name) and not name.startswith('.github/')]
    for required in ('VERSION', 'README.md', 'server.py', 'installation.py', 'Install Studio.bat', 'Setup-Studio.ps1', 'Launch-Studio.ps1', 'web/index.html'):
        if required not in files:
            raise ValueError('Release requires tracked file: ' + required)
    destination = Path(output or root / 'dist')
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / ('mt2-singleplayer-studio-' + version + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name in sorted(files):
            source = root / name
            if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
                raise ValueError('Linked release sources are unsupported: ' + name)
            info = zipfile.ZipInfo('mt2-singleplayer-studio-' + version + '/' + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (destination / 'SHA256SUMS.txt').write_text(checksum + '  ' + archive.name + '\n', 'ascii')
    print(f'{archive.name}: {len(files)} reviewed source files; SHA256 {checksum}')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    build(output=parser.parse_args().output)
