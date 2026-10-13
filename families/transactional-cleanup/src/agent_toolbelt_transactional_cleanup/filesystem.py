from __future__ import annotations

from contextlib import contextmanager, ExitStack
import ctypes
import hashlib
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


def check_chain(path: Path, *, allow_leaf_reparse: bool = False) -> None:
    parts = reversed(path.parents) if allow_leaf_reparse else (*reversed(path.parents), path)
    for part in parts:
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

    class FileIdInfo(ctypes.Structure):
        _fields_ = [('volume', ctypes.c_ulonglong), ('identifier', ctypes.c_ubyte * 16)]

    class FileBasicInfo(ctypes.Structure):
        _fields_ = [('created', ctypes.c_longlong), ('accessed', ctypes.c_longlong),
                    ('written', ctypes.c_longlong), ('changed', ctypes.c_longlong),
                    ('attributes', wintypes.DWORD)]

    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInfo)]
    kernel.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.ReadFile.restype = wintypes.BOOL


@contextmanager
def handle(path: Path, *, delete: bool = False, ancestor: bool = False):
    if os.name != 'nt':
        raise RuntimeError('Windows handle deletion is required')
    # READ_DATA/LIST_DIRECTORY participates in sharing checks; attribute-only handles do not.
    access = 0x81 | (0x10100 if delete else 0)
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
    file_id = FileIdInfo()
    filesystem = None
    if not kernel.GetFileInformationByHandleEx(opened, 18, ctypes.byref(file_id), ctypes.sizeof(file_id)):
        error = ctypes.get_last_error()
        if error not in (1, 50, 87) or filesystem_from_handle(opened) != 'exFAT':
            raise ctypes.WinError(error)
        filesystem = 'exFAT'
        index = (info.index_high << 32) | info.index_low
        if not index and not info.attributes & 0x10:
            raise ValueError('exFAT regular file identity is unavailable')
        identifier = f'exfat:{info.volume}:{index}:{info.created.dwHighDateTime}:{info.created.dwLowDateTime}'
        volume = info.volume
    else:
        identifier = f'{file_id.volume}:{bytes(file_id.identifier).hex()}:{info.created.dwHighDateTime}:{info.created.dwLowDateTime}'
        volume = file_id.volume
    return {
        'identity': identifier,
        'identity_kind': 'exfat_file_index_64' if filesystem else 'windows_file_id_128',
        **({'filesystem': filesystem} if filesystem else {}),
        'size': (info.size_high << 32) | info.size_low,
        'mtime': (info.written.dwHighDateTime << 32) | info.written.dwLowDateTime,
        'links': info.links, 'directory': bool(info.attributes & 0x10),
        'reparse': bool(info.attributes & 0x400), 'volume': volume,
    }


def identity(path: Path, *, allow_leaf_reparse: bool = False) -> dict:
    check_chain(path, allow_leaf_reparse=allow_leaf_reparse)
    if os.name == 'nt':
        with handle(path) as opened:
            info = from_handle(opened)
            if 'filesystem' not in info:
                info['filesystem'] = filesystem_type(path.anchor)
            return info
    info = path.lstat()
    return {'identity': f'{info.st_dev}:{info.st_ino}:{info.st_ctime_ns}',
            'size': info.st_size, 'mtime': info.st_mtime_ns, 'links': info.st_nlink,
            'directory': stat.S_ISDIR(info.st_mode), 'reparse': reparse(path),
            'volume': info.st_dev, 'filesystem': 'unsupported_read_only'}


def filesystem_from_handle(opened):
    buffer = ctypes.create_unicode_buffer(64)
    get_volume = kernel.GetVolumeInformationByHandleW
    get_volume.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD,
                          ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                          wintypes.LPWSTR, wintypes.DWORD]
    get_volume.restype = wintypes.BOOL
    if not get_volume(opened, None, 0, None, None, None, buffer, len(buffer)):
        raise ctypes.WinError(ctypes.get_last_error())
    return buffer.value


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


def hash_handle(opened):
    checksum = hashlib.sha256()
    buffer = ctypes.create_string_buffer(1024 * 1024)
    count = wintypes.DWORD()
    while True:
        if not kernel.ReadFile(opened, buffer, len(buffer), ctypes.byref(count), None):
            raise ctypes.WinError(ctypes.get_last_error())
        if not count.value:
            return checksum.hexdigest()
        checksum.update(buffer.raw[:count.value])


def content_snapshot(entry):
    with handle(canonical(entry['path']), delete=True) as opened:
        current = from_handle(opened)
        if current['identity'] != entry['identity'] or current['reparse']:
            raise ValueError('Retired file changed during review')
        if entry.get('filesystem') == 'exFAT' and (
                current['size'] != entry['size'] or current['mtime'] != entry['mtime']):
            raise ValueError('exFAT file changed during review')
        return hash_handle(opened)


def delete_exact(entry: dict, *, dry_run: bool = False) -> tuple[str, int]:
    """Keep ancestors immovable and dispose the checked object through its open handle."""
    path = canonical(entry['path'])
    if entry.get('filesystem') not in {'NTFS', 'ReFS', 'exFAT'}:
        return 'protected', 0
    exfat = entry.get('filesystem') == 'exFAT'
    if exfat and (entry.get('allow_leaf_reparse') or entry.get('allow_hardlinks')
                  or entry.get('allow_disposable_repository') or entry.get('git_marker_proof')
                  or entry.get('retired_repository_root')
                  or (not entry['directory'] and not entry.get('content_sha256'))):
        return 'protected', 0
    try:
        with ExitStack() as stack:
            for parent in reversed(path.parents):
                opened = stack.enter_context(handle(parent, ancestor=True))
                parent_info = from_handle(opened)
                if parent_info['reparse']:
                    return 'protected', 0
                if str(parent) == entry.get('retired_repository_root') and (
                        parent_info['identity'] != entry['retired_repository_identity']):
                    return 'replaced_after_scan', 0
                marker = entry.get('git_marker_proof') or {}
                for prefix in ('repository', 'git'):
                    ancestor = marker.get('repository_root' if prefix == 'repository' else 'git_directory')
                    if str(parent) == ancestor and parent_info['identity'] != marker[prefix + '_identity']:
                        return 'replaced_after_scan', 0
            opened = stack.enter_context(handle(path, delete=True))
            current = from_handle(opened)
            if exfat and current.get('filesystem', '') != 'exFAT':
                return 'protected', 0
            if current['reparse'] and not entry.get('allow_leaf_reparse'):
                return 'protected', 0
            if not current['directory'] and current['links'] != 1 and not entry.get('allow_hardlinks'):
                return 'protected', 0
            if current['identity'] != entry['identity'] or current['directory'] != entry['directory']:
                return 'replaced_after_scan', 0
            if exfat and not current['directory'] and (
                    current['size'] != entry['size'] or current['mtime'] != entry['mtime']):
                return 'modified_after_review', 0
            if entry.get('content_sha256') and hash_handle(opened) != entry['content_sha256']:
                return 'modified_after_review', 0
            # A permitted leaf reparse point is the link object itself. Never
            # enumerate it, because that would traverse its target.
            if current['directory'] and not current['reparse'] and any(path.iterdir()):
                return 'not_empty', 0
            if dry_run:
                return 'eligible', 0
            if not current['directory']:
                basic = FileBasicInfo()
                if not kernel.GetFileInformationByHandleEx(
                        opened, 0, ctypes.byref(basic), ctypes.sizeof(basic)):
                    raise ctypes.WinError(ctypes.get_last_error())
                if basic.attributes & 0x1:
                    basic.attributes &= ~0x1
                    if not kernel.SetFileInformationByHandle(
                            opened, 0, ctypes.byref(basic), ctypes.sizeof(basic)):
                        raise ctypes.WinError(ctypes.get_last_error())
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
