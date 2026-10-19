import unittest
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
import re
from types import SimpleNamespace
from unittest.mock import Mock

from tools.build_release import build, release_path

ROOT = Path(__file__).resolve().parents[1]


class WebAssetTests(unittest.TestCase):
    def test_every_referenced_frontend_asset_is_served_with_the_correct_type(self):
        from metin2_studio.server import Handler
        html=(ROOT/'web/index.html').read_text(encoding='utf-8')
        for url in re.findall(r'(?:src|href)="(/[^\"]+)"',html):
            with self.subTest(url=url):
                handler=object.__new__(Handler)
                handler.path=url;handler.headers={};handler.studio=SimpleNamespace()
                handler.guard=lambda:None;handler.send=Mock()
                handler.do_GET()
                sent=handler.send.call_args
                self.assertEqual(sent.args[0],(ROOT/'web'/url[1:]).read_bytes())
                self.assertTrue(sent.kwargs['mime'].startswith('text/css' if url.endswith('.css') else 'application/javascript'))


class ReleaseBoundaryTests(unittest.TestCase):
    def test_private_state_credentials_and_game_dumps_are_not_release_paths(self):
        for path in ('data/worlds/id/workspace.sqlite','data/backups/id/0.before','.env','nested/.env.local','workspace.sqlite-wal','server.log','studio.pid','dist/release.zip','tests/__pycache__/cached.pyc','shortcut.lnk'):
            with self.subTest(path=path):
                self.assertFalse(release_path(path))

    def test_unsafe_archive_paths_are_rejected(self):
        for path in ('../outside.py','/absolute.py','C:/private.py','data\\private.json','bad\x00name'):
            with self.subTest(path=path):
                self.assertFalse(release_path(path))

    def test_normal_application_and_operator_files_are_packaged(self):
        for path in ('studio.py','src/metin2_studio/server.py','VERSION','README.md','Install Studio.bat','scripts/windows/Setup-Studio.ps1','web/app.js','tests/test_installation.py','docs/USER_GUIDE.md'):
            with self.subTest(path=path):
                self.assertTrue(release_path(path))


class PortableLayoutTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / '.test-tmp'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def run_cli(self, path, *arguments):
        result = subprocess.run([sys.executable, str(path), *map(str, arguments)], cwd=self.base,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_source_entry_points_work_outside_the_project_directory(self):
        self.assertIn('--root', self.run_cli(ROOT / 'studio.py', 'serve', '--help'))
        self.assertIn('--server-root', self.run_cli(ROOT / 'studio.py', 'setup', '--help'))

    def test_extracted_release_finds_the_application_and_bundled_addons(self):
        archive = build(ROOT, self.base / 'dist')
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(self.base / 'extracted')
        project = self.base / 'extracted' / archive.stem
        self.assertIn('--root', self.run_cli(project / 'studio.py', '--help'))
        self.assertIn('--server-root', self.run_cli(project / 'studio.py', 'setup', '--help'))
        packages = sorted((project / 'src/metin2_studio/addons/catalog').iterdir())
        self.assertEqual(len(packages), 4)
        output = self.run_cli(project / 'tools/validate_addon.py', *packages)
        self.assertEqual(output.count('VALID community.'), 4)
        self.assertTrue((project / 'scripts/windows/Launch-Studio.ps1').is_file())
        self.assertFalse((project / 'data').exists())
