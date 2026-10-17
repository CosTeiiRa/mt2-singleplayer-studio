import unittest
from tools.build_release import release_path


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
        for path in ('server.py','VERSION','README.md','Install Studio.bat','web/app.js','tests/test_installation.py','docs/USER_GUIDE.md'):
            with self.subTest(path=path):
                self.assertTrue(release_path(path))
