"""Public GitHub source repositories; no credentials or build-script execution."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import re
import stat
from urllib.parse import quote, urlsplit
import zipfile

from .artifacts import MAX_ARCHIVE_BYTES, build_artifact
from .collections import COLLECTION_LIMIT, validate_collection
from .hubcore.packages import (MAX_FILE_BYTES, MAX_PACKAGE_BYTES, PackageError, confined_file,
                               logical_path, parse_json, sha256, validate_manifest)
from .transport import HTTPStatusError, https_url
from .versions import Version

COMMIT = re.compile(r'^[0-9a-f]{40}$')
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')
README_LIMIT = 256 * 1024
API_LIMIT = 2 * 1024 * 1024


def identity(url):
    normalized = https_url(url)
    parts = urlsplit(normalized)
    if parts.hostname not in ('github.com', 'www.github.com'):
        return None
    # Existing GitHub-hosted catalog release URLs remain catalog sources.
    if '/releases/download/' in parts.path:
        return None
    segments = parts.path.strip('/').split('/')
    if len(segments) != 2 or parts.query or parts.fragment:
        raise ValueError('Use a GitHub repository URL such as https://github.com/owner/repository.')
    owner, repo = segments
    repo = repo[:-4] if repo.lower().endswith('.git') else repo
    if not NAME.fullmatch(owner) or not NAME.fullmatch(repo) or repo in ('.', '..'):
        raise ValueError('Invalid GitHub owner or repository name.')
    owner, repo = owner.lower(), repo.lower()
    return {'owner': owner, 'repository': repo, 'url': 'https://github.com/%s/%s' % (owner, repo)}


def manifest_digest(manifest):
    return sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8'))


def allowed_release(release, channel):
    if channel == 'development':
        return release.get('kind') == 'development'
    return release.get('kind') != 'development' and (channel == 'prerelease' or not release.get('prerelease'))


class GitHubSource:
    def __init__(self, fetch):
        self.fetch = fetch

    def _get(self, url, limit):
        try:
            raw = self.fetch(url, limit)
            if not isinstance(raw, bytes) or len(raw) > limit:
                raise ValueError('GitHub response exceeds its size limit.')
            return raw
        except HTTPStatusError as exc:
            if exc.status in (403, 429):
                raise ValueError('GitHub refused this request; its public API rate limit may be reached. Retry later.') from exc
            raise

    def api(self, source, suffix=''):
        url = 'https://api.github.com/repos/%s/%s%s' % (source['owner'], source['repository'], suffix)
        return parse_json(self._get(url, API_LIMIT), API_LIMIT)

    def resolve(self, source, ref):
        if not isinstance(ref, str) or not 0 < len(ref) <= 256 or any(ord(c) < 32 for c in ref):
            raise ValueError('GitHub returned an invalid source reference.')
        data = self.api(source, '/commits/' + quote(ref, safe=''))
        commit = data.get('sha') if isinstance(data, dict) else None
        if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
            raise ValueError('GitHub did not resolve this reference to a full commit SHA.')
        return commit

    def raw_url(self, source, commit, name):
        if not COMMIT.fullmatch(commit):
            raise ValueError('A pinned source commit is required.')
        return 'https://raw.githubusercontent.com/%s/%s/%s/%s' % (source['owner'], source['repository'], commit, quote(name, safe='/'))

    def optional(self, source, commit, name, limit):
        try:
            return self._get(self.raw_url(source, commit, name), limit)
        except HTTPStatusError as exc:
            if exc.status == 404:
                return None
            raise

    def inspect(self, source, release, commit=None):
        commit = commit or self.resolve(source, release['source_ref'])
        path, declaration_hash = '', None
        if release.get('collection'):
            raw = self.optional(source, commit, 'addons.json', COLLECTION_LIMIT)
            if raw is None:
                raise ValueError('This collection version is missing root addons.json.')
            declaration = validate_collection(parse_json(raw, COLLECTION_LIMIT))
            entry = next((row for row in declaration['addons'] if row['id'] == release['addon_id']), None)
            if not entry:
                raise ValueError('This collection version does not list the requested add-on.')
            path, declaration_hash = entry['path'], manifest_digest(declaration)
        prefix = path + '/' if path else ''
        try:
            manifest = validate_manifest(parse_json(self._get(self.raw_url(source, commit, prefix + 'addon.json'), 256 * 1024)))
        except HTTPStatusError as exc:
            if exc.status == 404:
                raise ValueError('Unsupported repository layout: addon.json is missing at the declared package path ' + (path or '(repository root)') + '.') from exc
            raise
        if release.get('addon_id') and release['addon_id'] != manifest['id']:
            raise ValueError('The declared collection add-on id does not match its addon.json.')
        Version(manifest['version'])
        if release['kind'] != 'development' and manifest['version'] != release['version']:
            raise ValueError('GitHub release version does not match addon.json. Match the release tag (optional v prefix) to the package version.')
        readme_path = prefix + 'README.md'
        raw_readme = self.optional(source, commit, readme_path, README_LIMIT)
        if raw_readme is None and path:
            readme_path = 'README.md'
            raw_readme = self.optional(source, commit, readme_path, README_LIMIT)
        readme = raw_readme.decode('utf-8-sig') if raw_readme is not None else ''
        resolved = {**copy.deepcopy(release), 'commit': commit, 'package_version': manifest['version'],
                    'addon_id': manifest['id'], 'package_path': path, 'collection_digest': declaration_hash,
                    'manifest_digest': manifest_digest(manifest), 'readme': readme,
                    'documentation_url': source['url'] + '/blob/' + commit + '/' + quote(readme_path, safe='/')}
        if release['kind'] == 'development':
            resolved['release_notes'] = str(manifest.get('release_notes') or 'No changelog provided for this development snapshot.')[:4000]
        return resolved, manifest

    def releases(self, rows, branch, entry=None):
        releases, versions = [], set()
        prefix = entry['id'] + '/' if entry else ''
        for row in rows:
            if not isinstance(row, dict) or row.get('draft'):
                continue
            tag = row.get('tag_name')
            if not isinstance(tag, str) or len(tag) > 256 or not tag.startswith(prefix):
                continue
            suffix = tag[len(prefix):]
            try:
                version = Version(suffix[1:] if suffix.startswith('v') else suffix)
            except ValueError:
                continue
            if version.text in versions:
                raise ValueError('Multiple GitHub releases declare the same add-on version.')
            versions.add(version.text)
            releases.append({'version': version.text, 'kind': 'release', 'source_ref': tag, 'commit': None,
                'prerelease': bool(row.get('prerelease') or version.pre), 'withdrawn': False, 'reason': '',
                'release_notes': str(row.get('body') or 'No release notes provided.')[:4000]})
        releases.sort(key=lambda row: (Version(row['version']), row['version']), reverse=True)
        releases.append({'version': 'development', 'kind': 'development', 'source_ref': branch, 'commit': None,
                         'prerelease': True, 'withdrawn': False, 'reason': '',
                         'release_notes': 'Default branch development snapshot; select it explicitly to test unreleased code.'})
        if entry:
            for release in releases:
                release.update(addon_id=entry['id'], package_path=entry['path'], collection=True)
        return releases

    def discover(self, source, channel):
        metadata = self.api(source)
        if not isinstance(metadata, dict) or metadata.get('private') is not False or metadata.get('disabled'):
            raise ValueError('Choose an accessible public GitHub repository.')
        branch = metadata.get('default_branch')
        if not isinstance(branch, str) or not 0 < len(branch) <= 256:
            raise ValueError('This GitHub repository has no usable default branch.')
        branch_commit = self.resolve(source, branch)
        raw_collection = self.optional(source, branch_commit, 'addons.json', COLLECTION_LIMIT)
        declaration = validate_collection(parse_json(raw_collection, COLLECTION_LIMIT)) if raw_collection is not None else None
        if declaration and self.optional(source, branch_commit, 'addon.json', 256 * 1024) is not None:
            raise ValueError('Ambiguous repository layout: use root addon.json or addons.json with separate add-on folders.')
        rows = self.api(source, '/releases?per_page=50&page=1')
        if not isinstance(rows, list) or len(rows) > 50:
            raise ValueError('GitHub returned an invalid release list.')
        packages = []
        for entry in declaration['addons'] if declaration else [None]:
            releases = self.releases(rows, branch, entry)
            candidates = [row for row in releases if allowed_release(row, channel)]
            preview = candidates[0] if candidates else next((row for row in releases if row['kind'] == 'release'), releases[-1])
            resolved, manifest = self.inspect(source, preview, branch_commit if preview['kind'] == 'development' else None)
            releases[releases.index(preview)] = resolved
            package = {key: manifest[key] for key in ('id', 'name', 'description', 'author', 'category')}
            package.update(releases=releases, collection=bool(declaration), package_path=entry['path'] if entry else '')
            packages.append(package)
        return {'schema_version': 1, 'layout': 'collection' if declaration else 'single',
                'name': declaration['name'] if declaration else manifest['name'],
                'publisher': declaration['publisher'] if declaration else manifest['author'], 'packages': packages}, branch

    def archive_url(self, source, commit):
        if not COMMIT.fullmatch(commit):
            raise ValueError('A pinned source commit is required.')
        return 'https://codeload.github.com/%s/%s/zip/%s' % (source['owner'], source['repository'], commit)

    def artifact(self, source, reviewed, staging):
        raw = self._get(self.archive_url(source, reviewed['commit']), MAX_ARCHIVE_BYTES)
        destination = Path(staging) / 'source-package'
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                if not entries or len(entries) > 20000:
                    raise PackageError('GitHub source archive has too many entries or is empty.')
                roots = {entry.filename.split('/')[0] for entry in entries}
                if len(roots) != 1:
                    raise PackageError('GitHub source archive must have one top-level directory.')
                prefix = logical_path(roots.pop()) + '/'
                def members(wanted):
                    found = {}
                    folded = {name.casefold() for name in wanted}
                    if len(folded) != len(wanted):
                        raise PackageError('Declared GitHub source paths have Windows case collisions.')
                    for entry in entries:
                        relative = entry.filename[len(prefix):]
                        if relative.casefold() not in folded:
                            continue
                        if entry.orig_filename != entry.filename or relative not in wanted or relative in found:
                            raise PackageError('Ambiguous or case-colliding declared GitHub source file.')
                        found[relative] = entry
                    if set(found) != set(wanted):
                        raise PackageError('GitHub source snapshot is missing a declared package file.')
                    return found
                def read(entry, limit):
                    kind = stat.S_IFMT(entry.external_attr >> 16)
                    if (entry.is_dir() or kind not in (0, stat.S_IFREG) or entry.flag_bits & 1
                            or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) or entry.file_size > limit):
                        raise PackageError('A declared GitHub file is linked, encrypted, unsupported or too large.')
                    with archive.open(entry) as stream:
                        content = stream.read(limit + 1)
                    if len(content) > limit or len(content) != entry.file_size:
                        raise PackageError('Invalid GitHub source member size.')
                    return content
                path = reviewed.get('package_path') or ''
                package_prefix = logical_path(path) + '/' if path else ''
                if reviewed.get('collection'):
                    declaration = validate_collection(parse_json(read(members({'addons.json'})['addons.json'], COLLECTION_LIMIT)))
                    if (manifest_digest(declaration) != reviewed.get('collection_digest') or
                            not any(row['id'] == reviewed['addon_id'] and row['path'] == path for row in declaration['addons'])):
                        raise PackageError('Collection declaration differs from the reviewed package path or membership.')
                manifest_name = logical_path(package_prefix + 'addon.json')
                manifest = validate_manifest(parse_json(read(members({manifest_name})[manifest_name], 256 * 1024)))
                if manifest_digest(manifest) != reviewed['manifest_digest'] or manifest['id'] != reviewed['addon_id'] or manifest['version'] != reviewed['version']:
                    raise PackageError('GitHub source manifest differs from the reviewed commit/package.')
                selected = members({logical_path(package_prefix + 'payload/' + item['source']) for item in manifest['files']})
                if sum(item.file_size for item in selected.values()) > MAX_PACKAGE_BYTES:
                    raise PackageError('Declared GitHub payload exceeds 64 MiB.')
                destination.mkdir()
                (destination / 'addon.json').write_text(json.dumps(manifest), 'utf-8')
                for name, entry in selected.items():
                    target = confined_file(destination, name[len(package_prefix):])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(read(entry, MAX_FILE_BYTES))
            output = Path(staging) / 'normalized.m2addon.zip'
            build_artifact(destination, output)  # Reuses payload/hash/namespace validation; never imports code.
            return output.read_bytes()
        except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
            raise PackageError('Invalid GitHub source archive: %s' % exc) from exc
