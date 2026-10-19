"""Reproducible add-on ZIPs and bounded extraction. Payloads are never executed."""
import io
import json
from pathlib import Path
import stat
import tempfile
import zipfile

from .hubcore.packages import (MAX_FILE_BYTES, MAX_FILES, MAX_PACKAGE_BYTES, PackageError,
                               confined_file, load_package, logical_path, parse_json, sha256, validate_manifest)
from .versions import Version

MAX_ARCHIVE_BYTES = MAX_PACKAGE_BYTES + 2 * 1024 * 1024


def build_artifact(package_dir, output):
    package = load_package(package_dir)
    Version(package.manifest['version'])
    members = {'addon.json': (json.dumps(package.manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')}
    for entry in package.manifest['files']:
        logical_path('payload/' + entry['source'])
        members['payload/' + entry['source']] = package.files[entry['target']]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(members.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    data = buffer.getvalue()
    if len(data) > MAX_ARCHIVE_BYTES:
        raise PackageError('Compressed package exceeds the artifact size limit.')
    target = Path(output)
    if target.exists():
        raise PackageError('Artifact output already exists. Use a fresh output filename.')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {'id': package.manifest['id'], 'version': package.manifest['version'], 'sha256': sha256(data),
            'bytes': len(data), 'package_digest': package.digest, 'filename': target.name}


def archive_members(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_ARCHIVE_BYTES:
        raise PackageError('Add-on archive exceeds the size limit.')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_FILES * 3 + 1:
                raise PackageError('Too many ZIP entries.')
            files, names, total = {}, set(), 0
            for entry in entries:
                if entry.orig_filename != entry.filename:
                    raise PackageError('ZIP member name contains a NUL or an altered path.')
                name = entry.filename.rstrip('/') if entry.is_dir() else entry.filename
                logical_path(name)
                folded = name.casefold()
                if folded in names:
                    raise PackageError('Duplicate or case-colliding ZIP path: %s' % name)
                names.add(folded)
                mode = entry.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or (kind == stat.S_IFDIR) != entry.is_dir() and kind:
                    raise PackageError('Linked or special ZIP members are unsupported.')
                if entry.flag_bits & 1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise PackageError('Encrypted or unsupported ZIP compression.')
                if entry.is_dir():
                    continue
                limit = 256 * 1024 if name == 'addon.json' else MAX_FILE_BYTES
                if entry.file_size > limit:
                    raise PackageError('ZIP member exceeds its size limit: %s' % name)
                total += entry.file_size
                if total > MAX_PACKAGE_BYTES + 256 * 1024:
                    raise PackageError('Expanded add-on archive exceeds 64 MiB.')
                with archive.open(entry) as stream:
                    content = stream.read(limit + 1)
                if len(content) > limit or len(content) != entry.file_size:
                    raise PackageError('Invalid expanded ZIP member size.')
                files[name] = content
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise PackageError('Invalid add-on ZIP archive.') from exc
    if 'addon.json' not in files:
        raise PackageError('The ZIP must contain addon.json at its root.')
    try:
        manifest = validate_manifest(parse_json(files['addon.json']))
    except (UnicodeError, ValueError) as exc:
        raise PackageError('Invalid archived manifest: %s' % exc) from exc
    Version(manifest['version'])
    expected = {'addon.json'} | {'payload/' + row['source'] for row in manifest['files']}
    if set(files) != expected:
        raise PackageError('The ZIP may contain only its manifest and declared payload files.')
    # Parent/file collisions must fail before creating any output files.
    folded_files = {name.casefold() for name in files}
    for name in names:
        parents = Path(name).parents
        if any(parent.as_posix().casefold() in folded_files for parent in parents if parent.as_posix() != '.'):
            raise PackageError('ZIP directory/file collision.')
    return manifest, files


def extract_artifact(raw, destination):
    manifest, files = archive_members(raw)
    destination = Path(destination)
    if destination.exists():
        raise PackageError('Release destination already exists.')
    destination.mkdir(parents=True)
    for name, content in files.items():
        target = confined_file(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    package = load_package(destination)
    return package


def inspect_artifact(raw):
    scratch = Path(__file__).resolve().parents[1] / '.test-tmp'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='artifact-', dir=scratch) as temporary:
        package = extract_artifact(raw, Path(temporary) / 'release')
        return {'manifest': package.manifest, 'package_digest': package.digest, 'sha256': sha256(raw), 'bytes': len(raw)}
