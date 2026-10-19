"""Original two-package GitHub collection snapshots, never runnable third-party code."""
import io
import json
from pathlib import Path
from urllib.parse import unquote
import zipfile

from metin2_studio.addons.collections import create_collection
from metin2_studio.addons.hubcore.packages import sha256
from metin2_studio.addons.transport import HTTPStatusError
from tests.github_fixture import API, URL, GitHubFixture
from tools.addon import scaffold

FIRST, SECOND = 'fixture.collection-atlas', 'fixture.collection-legend'


class CollectionFixture(GitHubFixture):
    def __init__(self, root):
        super().__init__(root)
        self.files = {}

    def snapshot(self, commit, specifications):
        root = self.root / commit
        paths = []
        content = {'README.md': b'# Original collection instructions\n'}
        for spec in specifications:
            ident, path, version = spec['id'], spec['path'], spec['version']
            package = root / path
            scaffold(ident, 'Collection ' + ident.split('.')[-1], 'Fixture creator', package, version=version)
            manifest = json.loads((package / 'addon.json').read_text('utf-8'))
            manifest['release_notes'] = spec.get('notes', 'Original notes for ' + ident + ' ' + version)
            if spec.get('requires'):
                manifest['requires'] = spec['requires']
            if 'code' in spec:
                source = package / 'payload' / manifest['files'][0]['source']
                source.write_bytes(spec['code'])
                manifest['files'][0]['sha256'] = sha256(spec['code'])
            (package / 'addon.json').write_text(json.dumps(manifest), 'utf-8')
            (package / 'README.md').write_text('# Usage for ' + ident + '\n\n<script>literal documentation</script>', 'utf-8')
            for file in package.rglob('*'):
                if file.is_file():
                    content[file.relative_to(root).as_posix()] = file.read_bytes()
            paths.append(path)
        create_collection(root, paths, 'Original fixture collection', 'Fixture creator')
        content['addons.json'] = (root / 'addons.json').read_bytes()
        content['setup.py'] = b'raise RuntimeError("COLLECTION BUILD SCRIPT MUST NEVER RUN")\n'
        self.files[commit] = content
        self.refs[self.default_branch] = commit
        self.rebuild(commit)
        return root

    def publish(self, ident, version, commit, prerelease=False):
        tag = ident + '/v' + version
        self.refs[tag] = commit
        self.releases.append({'tag_name': tag, 'draft': False, 'prerelease': prerelease,
                              'body': 'Original changelog for ' + ident + ' ' + version})

    def rebuild(self, commit):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            prefix = 'atlas-addon-' + commit + '/'
            for name, raw in self.files[commit].items():
                archive.writestr(prefix + name, raw)
        self.archives[commit] = buffer.getvalue()

    def __call__(self, url, limit):
        raw_prefix = 'https://raw.githubusercontent.com/fixture-creator/atlas-addon/'
        if url.startswith(raw_prefix) and url not in self.overrides:
            self.calls.append(url)
            commit, name = url[len(raw_prefix):].split('/', 1)
            name = unquote(name)
            if name in self.files.get(commit, {}):
                return self.files[commit][name]
            raise HTTPStatusError(404)
        return super().__call__(url, limit)


def specs(first='1.0.0', second='2.0.0', first_path='addons/atlas', first_code=None):
    rows = [{'id': FIRST, 'path': first_path, 'version': first},
            {'id': SECOND, 'path': 'addons/legend', 'version': second}]
    if first_code is not None:
        rows[0]['code'] = first_code
    return rows
