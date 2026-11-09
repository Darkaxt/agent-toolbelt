"""Own the shared recall writer connection through its actual SQLite close.

Per-thread ownership remains independent. The OS releases this byte-range lock
on process exit; waiting uses kernel completion, with no age-based takeover,
polling, retry or cancellation deadline. Read-only status does not acquire it.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import sys


@contextmanager
def _database_lock(database):
    path = Path(database).with_name(Path(database).name + ".writer.lock")
    with path.open("a+b") as stream:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            import msvcrt

            class Overlapped(ctypes.Structure):
                _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                    ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            lock = kernel.LockFileEx
            lock.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
            lock.restype = wintypes.BOOL
            unlock = kernel.UnlockFileEx
            unlock.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
            unlock.restype = wintypes.BOOL
            handle = wintypes.HANDLE(msvcrt.get_osfhandle(stream.fileno()))
            overlapped = Overlapped()
            if not lock(handle, 2, 0, 1, 0, ctypes.byref(overlapped)):
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                yield
            finally:
                if not unlock(handle, 0, 1, 0, ctypes.byref(overlapped)):
                    raise ctypes.WinError(ctypes.get_last_error())
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class OwnedCacheConnection(sqlite3.Connection):
    """SQLite may checkpoint on close, after its explicit transaction committed.

    Keep writer ownership until that cleanup actually ends, not just until an
    INSERT/COMMIT returns. See https://www.sqlite.org/wal.html#sometimes_queries_return_sqlite_busy_in_wal_mode.
    """
    def close(self):
        owner = getattr(self, "_writer_owner", None)
        try:
            super().close()
        finally:
            if owner is not None:
                self._writer_owner = None
                owner.__exit__(None, None, None)


def connect_cache_database(path, **sqlite_options):
    """Acquire before opening SQLite; callers retain the existing explicit close.

    No SQLite operation precedes ownership, so concurrent opening/recovery/close
    cannot race a collector's write. The lock is not used by read-only status.
    """
    owner = _database_lock(path)
    owner.__enter__()
    try:
        conn = sqlite3.connect(path, factory=OwnedCacheConnection, **sqlite_options)
    except BaseException:
        owner.__exit__(*sys.exc_info())
        raise
    conn._writer_owner = owner
    return conn
