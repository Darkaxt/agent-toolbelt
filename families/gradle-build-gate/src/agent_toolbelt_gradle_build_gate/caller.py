"""Resolve only this caller's live session; never infer identity from a project."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import uuid

from .queue import NativeWait


def ancestors():
    if os.name != 'nt':
        return []
    class ProcessEntry(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD),
                    ('pid', wintypes.DWORD), ('heap', ctypes.c_size_t),
                    ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                    ('parent', wintypes.DWORD), ('priority', wintypes.LONG),
                    ('flags', wintypes.DWORD), ('exe', wintypes.WCHAR * 260)]
    native = NativeWait()
    k = native.k
    k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        getattr(k, name).argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        getattr(k, name).restype = wintypes.BOOL
    snapshot = k.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    parents = {}
    try:
        row = ProcessEntry()
        row.size = ctypes.sizeof(row)
        found = k.Process32FirstW(snapshot, ctypes.byref(row))
        while found:
            parents[row.pid] = row.parent
            found = k.Process32NextW(snapshot, ctypes.byref(row))
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        k.CloseHandle(snapshot)
    result, seen, pid, child_ticks = [], set(), os.getpid(), None
    while pid and pid not in seen:
        seen.add(pid)
        try:
            handle, ticks = native.process(pid)
        except OSError:
            break  # Retain verified lower ancestry when a host parent is inaccessible.
        if handle is None:
            break
        k.CloseHandle(handle)
        if child_ticks is not None and ticks > child_ticks:
            break  # A parent PID was reused after the child's creation.
        result.append((pid, ticks))
        child_ticks, pid = ticks, parents.get(pid)
    return result


def resolve(thread_name=None, *, root=None):
    explicit = thread_name.strip() if thread_name and thread_name.strip() else None
    identity = {'system': 'unknown', 'session_id': None, 'thread_name': explicit,
                'name_source': 'explicit' if explicit else 'unavailable'}
    registrations = Path(root) if root else Path(os.environ.get(
        'CLAUDE_CONFIG_DIR', str(Path.home() / '.claude'))) / 'sessions'
    try:
        for pid, ticks in ancestors():
            try:
                record = json.loads((registrations / f'{pid}.json').read_text(encoding='utf-8'))
                if record.get('pid') != pid or str(record.get('procStart')) != str(ticks):
                    continue
                session = str(uuid.UUID(record['sessionId']))
                name = record.get('name')
                name = name.strip() if isinstance(name, str) and name.strip() else None
                return {'system': 'claude', 'session_id': session, 'thread_name': explicit or name,
                        'name_source': 'explicit' if explicit else 'live_registration' if name else 'unavailable',
                        'pid': pid, 'created_ticks': ticks}
            except (OSError, ValueError, KeyError, TypeError):
                continue
    except OSError:
        pass  # Cosmetic metadata must never prevent an authorized build.
    if os.environ.get('CODEX_THREAD_ID'):
        identity.update(system='codex', session_id=os.environ['CODEX_THREAD_ID'])
    elif os.environ.get('CLAUDE_SESSION_ID'):
        identity.update(system='claude', session_id=os.environ['CLAUDE_SESSION_ID'])
    return identity
