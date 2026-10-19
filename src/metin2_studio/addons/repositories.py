"""Explicit repository subscriptions, immutable releases and reviewed downloads."""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import quote
import tempfile
import uuid

from .artifacts import MAX_ARCHIVE_BYTES, extract_artifact
from .hubcore.manager import _atomic_bytes, _atomic_json, _json
from .hubcore.packages import ID_RE, SHA_RE, PackageError, discover_packages, load_package, parse_json, sha256
from .transport import PublicHTTPSFetcher, https_url
from .versions import Version
from .github_source import GitHubSource, allowed_release, identity as github_identity, manifest_digest

INDEX_LIMIT = 2 * 1024 * 1024


def _text(value, label, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError('Invalid repository %s.' % label)
    return value


def validate_index(value):
    if not isinstance(value, dict) or value.get('schema_version') != 1 or isinstance(value.get('schema_version'), bool):
        raise ValueError('Only repository schema version 1 is supported.')
    result = {'schema_version': 1, 'name': _text(value.get('name'), 'name', 128),
              'publisher': _text(value.get('publisher'), 'publisher', 128), 'packages': []}
    packages = value.get('packages')
    if not isinstance(packages, list) or len(packages) > 200:
        raise ValueError('A repository may list at most 200 packages.')
    seen = set()
    for item in packages:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not ID_RE.fullmatch(item['id']) or item['id'] in seen:
            raise ValueError('Invalid or duplicate repository add-on id.')
        seen.add(item['id'])
        package = {'id': item['id'], 'name': _text(item.get('name'), 'package name', 256),
                   'description': _text(item.get('description'), 'description'),
                   'author': _text(item.get('author', result['publisher']), 'author', 256),
                   'category': _text(item.get('category', 'Community'), 'category', 128), 'releases': []}
        releases = item.get('releases')
        if not isinstance(releases, list) or not 0 < len(releases) <= 50:
            raise ValueError('Each repository package needs 1–50 releases.')
        versions = set()
        for row in releases:
            if not isinstance(row, dict):
                raise ValueError('Invalid repository release.')
            version = Version(row.get('version'))
            if version.text in versions:
                raise ValueError('Duplicate repository release version.')
            versions.add(version.text)
            if not isinstance(row.get('sha256'), str) or not SHA_RE.fullmatch(row['sha256']):
                raise ValueError('Each release needs a lowercase SHA-256 checksum.')
            size = row.get('bytes')
            if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_ARCHIVE_BYTES:
                raise ValueError('Each release needs its bounded archive byte size.')
            withdrawn = row.get('withdrawn', False)
            if not isinstance(withdrawn, bool):
                raise ValueError('Release withdrawal must be a boolean.')
            package['releases'].append({'version': version.text, 'url': https_url(row.get('url')),
                                        'sha256': row['sha256'], 'bytes': size, 'withdrawn': withdrawn,
                                        'reason': _text(row.get('reason') or 'Withdrawn by repository', 'withdrawal reason', 2000) if withdrawn else '',
                                        'release_notes': _text(row.get('release_notes', 'No release notes provided.'), 'release notes')})
        package['releases'].sort(key=lambda row: (Version(row['version']), row['version']), reverse=True)
        result['packages'].append(package)
    return result


class RepositoryStore:
    def __init__(self, state_dir, bundled_dir, fetcher=None):
        self.root = Path(state_dir).resolve()
        self.bundled_dir = Path(bundled_dir).resolve()
        self.path = self.root / 'repositories.json'
        self.fetch = fetcher or PublicHTTPSFetcher()
        self.pending = {}
        self._working_state = None

    def _state(self):
        if self._working_state is not None:
            return copy.deepcopy(self._working_state)
        state = _json(self.path, {'schema_version': 1, 'repositories': {}, 'active': {}, 'seen': {}})
        if state.get('schema_version') != 1 or any(not isinstance(state.get(key), dict) for key in ('repositories', 'active', 'seen')):
            raise ValueError('Repository state is invalid. Preserve the add-on data folder.')
        if not isinstance(state.setdefault('github_cache', {}), dict):
            raise ValueError('GitHub cache state is invalid. Preserve the add-on data folder.')
        return state

    def _save(self, state):
        if self._working_state is None:
            _atomic_json(self.path, state)
        else:
            self._working_state = copy.deepcopy(state)
        self.pending.clear()

    def fork(self):
        """Prepare metadata in isolation; immutable cache bytes may be shared."""
        working = RepositoryStore(self.root, self.bundled_dir, self.fetch)
        working._working_state = self._state()
        working.pending = copy.deepcopy(self.pending)
        return working

    def publish(self, working, expected):
        if self.fingerprint() != expected:
            raise ValueError('Repository state changed during this job. Prepared changes were discarded; check again.')
        _atomic_json(self.path, working._state())
        self.pending = copy.deepcopy(working.pending)

    def fingerprint(self, state=None):
        return sha256(json.dumps(self._state() if state is None else state, sort_keys=True, separators=(',', ':')).encode('utf-8'))

    def annotate(self, items):
        state = self._state()
        for item in items:
            active = state['active'].get(item['id'])
            if active:
                item['distribution'] = self._distribution(active)
        return items

    def _distribution(self, active):
        if active.get('source_kind') == 'local':
            return {'kind': 'local', 'filename': active['filename'], 'sha256': active['sha256']}
        result = {'kind': active.get('source_kind', 'repository'),
                  **{key: active[key] for key in ('repository_id', 'repository_url', 'sha256')}}
        if result['kind'] == 'github':
            result.update({key: active[key] for key in ('commit', 'source_ref', 'selection')})
            result.update(package_path=active.get('package_path', ''), collection=active.get('collection', False))
            readme = (active.get('package_path', '') + '/' if active.get('package_path') else '') + 'README.md'
            result['documentation_url'] = active.get('documentation_url') or active['repository_url'] + '/blob/' + active['commit'] + '/' + quote(readme, safe='/')
        return result

    def _github(self):
        return GitHubSource(self.fetch)

    def _github_key(self, ident, release):
        scope = release['addon_id'] + '/' if release.get('collection') else ''
        return 'github/' + ident + '/' + scope + release['version']

    def _remember_github(self, state, ident, row, release):
        key = self._github_key(ident, release)
        if release.get('collection') and state['seen'].get('github-single-id/' + ident) == release['addon_id']:
            legacy = state['seen'].get('github/' + ident + '/' + release['version'])
            if legacy:
                state['seen'].setdefault(key, legacy)
        if not release.get('collection') and release.get('addon_id'):
            previous_id = state['seen'].get('github-single-id/' + ident)
            if previous_id and previous_id != release['addon_id']:
                row['blocked'] = True
                raise ValueError('This single-add-on GitHub source changed its add-on id.')
            state['seen']['github-single-id/' + ident] = release['addon_id']
        if release.get('commit') and release['kind'] != 'development':
            if state['seen'].get(key) not in (None, release['commit']):
                row['blocked'] = True
                raise ValueError('A published GitHub version moved to another commit. Publish a new version; this source is blocked.')
            state['seen'][key] = release['commit']

    def _github_cache_key(self, ident, release):
        scope = release['addon_id'] + '/' if release.get('collection') else ''
        return ident + '/' + scope + str(release.get('commit'))

    def _github_cache(self, state, ident, release):
        return state['github_cache'].get(self._github_cache_key(ident, release), {})

    def list(self):
        state = self._state()
        return [{'id': ident, 'url': row['url'], 'enabled': row['enabled'], 'channel': row['channel'],
                 'kind': row.get('kind', 'catalog'), 'layout': row.get('index', {}).get('layout'), 'default_branch': row.get('default_branch'),
                 'name': row.get('index', {}).get('name', 'Repository awaiting check'),
                 'publisher': row.get('index', {}).get('publisher'),
                 'checked_at': row.get('checked_at'), 'error': row.get('error'), 'blocked': row.get('blocked', False),
                 'package_count': len(row.get('index', {}).get('packages', []))}
                for ident, row in sorted(state['repositories'].items())]

    def add(self, url, channel='stable'):
        url = https_url(url)
        github = github_identity(url)
        if github:
            url = github['url']
        if channel not in (('stable', 'prerelease', 'development') if github else ('stable', 'prerelease')):
            raise ValueError('Choose stable/prerelease, or development for a GitHub repository.')
        ident = sha256(url.encode('utf-8'))[:16]
        state = self._state()
        if ident in state['repositories']:
            raise ValueError('This repository is already subscribed.')
        if len(state['repositories']) >= 20:
            raise ValueError('At most 20 repositories may be subscribed.')
        state['repositories'][ident] = {'url': url, 'enabled': True, 'channel': channel, 'kind': 'github' if github else 'catalog'}
        if github:
            state['repositories'][ident]['github'] = github
        self._save(state)
        self.refresh(ident)
        return ident

    def refresh(self, ident):
        state = self._state()
        if ident not in state['repositories']:
            raise ValueError('Unknown repository.')
        row = state['repositories'][ident]
        try:
            if row.get('kind') == 'github':
                index, branch = self._github().discover(row['github'], row['channel'])
                old_index = row.get('index', {})
                old_packages = {package['id']: package for package in old_index.get('packages', [])}
                if old_index.get('layout', 'single') == 'single' and len(old_packages) == 1:
                    previous_id = next(iter(old_packages))
                    state['seen'].setdefault('github-single-id/' + ident, previous_id)
                    if index.get('layout') == 'single' and previous_id != index['packages'][0]['id']:
                        row['blocked'] = True
                        raise ValueError('This GitHub repository changed its add-on id. Add-ons must keep a stable id.')
                for package in index['packages']:
                    old_releases = {r['version']: r for r in old_packages.get(package['id'], {}).get('releases', [])}
                    for release in package['releases']:
                        self._remember_github(state, ident, row, release)
                        if not release.get('commit'):
                            old = old_releases.get(release['version'], {})
                            for key in ('commit', 'package_version', 'manifest_digest', 'readme', 'documentation_url', 'package_path', 'collection_digest'):
                                if key in old and old.get('source_ref') == release['source_ref']:
                                    release[key] = old[key]
                            if release['kind'] == 'development' and old.get('source_ref') == release['source_ref'] and old.get('release_notes'):
                                release['release_notes'] = old['release_notes']
                            if not release.get('commit') and release['kind'] != 'development':
                                release['commit'] = state['seen'].get(self._github_key(ident, release))
                row['default_branch'] = branch
                raw = json.dumps(index, sort_keys=True).encode('utf-8')
            else:
                raw = self.fetch(row['url'], INDEX_LIMIT)
                if len(raw) > INDEX_LIMIT:
                    raise ValueError('Repository index exceeds 2 MiB.')
                index = validate_index(parse_json(raw, INDEX_LIMIT))
                for package in index['packages']:
                    for release in package['releases']:
                        key = ident + '/' + package['id'] + '/' + release['version']
                        previous = state['seen'].get(key)
                        if previous and previous != release['sha256']:
                            row['blocked'] = True
                            raise ValueError('A published version changed its archive checksum. Publish a new version; this repository is blocked.')
                for package in index['packages']:
                    for release in package['releases']:
                        state['seen'][ident + '/' + package['id'] + '/' + release['version']] = release['sha256']
            row.update(index=index, index_sha256=sha256(raw), checked_at=datetime.now(timezone.utc).isoformat(), error=None, blocked=False)
        except (ValueError, OSError, UnicodeError) as exc:
            row['error'] = str(exc)
            self._save(state)
            raise ValueError('Repository check failed: %s' % exc) from exc
        self._save(state)

    def configure(self, ident, enabled=None, channel=None, remove=False):
        state = self._state()
        if ident not in state['repositories']:
            raise ValueError('Unknown repository.')
        if remove:
            del state['repositories'][ident]
        else:
            if enabled is not None:
                if not isinstance(enabled, bool):
                    raise ValueError('Repository enabled state must be a boolean.')
                state['repositories'][ident]['enabled'] = enabled
            if channel is not None:
                if channel not in (('stable', 'prerelease', 'development') if state['repositories'][ident].get('kind') == 'github' else ('stable', 'prerelease')):
                    raise ValueError('Development snapshots require a GitHub repository.')
                state['repositories'][ident]['channel'] = channel
        self._save(state)

    def _release(self, state, repo_id, addon_id, version):
        repo = state['repositories'].get(repo_id)
        if not repo or not repo['enabled'] or repo.get('blocked'):
            raise ValueError('Enable and successfully check this repository before downloading.')
        for package in repo.get('index', {}).get('packages', []):
            if package['id'] == addon_id:
                for release in package['releases']:
                    if release['version'] == version:
                        if repo.get('kind') == 'github' and not allowed_release(release, repo['channel']):
                            raise ValueError('Choose the release channel that includes this GitHub version before reviewing it.')
                        if release['withdrawn']:
                            raise ValueError('This release was withdrawn: ' + release['reason'])
                        cache_hash = self._github_cache(state, repo_id, release).get('sha256') if repo.get('kind') == 'github' else release['sha256']
                        if repo.get('error') and not (cache_hash and (self.root / 'artifacts' / (cache_hash + '.zip')).is_file()):
                            raise ValueError('Repository check failed; only already-cached releases can be selected offline.')
                        return repo, package, release
        raise ValueError('This repository no longer lists the requested release.')

    def _available(self, state, active):
        if active.get('source_kind') == 'local':
            return True
        repo = state['repositories'].get(active['repository_id'])
        if not repo or not repo['enabled'] or repo.get('blocked'):
            return False
        if active.get('source_kind') == 'github':
            return any(package['id'] == active['id'] and any(release['version'] == active['selection'] and not release['withdrawn']
                       for release in package['releases']) for package in repo.get('index', {}).get('packages', []))
        return any(package['id'] == active['id'] and any(release['version'] == active['version'] and
                   release['sha256'] == active['sha256'] and not release['withdrawn'] for release in package['releases'])
                   for package in repo.get('index', {}).get('packages', []))

    def policy_check(self, addon_id, action):
        active = self._state()['active'].get(addon_id)
        if action in ('install', 'update', 'enable') and active and not self._available(self._state(), active):
            raise ValueError('The selected release source is disabled, missing, blocked or withdrawn. Removal and disabling remain available.')

    def packages(self):
        state = self._state()
        packages, errors = discover_packages(self.bundled_dir)
        for addon_id, active in state['active'].items():
            if addon_id in packages:
                errors.append({'id': addon_id, 'status': 'invalid', 'error': 'A remote release cannot replace a bundled add-on.'})
                continue
            if not self._available(state, active):
                continue
            try:
                if not SHA_RE.fullmatch(active['sha256']):
                    raise PackageError('Invalid cached release identity.')
                path = self.root / 'releases' / active['sha256']
                if path.is_symlink() or not path.resolve().is_relative_to(self.root):
                    raise PackageError('Cached release escaped its state directory.')
                package = load_package(path)
                if package.digest != active['package_digest'] or package.manifest['id'] != addon_id or package.manifest['version'] != active['version']:
                    raise PackageError('Cached release changed after verification.')
                packages[addon_id] = replace(package, distribution=self._distribution(active))
            except (ValueError, OSError) as exc:
                errors.append({'id': addon_id, 'name': addon_id, 'status': 'invalid', 'error': str(exc)})
        return packages, errors

    def offers(self, installed=()):
        state = self._state()
        bundled, errors = discover_packages(self.bundled_dir)
        installed = {row['id']: row for row in installed}
        occurrences = {}
        for repo_id, repo in state['repositories'].items():
            if repo['enabled']:
                for package in repo.get('index', {}).get('packages', []):
                    occurrences.setdefault(package['id'], []).append(repo_id)
        result = []
        for repo_id, repo in state['repositories'].items():
            if not repo['enabled']:
                continue
            for package in repo.get('index', {}).get('packages', []):
                releases = [copy.deepcopy(release) for release in package['releases']
                            if (allowed_release(release, repo['channel']) if repo.get('kind') == 'github'
                                else repo['channel'] == 'prerelease' or not Version(release['version']).pre)]
                for release in releases:
                    cache_hash = self._github_cache(state, repo_id, release).get('sha256') if repo.get('kind') == 'github' else release['sha256']
                    release['cached'] = bool(cache_hash and (self.root / 'artifacts' / (cache_hash + '.zip')).is_file())
                latest = next((release for release in releases if not release['withdrawn']), None)
                active = state['active'].get(package['id'])
                current = installed.get(package['id'])
                conflict = package['id'] in bundled or len(occurrences[package['id']]) > 1
                source = (current.get('distribution') or {}) if current else {}
                same_source = bool(source.get('repository_id') == repo_id)
                if current and not source and active and active['package_digest'] == current.get('package_digest'):
                    same_source = active.get('repository_id') == repo_id
                update = False
                if latest and current and same_source and not conflict and not repo.get('blocked'):
                    if latest.get('kind') == 'development':
                        update = (latest['manifest_digest'] != current.get('package_digest') if latest.get('manifest_digest')
                                  else bool(latest.get('commit') and latest['commit'] != current.get('distribution', {}).get('commit')))
                    else:
                        try:
                            update = Version(latest['version']) > Version(current['version'])
                        except ValueError:
                            pass
                result.append({**package, 'releases': releases, 'latest': latest, 'repository_id': repo_id,
                               'source_kind': repo.get('kind', 'catalog'), 'default_branch': repo.get('default_branch'),
                               'repository_name': repo['index']['name'], 'repository_url': repo['url'],
                               'checked_at': repo.get('checked_at'), 'channel': repo['channel'],
                               'publisher': repo['index']['publisher'],
                               'error': 'Add-on id is offered by competing sources or reserved for a bundled example.' if conflict else repo.get('error'),
                               'blocked': conflict or repo.get('blocked', False), 'update_available': update,
                               'selected_version': active.get('selection', active['version']) if active else None,
                               'installed_version': current['version'] if current else None})
        return result

    def review(self, repo_id, addon_id, version):
        state = self._state()
        repo, package, release = self._release(state, repo_id, addon_id, version)
        offer = next(row for row in self.offers() if row['repository_id'] == repo_id and row['id'] == addon_id)
        if offer['blocked']:
            raise ValueError(offer['error'] or 'This release source is blocked.')
        if repo.get('kind') == 'github':
            return self._review_github(state, repo_id, repo, package, release)
        active = state['active'].get(addon_id)
        public = {**copy.deepcopy(release), 'id': uuid.uuid4().hex, 'addon_id': addon_id, 'name': package['name'],
                  'repository_id': repo_id, 'repository_url': repo['url'], 'publisher': repo['index']['publisher'],
                  'source_changed': bool(active and active.get('repository_id') != repo_id),
                  'previous_source': (active.get('repository_url') or 'Local file: ' + active.get('filename', 'archive')) if active else None,
                  'notice': 'Choose sources you trust. Downloading checks archive integrity and does not install or run the add-on.'}
        self.pending[public['id']] = {'public': public, 'index_sha256': repo['index_sha256'], 'fingerprint': self.fingerprint(state)}
        return copy.deepcopy(public)

    def _review_github(self, state, repo_id, repo, package, release):
        if not repo.get('error'):
            try:
                resolved, manifest = self._github().inspect(repo['github'], release)
                if manifest['id'] != package['id']:
                    repo['blocked'] = True
                    raise ValueError('This GitHub version declares another add-on id.')
                self._remember_github(state, repo_id, repo, resolved)
            except (ValueError, OSError) as exc:
                repo['error'] = str(exc)
                self._save(state)
                raise
            release.update(resolved)
            self._save(state)
        else:
            cache = self._github_cache(state, repo_id, release)
            if not cache:
                raise ValueError('Check this GitHub repository successfully before selecting an uncached source snapshot.')
            cached_package = load_package(self.root / 'releases' / cache['sha256'])
            if cached_package.digest != cache['package_digest']:
                raise ValueError('Cached GitHub package changed after verification.')
            manifest = cached_package.manifest
            release = {**release, 'package_path': cache.get('package_path', ''), 'collection_digest': cache.get('collection_digest'),
                       'documentation_url': cache.get('documentation_url', release.get('documentation_url'))}
        cache = self._github_cache(state, repo_id, release)
        active = state['active'].get(package['id'])
        public = {'id': uuid.uuid4().hex, 'source_kind': 'github', 'addon_id': package['id'], 'name': manifest['name'],
            'version': manifest['version'], 'selection': release['version'], 'commit': release['commit'],
            'collection': release.get('collection', False), 'package_path': release.get('package_path', ''),
            'collection_digest': release.get('collection_digest'),
            'source_ref': release['source_ref'], 'kind': release['kind'], 'manifest_digest': manifest_digest(manifest),
            'repository_id': repo_id, 'repository_url': repo['url'], 'publisher': manifest['author'],
            'sha256': cache.get('sha256'), 'bytes': cache.get('bytes'),
            'url': self._github().archive_url(repo['github'], release['commit']),
            'readme': release.get('readme', ''), 'documentation_url': release.get('documentation_url'),
            'release_notes': release['release_notes'], 'source_changed': bool(active and active.get('repository_id') != repo_id),
            'previous_source': (active.get('repository_url') or 'Local file: ' + active.get('filename', 'archive')) if active else None,
            'notice': 'Choose sources you trust. This stages the declared files from the pinned commit; installation is reviewed separately.'}
        self.pending[public['id']] = {'public': public, 'index_sha256': repo['index_sha256'], 'fingerprint': self.fingerprint(state)}
        return copy.deepcopy(public)

    def download(self, review_id, accept_source_change=False):
        reviewed = self.pending.get(review_id)
        if not reviewed:
            raise ValueError('Download review expired. Review the release again.')
        public = reviewed['public']
        if public['source_changed'] and accept_source_change is not True:
            raise ValueError('Explicitly accept the repository source change before downloading.')
        state = self._state()
        if reviewed['fingerprint'] != self.fingerprint(state):
            raise ValueError('Repository state changed after review. Review again.')
        repo, package, release = self._release(state, public['repository_id'], public['addon_id'], public.get('selection', public['version']))
        if repo['index_sha256'] != reviewed['index_sha256']:
            raise ValueError('Repository changed after review. Review again.')
        if public.get('source_kind') == 'github':
            return self._download_github(state, repo, public)
        artifact = self.root / 'artifacts' / (release['sha256'] + '.zip')
        raw = artifact.read_bytes() if artifact.is_file() else self.fetch(release['url'], release['bytes'])
        if len(raw) != release['bytes'] or sha256(raw) != release['sha256']:
            raise ValueError('Downloaded release size or SHA-256 does not match the reviewed catalog.')
        verified, archive_hash = self._cache_artifact(raw, public['addon_id'], public['version'])
        state['active'][public['addon_id']] = {'id': public['addon_id'], 'version': public['version'],
            'source_kind': 'repository', 'repository_id': public['repository_id'], 'repository_url': repo['url'],
            'sha256': archive_hash, 'package_digest': verified.digest}
        self._save(state)
        return {'downloaded': public['addon_id'], 'version': public['version'], 'sha256': archive_hash,
                'message': 'Release verified and added to the local catalog. Review a separate installation plan to use it.'}

    def _download_github(self, state, repo, public):
        key = self._github_cache_key(public['repository_id'], public)
        cache = state['github_cache'].get(key)
        if cache:
            if cache.get('package_path', '') != public.get('package_path', '') or cache.get('collection_digest') != public.get('collection_digest'):
                raise ValueError('Cached GitHub source identity differs from the reviewed package path or collection.')
            raw = (self.root / 'artifacts' / (cache['sha256'] + '.zip')).read_bytes()
            if sha256(raw) != cache['sha256'] or len(raw) != cache['bytes']:
                raise ValueError('Cached GitHub archive changed after verification.')
        else:
            staging = self.root / '.staging'
            staging.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=staging, prefix='github-') as temporary:
                raw = self._github().artifact(repo['github'], public, temporary)
        verified, archive_hash = self._cache_artifact(raw, public['addon_id'], public['version'])
        if verified.digest != public['manifest_digest']:
            raise ValueError('GitHub package differs from the reviewed source manifest.')
        state['github_cache'][key] = {'sha256': archive_hash, 'bytes': len(raw), 'package_digest': verified.digest,
                                    'package_path': public.get('package_path', ''), 'collection_digest': public.get('collection_digest'),
                                    'documentation_url': public.get('documentation_url')}
        state['active'][public['addon_id']] = {'id': public['addon_id'], 'version': public['version'], 'source_kind': 'github',
            'repository_id': public['repository_id'], 'repository_url': repo['url'], 'commit': public['commit'],
            'source_ref': public['source_ref'], 'selection': public['selection'],
            'package_path': public.get('package_path', ''), 'collection': public.get('collection', False),
            'documentation_url': public.get('documentation_url'), 'sha256': archive_hash, 'package_digest': verified.digest}
        self._save(state)
        return {'downloaded': public['addon_id'], 'version': public['version'], 'commit': public['commit'], 'sha256': archive_hash,
                'message': 'GitHub source validated and staged. Review a separate installation/update plan to use it.'}

    def _cache_artifact(self, raw, addon_id=None, version=None):
        archive_hash = sha256(raw)
        artifact = self.root / 'artifacts' / (archive_hash + '.zip')
        if artifact.exists() and sha256(artifact.read_bytes()) != archive_hash:
            raise ValueError('Cached archive has unexpected changes. Preserve it for investigation.')
        staging = self.root / '.staging'
        staging.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=staging, prefix='download-') as temporary:
            extracted = Path(temporary) / 'release'
            verified = extract_artifact(raw, extracted)
            if addon_id is not None and (verified.manifest['id'] != addon_id or verified.manifest['version'] != version):
                raise ValueError('Downloaded manifest identity differs from the reviewed release.')
            if verified.manifest['id'] in discover_packages(self.bundled_dir)[0]:
                raise ValueError('Imported or downloaded packages cannot replace a bundled add-on id.')
            destination = self.root / 'releases' / archive_hash
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                existing = load_package(destination)
                if existing.digest != verified.digest:
                    raise ValueError('Cached release has unexpected changes. Preserve it for investigation.')
            else:
                if not extracted.resolve().is_relative_to(staging.resolve()) or destination.resolve().parent != (self.root / 'releases').resolve():
                    raise ValueError('Invalid owned release staging path.')
                extracted.rename(destination)
            if not artifact.exists():
                _atomic_bytes(artifact, raw)
        return verified, archive_hash

    def import_archive(self, raw, filename):
        if (not isinstance(filename, str) or not 0 < len(filename) <= 160 or filename.strip() != filename
                or any(ord(c) < 32 or c in '/\\:<>"|?*' for c in filename) or not filename.lower().endswith('.zip')):
            raise ValueError('Choose a ZIP filename without paths or special characters.')
        if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_ARCHIVE_BYTES:
            raise ValueError('Choose a nonempty add-on ZIP no larger than 66 MiB.')
        state = self._state()
        verified, archive_hash = self._cache_artifact(raw)
        addon_id, version = verified.manifest['id'], verified.manifest['version']
        previous = state['active'].get(addon_id)
        state['active'][addon_id] = {'id': addon_id, 'version': version, 'source_kind': 'local',
                                   'filename': filename, 'sha256': archive_hash, 'package_digest': verified.digest}
        self._save(state)
        return {'imported': addon_id, 'version': version, 'filename': filename, 'sha256': archive_hash,
                'same_version_changed': bool(previous and previous['version'] == version and previous['sha256'] != archive_hash),
                'message': 'Package added to the local catalog. Review a separate installation plan to use it.'}

    def forget_import(self, addon_id):
        state = self._state()
        if state['active'].get(addon_id, {}).get('source_kind') != 'local':
            raise ValueError('Choose an imported local package to remove from the catalog.')
        del state['active'][addon_id]
        self._save(state)
        return {'forgotten': addon_id, 'message': 'Removed from the catalog. Installed code, cached bytes and recovery data were retained.'}
