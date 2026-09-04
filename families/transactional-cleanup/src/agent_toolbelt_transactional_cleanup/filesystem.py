from __future__ import annotations

from contextlib import contextmanager, ExitStack
import ctypes
from ctypes import wintypes
from functools import lru_cache
import os
from pathlib import Path
import stat


def canonical(value: str | Path) -> Path:
    text = os.fspath(value)
    if not text or any(c in text for c in ('*', '?', '\x00')):
        raise ValueError('Literal local path required')
    path = Path(os.path.abspath(os.path.expanduser(text)))
    if os.name == 'nt' and (str(path).startswith('\\\\') or ':' in str(path)[2:]):
        raise ValueError('UNC, device paths and alternate streams are unsupported')
    return path


def within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([path, root]).casefold() == str(root).casefold()
    except ValueError:
        return False


def reparse(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def check_chain(path: Path) -> None:
    for part in (*reversed(path.parents), path):
        try:
            if reparse(part):
                raise ValueError(f'Reparse point protected: {part}')
        except FileNotFoundError:
            continue


if os.name == 'nt':
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)

    class FileInfo(ctypes.Structure):
        _fields_ = [('attributes', wintypes.DWORD), ('created', wintypes.FILETIME),
                    ('accessed', wintypes.FILETIME), ('written', wintypes.FILETIME),
                    ('volume', wintypes.DWORD), ('size_high', wintypes.DWORD),
                    ('size_low', wintypes.DWORD), ('links', wintypes.DWORD),
                    ('index_high', wintypes.DWORD), ('index_low', wintypes.DWORD)]

    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInfo)]
    kernel.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL


@contextmanager
def handle(path: Path, *, delete: bool = False, ancestor: bool = False):
    if os.name != 'nt':
        raise RuntimeError('Windows handle deletion is required')
    # READ_DATA/LIST_DIRECTORY participates in sharing checks; attribute-only handles do not.
    access = 0x81 | (0x10000 if delete else 0)
    share = 1 if delete else (3 if ancestor else 7)
    opened = kernel.CreateFileW(str(path), access, share, None, 3, 0x02200000, None)
    if opened == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield opened
    finally:
        kernel.CloseHandle(opened)


def from_handle(opened) -> dict:
    info = FileInfo()
    if not kernel.GetFileInformationByHandle(opened, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {
        'identity': f'{info.volume}:{info.index_high}:{info.index_low}:{info.created.dwHighDateTime}:{info.created.dwLowDateTime}',
        'size': (info.size_high << 32) | info.size_low,
        'mtime': (info.written.dwHighDateTime << 32) | info.written.dwLowDateTime,
        'links': info.links, 'directory': bool(info.attributes & 0x10),
        'reparse': bool(info.attributes & 0x400), 'volume': info.volume,
    }


def identity(path: Path) -> dict:
    check_chain(path)
    if os.name == 'nt':
        with handle(path) as opened:
            info = from_handle(opened)
            info['filesystem'] = filesystem_type(path.anchor)
            return info
    info = path.lstat()
    return {'identity': f'{info.st_dev}:{info.st_ino}:{info.st_ctime_ns}',
            'size': info.st_size, 'mtime': info.st_mtime_ns, 'links': info.st_nlink,
            'directory': stat.S_ISDIR(info.st_mode), 'reparse': reparse(path),
            'volume': info.st_dev, 'filesystem': 'unsupported_read_only'}


@lru_cache(maxsize=32)
def filesystem_type(anchor):
    buffer = ctypes.create_unicode_buffer(64)
    get_volume = kernel.GetVolumeInformationW
    get_volume.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
                          ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                          wintypes.LPWSTR, wintypes.DWORD]
    get_volume.restype = wintypes.BOOL
    if not get_volume(anchor, None, 0, None, None, None, buffer, len(buffer)):
        return 'unknown'
    return buffer.value


def delete_exact(entry: dict, *, dry_run: bool = False) -> tuple[str, int]:
    """Keep ancestors immovable and dispose the checked object through its open handle."""
    path = canonical(entry['path'])
    if entry.get('filesystem') not in {'NTFS', 'ReFS'}:
        return 'protected', 0
    try:
        with ExitStack() as stack:
            for parent in reversed(path.parents):
                opened = stack.enter_context(handle(parent, ancestor=True))
                if from_handle(opened)['reparse']:
                    return 'protected', 0
            opened = stack.enter_context(handle(path, delete=True))
            current = from_handle(opened)
            if current['reparse'] or (not current['directory'] and current['links'] != 1):
                return 'protected', 0
            if current['identity'] != entry['identity'] or current['directory'] != entry['directory']:
                return 'replaced_after_scan', 0
            if current['directory'] and any(path.iterdir()):
                return 'not_empty', 0
            if dry_run:
                return 'eligible', 0
            # FILE_DISPOSITION_INFO uses a one-byte BOOLEAN. It refuses nonempty directories.
            disposition = ctypes.c_ubyte(1)
            if not kernel.SetFileInformationByHandle(opened, 4, ctypes.byref(disposition), 1):
                raise ctypes.WinError(ctypes.get_last_error())
            return 'deleted', 0 if current['directory'] else current['size']
    except FileNotFoundError:
        return 'already_missing', 0
    except OSError as exc:
        if getattr(exc, 'winerror', None) in (2, 3):
            return 'already_missing', 0
        if getattr(exc, 'winerror', None) in (5, 32, 33):
            return 'locked', 0
        if getattr(exc, 'winerror', None) == 145:
            return 'not_empty', 0
        return 'failed', 0
