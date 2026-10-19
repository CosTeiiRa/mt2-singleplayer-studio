"""Stage official packages; archive custom differences and give the game priority."""
import hashlib
import json
from pathlib import PurePosixPath
import re
import secrets
import stat
import subprocess
import threading
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import zipfile


MANIFEST = 'https://api.github.com/repos/TieruYT/metin2-playerbots/contents/update-manifest-mt2009.json?ref=main'
MAX_PACKAGE = 600 * 1024 * 1024
MAX_EXPANDED = 4 * 1024 * 1024 * 1024


def file_hash(path):
    checksum = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def package_members(archive):
    names, size = {}, 0
    for item in archive.infolist():
        name = item.orig_filename
        parts = PurePosixPath(name).parts
        if name != item.filename or not parts or str(PurePosixPath(name)) != name.rstrip('/') or name.startswith(('/', '\\')) or '\\' in name or any(part in ('.', '..') or ':' in part or part.endswith((' ', '.')) or re.search(r'[\x00-\x1f]', part) or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part) for part in parts):
            raise ValueError('The update contains an unsafe path.')
        mode = item.external_attr >> 16
        if stat.S_ISLNK(mode) or item.flag_bits & 1:
            raise ValueError('Linked or encrypted package entries are not supported.')
        if item.is_dir():
            continue
        key = name.casefold()
        if key in names:
            raise ValueError('The update contains duplicate or case-colliding file paths.')
        names[key] = item
        size += item.file_size
        if len(names) > 100000 or item.file_size > MAX_PACKAGE or size > MAX_EXPANDED:
            raise ValueError('The update exceeds the package safety limits.')
    if 'version' not in names:
        raise ValueError('Choose a server update ZIP with VERSION at its root, not a client package or enclosing folder.')
    if names['version'].file_size > 1024:
        raise ValueError('The package version marker is too large.')
    return names


class ProtectedUpdates:
    def __init__(self, studio):
        self.studio = studio
        self.folder = studio.state / 'update-packages'
        self.folder.mkdir(exist_ok=True)
        self.job = {'status': 'idle', 'message': ''}
        self.available = None

    def metadata(self, ident):
        if not re.fullmatch(r'[a-f0-9]{24}', str(ident)):
            raise ValueError('Invalid staged package.')
        path = self.folder / (ident + '.json')
        if not path.is_file():
            raise ValueError('The staged package is no longer available.')
        return json.loads(path.read_text('utf-8'))

    def stage(self, stream, length, expected='', provenance='manual'):
        if not 1 <= length <= MAX_PACKAGE:
            raise ValueError('Choose an update ZIP smaller than 600 MiB.')
        expected = str(expected).strip().lower()
        if expected and not re.fullmatch(r'[a-f0-9]{64}', expected):
            raise ValueError('Expected SHA-256 must contain 64 hexadecimal characters.')
        ident = secrets.token_hex(12)
        path = self.folder / (ident + '.zip')
        checksum, remaining = hashlib.sha256(), length
        try:
            with path.open('xb') as output:
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError('The package upload was interrupted.')
                    output.write(chunk)
                    checksum.update(chunk)
                    remaining -= len(chunk)
            actual = checksum.hexdigest()
            if expected and expected != actual:
                raise ValueError('SHA-256 mismatch. Nothing was installed.')
            with zipfile.ZipFile(path) as archive:
                members = package_members(archive)
                version = archive.read(members['version']).decode('utf-8-sig').strip()
                if not re.fullmatch(r'[A-Za-z0-9_.+\-]{1,60}', version):
                    raise ValueError('Unsupported package version marker.')
                protected = 'linux-port/protected' in members
                if (self.studio.root / 'linux-port/PROTECTED').exists() and not protected:
                    raise ValueError('This installation requires a protected server package. Nothing was installed.')
            meta = {'id': ident, 'version': version, 'sha256': actual, 'verified': bool(expected), 'provenance': provenance, 'files': len(members), 'bytes': length, 'kind': 'protected' if protected else 'ordinary', 'at': time.time()}
            (self.folder / (ident + '.json')).write_text(json.dumps(meta), 'utf-8')
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return self.preview(ident)

    def preview(self, ident):
        meta = self.metadata(ident)
        path = self.folder / (ident + '.zip')
        if file_hash(path) != meta['sha256']:
            raise ValueError('The staged package changed. Import it again.')
        with zipfile.ZipFile(path) as archive:
            members = package_members(archive)
            incoming = {}
            for record in self.studio.workspace.tracked():
                item = members.get(record['path'].casefold())
                if item:
                    if item.file_size > 1800000:
                        raise ValueError('A customised configuration became too large for a safe merge.')
                    incoming[record['path']] = archive.read(item)
        report = self.studio.workspace.scan(incoming, kind='package', package=ident)
        report['package'] = meta
        report['notice'] = 'Install the game update first. Original and custom values are archived and retained in a pending merge review. Choose how to merge them afterwards in Studio. Build/Apply remains separate.'
        return report

    def check(self):
        request = Request(MANIFEST, headers={'Accept': 'application/vnd.github.raw+json', 'User-Agent': 'Metin2-Server-Studio'})
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError('The release manifest is too large.')
            manifest = json.loads(raw)
            key = 'serverProtected' if (self.studio.root / 'linux-port/PROTECTED').exists() else 'server'
            component = manifest.get(key) or {}
            url, expected = str(component.get('url', '')), str(component.get('sha256', '')).lower()
            parsed = urlparse(url)
            if parsed.scheme != 'https' or parsed.netloc.lower() != 'github.com' or not parsed.path.startswith('/TieruYT/metin2-playerbots/releases/download/') or not re.fullmatch('[a-f0-9]{64}', expected):
                raise ValueError('The official manifest does not provide a supported server package.')
            self.available = {'url': url, 'sha256': expected, 'version': str(component.get('version', '')), 'kind': key, 'checkedAt': time.time()}
            return self.available
        except (OSError, ValueError) as error:
            raise ValueError('Could not read a verified official release offer. You can import a downloaded ZIP with its published SHA-256.') from error

    def download(self):
        if not self.available:
            raise ValueError('Check the official release first.')
        if self.job['status'] == 'running':
            raise ValueError('An update operation is already running.')
        offer = dict(self.available)
        self.job = {'status': 'running', 'message': 'Downloading the verified release package…', 'started': time.time()}
        def run():
            try:
                with urlopen(Request(offer['url'], headers={'User-Agent': 'Metin2-Server-Studio'}), timeout=30) as response:
                    final = urlparse(response.geturl())
                    if final.scheme != 'https' or final.netloc.lower() not in ('github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'):
                        raise ValueError('The release download redirected outside supported GitHub release hosts.')
                    length = int(response.headers.get('Content-Length', 0))
                    if not 1 <= length <= MAX_PACKAGE:
                        raise ValueError('The release has no supported bounded download length. Import its ZIP manually.')
                    report = self.stage(response, length, offer['sha256'], 'official manifest')
                self.job = {'status': 'succeeded', 'message': 'Package ready for customisation review.', 'report': report}
            except Exception as error:
                self.job = {'status': 'failed', 'message': str(error)}
        threading.Thread(target=run, daemon=True).start()
        return self.job

    def install(self, values):
        with self.studio.lock:
            report, changes, rebased = self.studio.workspace.reconciliation(values)
            if report['kind'] != 'package':
                raise ValueError('Preview a staged server package first.')
            meta = self.metadata(report['package'])
            if not meta['verified']:
                raise ValueError('Installation requires the expected SHA-256 from the release manifest. Import again with that checksum.')
            if self.job['status'] == 'running' or self.studio.server_busy():
                raise ValueError('Wait for the current update or apply operation.')
            tracking = self.studio.workspace.signature()
            if tracking != report.get('tracking'):
                raise ValueError('Your custom changes changed since package review. Preview the package again.')
            # Re-hash immediately before dispatch; the native updater verifies it again.
            package = self.folder / (meta['id'] + '.zip')
            if file_hash(package) != meta['sha256']:
                raise ValueError('The staged package changed. Import it again.')
            self.job = {'status': 'running', 'message': 'Installing package files with the native updater; no build is started.', 'started': time.time()}
            self.studio.workspace.set_preference('nativeUpdatePending', {'package': meta, 'ready': False, 'phase': 'installing'})
            self.studio.job = {'status': 'running', 'kind': 'update-files', 'lines': ['Installing the reviewed server package.'], 'started': time.time()}
            threading.Thread(target=self._install, args=(meta, report, changes, rebased), daemon=True).start()
            return self.job

    def _install(self, meta, report, changes, rebased):
        package = self.folder / (meta['id'] + '.zip')
        result_file = self.folder / (meta['id'] + '.installed.json')
        try:
            # Preserve displaced work outside the game before the native updater
            # runs. Restoration is a separate, deliberate edit after compatibility
            # has been reviewed; package installation never writes custom values.
            backup_id = 'update-custom-' + secrets.token_hex(8)
            backup = self.studio.state / 'updates' / backup_id
            backup.mkdir(parents=True)
            archived = []
            for index, row in enumerate(report['files']):
                record = row['record']
                for suffix, raw in (('original', record['original']), ('custom', record['custom']), ('before-update', row['current'])):
                    if raw is not None:
                        (backup / (str(index) + '.' + suffix)).write_bytes(raw)
                archived.append({'path': record['path'], 'index': index, 'version': record['version']})
            archive_meta = {'package': meta, 'policy': 'game-first', 'files': archived}
            (backup / 'manifest.json').write_text(json.dumps(archive_meta, indent=2), 'utf-8')
            args = ['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(self.studio.app / 'Install-ReviewedUpdate.ps1'), '-ServerRoot', str(self.studio.root), '-PackagePath', str(package), '-ExpectedHash', meta['sha256'], '-PackageVersion', meta['version'], '-PackageKind', meta['kind'], '-ResultPath', str(result_file)]
            result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode or not result_file.is_file():
                raise ValueError('The native package installation did not finish. Its original rollback rules apply; inspect the native launcher before retrying.')
            native = json.loads(result_file.read_text('utf-8-sig'))
            if not isinstance(native, dict):
                raise ValueError('Native installation returned an unsupported receipt. Review installed-file recovery before applying.')
            self.studio.workspace.set_preference('nativeUpdatePending', {'package': meta, 'nativeBackup': native.get('Backup'), 'ready': False})
            archive_meta['nativeBackup'] = native.get('Backup')
            (backup / 'manifest.json').write_text(json.dumps(archive_meta, indent=2), 'utf-8')
            # Verify the native result and update Studio's tracking only. Do not
            # rewrite any game file after the game's own updater has installed it.
            with self.studio.lock:
                for row in report['files']:
                    path = self.studio.safe(self.studio.root / row['record']['path'])
                    observed = path.read_bytes() if path.exists() else None
                    if observed != row['incoming']:
                        raise ValueError('An affected file differs from the reviewed package. Studio reconciliation paused; inspect the native updater result. No Studio edits were restored.')
                custom_files = []
                for row in report['files']:
                    rel = row['record']['path']
                    path = self.studio.safe(self.studio.root / rel)
                    custom_files.append((path, row['current'], row['incoming']))
                deferred = {row['record']['path']: (row['record']['original'], row['record']['custom'], row['incoming'], row['record']['version']) for row in report['files']}
                self.studio.workspace.record_commit(custom_files, 'Installed game update ' + meta['version'] + '; custom merge deferred', backup_id, {'deferred': deferred})
                self.studio.workspace.set_preference('nativeUpdatePending', {'package': meta, 'nativeBackup': native.get('Backup'), 'customBackup': backup_id, 'ready': True})
            self.job = {'status': 'succeeded', 'message': 'Game package installed. Original and custom values are preserved for a later merge review. Reload Studio; you can Apply the game update now or review custom merges first.', 'package': meta, 'requiresReload': True}
            self.studio.job = {'status': 'files-ready', 'lines': [self.job['message']]}
        except Exception as error:
            self.job = {'status': 'failed', 'message': str(error)}
            self.studio.job = {'status': 'failed', 'lines': [str(error)]}
