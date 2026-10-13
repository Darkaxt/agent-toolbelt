"""Native process identities, mutexes and event-driven waits."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import os
import threading

INFINITE = 0xFFFFFFFF
PREFIX = r"Local\Darka.WindowsElevation"


class Native:
    def __init__(self):
        if os.name != "nt":
            raise OSError("Windows elevation gate requires an interactive Windows session")
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateMutexW": ([ctypes.c_void_p, w.BOOL, w.LPCWSTR], w.HANDLE),
            "ReleaseMutex": ([w.HANDLE], w.BOOL),
            "CreateEventW": ([ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR], w.HANDLE),
            "SetEvent": ([w.HANDLE], w.BOOL), "ResetEvent": ([w.HANDLE], w.BOOL),
            "CloseHandle": ([w.HANDLE], w.BOOL),
            "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
            "WaitForMultipleObjects": ([w.DWORD, ctypes.POINTER(w.HANDLE), w.BOOL, w.DWORD], w.DWORD),
            "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            "GetProcessTimes": ([w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4, w.BOOL),
            "GetProcessId": ([w.HANDLE], w.DWORD),
            "GetExitCodeProcess": ([w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
            "ProcessIdToSessionId": ([w.DWORD, ctypes.POINTER(w.DWORD)], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.k, name)
            function.argtypes, function.restype = args, result

    def close(self, handle):
        if handle:
            self.k.CloseHandle(handle)

    def event(self, name):
        handle = self.k.CreateEventW(None, True, False, name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def signal(self, handle):
        if not self.k.SetEvent(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def wait(self, *handles):
        values = (w.HANDLE * len(handles))(*handles)
        result = self.k.WaitForMultipleObjects(len(handles), values, False, INFINITE)
        if not 0 <= result < len(handles):
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    def ticks(self, handle):
        times = [w.FILETIME() for _ in range(4)]
        if not self.k.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime

    def process(self, pid, ticks=None):
        handle = self.k.OpenProcess(0x100000 | 0x1000, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:
                return None, None
            raise ctypes.WinError(error)
        try:
            state = self.k.WaitForSingleObject(handle, 0)
            if state == 0:
                self.close(handle)
                return None, None
            if state != 258:
                raise ctypes.WinError(ctypes.get_last_error())
            actual = self.ticks(handle)
            if ticks is not None and actual != ticks:
                self.close(handle)
                return None, None
            return handle, actual
        except BaseException:
            self.close(handle)
            raise

    def session(self):
        session = w.DWORD()
        if not self.k.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
            raise ctypes.WinError(ctypes.get_last_error())
        return session.value


class Mutex:
    def __init__(self, name, native=None):
        self.n = native or Native()
        self.name = name
        self.handle = self.n.k.CreateMutexW(None, False, name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def __enter__(self):
        result = self.n.k.WaitForSingleObject(self.handle, INFINITE)
        if result not in (0, 0x80):
            self.n.close(self.handle)
            raise ctypes.WinError(ctypes.get_last_error())
        self.owner = threading.get_ident()
        self.abandoned = result == 0x80
        return self

    def __exit__(self, *args):
        try:
            if self.owner != threading.get_ident():
                raise RuntimeError("Prompt mutex must be released by its owning thread")
            if not self.n.k.ReleaseMutex(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.n.close(self.handle)
