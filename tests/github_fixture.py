"""Original GitHub response fixtures, shared by tests and the pack rehearsal."""
import io
import json
from pathlib import Path
from urllib.parse import unquote
import zipfile

from addonhub.hubcore.packages import sha256
from addonhub.transport import HTTPStatusError
from tools.addon import scaffold

URL = 'https://github.com/fixture-creator/atlas-addon'
API = 'https://api.github.com/repos/fixture-creator/atlas-addon'
ADDON_ID = 'fixture.github-atlas'


class GitHubFixture:
    def __init__(self, root):
        self.root = Path(root)
        self.refs, self.manifests, self.archives, self.readmes = {}, {}, {}, {}
        self.releases, self.calls, self.overrides = [], [], {}
        self.default_branch = 'main'

    def add(self, version, commit, published=True, prerelease=False, code=None, addon_id=ADDON_ID):
        package = self.root / commit
        scaffold(addon_id, 'GitHub atlas fixture', 'Fixture creator', package, version=version)
        manifest = json.loads((package / 'addon.json').read_text('utf-8'))
        if code is not None:
            (package / 'payload' / manifest['files'][0]['source']).write_bytes(code)
            manifest['files'][0]['sha256'] = sha256(code)
            (package / 'addon.json').write_text(json.dumps(manifest), 'utf-8')
        self.manifests[commit] = (package / 'addon.json').read_bytes()
        self.readmes[commit] = b'# Fixture add-on\n\nOriginal creator documentation. <script>not executed</script>\n'
        self.refs[self.default_branch] = commit
        if published:
            self.refs['v' + version] = commit
            self.releases.append({'tag_name': 'v' + version, 'draft': False, 'prerelease': prerelease, 'body': 'Original fixture release ' + version})
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as bundle:
            prefix = 'atlas-addon-' + commit + '/'
            bundle.writestr(prefix + 'addon.json', self.manifests[commit])
            bundle.writestr(prefix + 'README.md', self.readmes[commit])
            bundle.writestr(prefix + 'setup.py', b'raise RuntimeError("UNDECLARED BUILD SCRIPT MUST NOT RUN")\n')
            for row in manifest['files']:
                bundle.writestr(prefix + 'payload/' + row['source'], (package / 'payload' / row['source']).read_bytes())
        self.archives[commit] = buffer.getvalue()
        return package

    def __call__(self, url, limit):
        self.calls.append(url)
        if url in self.overrides:
            value = self.overrides[url]
            if isinstance(value, Exception):
                raise value
            return value
        if url == API:
            return json.dumps({'private': False, 'disabled': False, 'default_branch': self.default_branch}).encode()
        if url == API + '/releases?per_page=50&page=1':
            return json.dumps(self.releases).encode()
        if url.startswith(API + '/commits/'):
            ref = unquote(url.split('/commits/', 1)[1])
            if ref in self.refs:
                return json.dumps({'sha': self.refs[ref]}).encode()
        raw_prefix = 'https://raw.githubusercontent.com/fixture-creator/atlas-addon/'
        if url.startswith(raw_prefix):
            commit, name = url[len(raw_prefix):].split('/', 1)
            table = self.manifests if name == 'addon.json' else self.readmes if name == 'README.md' else {}
            if commit in table:
                return table[commit]
        archive_prefix = 'https://codeload.github.com/fixture-creator/atlas-addon/zip/'
        if url.startswith(archive_prefix):
            commit = url[len(archive_prefix):]
            if commit in self.archives:
                return self.archives[commit]
        raise HTTPStatusError(404)
