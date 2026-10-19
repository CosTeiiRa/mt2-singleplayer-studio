from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from local_lock import StudioLocks


class GameLockTests(unittest.TestCase):
    def setUp(self):
        self.project = Path(__file__).resolve().parents[1]
        scratch = self.project / '.test-tmp'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.assertTrue(self.base.resolve().is_relative_to((self.project / '.test-tmp').resolve()))
        self.temp.cleanup()

    def test_same_game_is_locked_across_processes_and_separate_data_folders(self):
        root = self.base / 'game'
        source = "from local_lock import StudioLocks; import sys; lock=StudioLocks(sys.argv[1],sys.argv[2]).acquire(); print('locked',flush=True); sys.stdin.readline(); lock.close()"
        process = subprocess.Popen([sys.executable, '-c', source, str(root), str(self.base / 'first-state')], cwd=self.project, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'locked')
            with self.assertRaisesRegex(ValueError, 'already managing this game'):
                StudioLocks(root, self.base / 'second-state').acquire()
            other = StudioLocks(self.base / 'other-game', self.base / 'other-state').acquire()
            other.close()
        finally:
            process.communicate('\n', timeout=15)
        reopened = StudioLocks(root, self.base / 'second-state').acquire()
        reopened.close()

    def test_process_exit_releases_game_lock(self):
        source = "from local_lock import StudioLocks; import sys; lock=StudioLocks(sys.argv[1],sys.argv[2]).acquire()"
        subprocess.run([sys.executable, '-c', source, str(self.base / 'game'), str(self.base / 'state')], cwd=self.project, check=True, timeout=15)
        lock = StudioLocks(self.base / 'game', self.base / 'state').acquire()
        lock.close()
