"""Cross-process locks for a game installation and its separate Studio data."""
import hashlib
import os
from pathlib import Path
import tempfile


class InstanceLock:
    def __init__(self, path):
        self.path = Path(path)
        self.stream = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('a+b')
        try:
            self.stream.seek(0)
            if not self.stream.read(1):
                self.stream.write(b'1')
                self.stream.flush()
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.close()
            raise ValueError('This Studio world data folder is already in use. Stop its existing Studio instance first.') from None
        return self

    def close(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


class GameInstanceLock:
    def __init__(self, root):
        identity = os.path.normcase(str(Path(root).resolve())).encode('utf-8')
        self.ident = hashlib.sha256(identity).hexdigest()
        self.handle = None
        self.file_lock = None

    def acquire(self):
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            kernel.CreateMutexW.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.handle = kernel.CreateMutexW(None, False, 'Local\\Metin2Studio-Game-' + self.ident)
            error = ctypes.get_last_error()
            if not self.handle:
                raise ctypes.WinError(error)
            if error == 183:  # Another handle keeps this named mutex alive.
                self.close()
                raise ValueError('Another Studio is already managing this game folder. Stop it before opening another Studio or data folder.')
        else:
            self.file_lock = InstanceLock(Path(tempfile.gettempdir()) / ('metin2-studio-%s' % os.getuid()) / (self.ident + '.lock'))
            try:
                self.file_lock.acquire()
            except ValueError:
                raise ValueError('Another Studio is already managing this game folder. Stop it before opening another Studio or data folder.') from None
        return self

    def close(self):
        if self.handle:
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(self.handle)
            self.handle = None
        if self.file_lock:
            self.file_lock.close()
            self.file_lock = None


class StudioLocks:
    def __init__(self, root, state):
        self.game = GameInstanceLock(root)
        self.state = InstanceLock(Path(state) / 'studio.instance.lock')

    def acquire(self):
        try:
            self.game.acquire()
            self.state.acquire()
        except BaseException:
            self.close()
            raise
        return self

    def close(self):
        self.state.close()
        self.game.close()
