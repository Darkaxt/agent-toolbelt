"""FIFO registration plus native event/process-exit waiting, without a broker."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import sys
import uuid

from .gate import NamedMutex

QUEUE_NAME = r"Local\Darka.AndroidGradleBuildQueue"
INFINITE = 0xFFFFFFFF


class NativeWait:
    def __init__(self):
        if os.name != "nt":
            raise OSError("Gradle execution tickets require Windows")
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "GetProcessTimes": ([wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4, wintypes.BOOL),
            "ProcessIdToSessionId": ([wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            "CreateEventW": ([ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetEvent": ([wintypes.HANDLE], wintypes.BOOL),
            "ResetEvent": ([wintypes.HANDLE], wintypes.BOOL),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            "WaitForMultipleObjects": ([wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE), wintypes.BOOL, wintypes.DWORD], wintypes.DWORD),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.k, name)
            function.argtypes, function.restype = args, result

    def process(self, pid, created_ticks=None):
        handle = self.k.OpenProcess(0x100000 | 0x1000, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:  # PID no longer exists. Access denied is NOT death.
                return None, None
            raise ctypes.WinError(error)
        try:
            result = self.k.WaitForSingleObject(handle, 0)
            if result == 0:
                self.k.CloseHandle(handle)
                return None, None
            if result != 258:
                raise ctypes.WinError(ctypes.get_last_error())
            times = [wintypes.FILETIME() for _ in range(4)]
            if not self.k.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                raise ctypes.WinError(ctypes.get_last_error())
            ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            if created_ticks is not None and ticks != created_ticks:
                self.k.CloseHandle(handle)
                return None, None
            return handle, ticks
        except BaseException:
            self.k.CloseHandle(handle)
            raise

    def event(self, name):
        handle = self.k.CreateEventW(None, True, False, name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def signal(self, handle):
        if not self.k.SetEvent(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def wait(self, event, process):
        handles = (wintypes.HANDLE * 2)(event, process)
        result = self.k.WaitForMultipleObjects(2, handles, False, INFINITE)
        if result not in (0, 1):
            raise ctypes.WinError(ctypes.get_last_error())


def default_root(native=None):
    native = native or NativeWait()
    session = wintypes.DWORD()
    if not native.k.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
        raise ctypes.WinError(ctypes.get_last_error())
    return Path(os.environ["LOCALAPPDATA"]) / "Tools/gradle-build-gate/queue" / f"session-{session.value}"


def read_state(root):
    path = root / "queue.json"
    if not path.exists():
        return {"schema": 1, "next_number": 1, "tickets": []}
    state = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(state, dict) or state.get("schema") != 1 or
            type(state.get("next_number")) is not int or state["next_number"] < 1 or
            not isinstance(state.get("tickets"), list)):
        raise ValueError("Invalid execution queue; refusing to reset or grant a turn")
    ids, numbers = set(), []
    for ticket in state["tickets"]:
        if (not isinstance(ticket, dict) or not isinstance(ticket.get("id"), str) or
                not re.fullmatch(r"[0-9a-f]{32}", ticket["id"]) or
                any(type(ticket.get(key)) is not int or ticket[key] < 1 for key in ("number", "pid", "created_ticks"))):
            raise ValueError("Invalid execution ticket")
        ids.add(ticket["id"])
        numbers.append(ticket["number"])
    if len(ids) != len(numbers) or numbers != sorted(set(numbers)) or (numbers and numbers[-1] >= state["next_number"]):
        raise ValueError("Invalid execution queue ordering")
    return state


def queue_status(root=None, namespace=None):
    """Diagnostic snapshot only: no tickets created, reclaimed or modified."""
    # Readers share the metadata mutex to avoid Windows file sharing preventing
    # atomic replacement. This lock does not register or reclaim any ticket.
    with NamedMutex(namespace or QUEUE_NAME):
        state = read_state(Path(root) if root is not None else default_root())
    return {"ordering": "fifo_registration", "pending": len(state["tickets"]),
            "head": state["tickets"][0] if state["tickets"] else None,
            "tickets": state["tickets"], "next_number": state["next_number"], "read_only": True}


class TicketQueue:
    def __init__(self, root=None, namespace=None):
        self.native = NativeWait()
        self.root = Path(root) if root is not None else default_root(self.native)
        self.namespace = namespace or QUEUE_NAME
        self.ticket = None
        self.event = None

    def save(self, state):
        self.root.mkdir(parents=True, exist_ok=True)
        pending = self.root / (uuid.uuid4().hex + ".pending")
        try:
            with pending.open("x", encoding="utf-8") as stream:
                json.dump(state, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, self.root / "queue.json")
        finally:
            pending.unlink(missing_ok=True)

    def prune(self, state):
        live = []
        for ticket in state["tickets"]:
            handle, _ = self.native.process(ticket["pid"], ticket["created_ticks"])
            if handle:
                self.native.k.CloseHandle(handle)
                live.append(ticket)
        changed = state["tickets"] != live
        state["tickets"] = live
        return changed

    def signal_head(self, state):
        if state["tickets"]:
            event = self.native.event(self.namespace + ".Ticket." + state["tickets"][0]["id"])
            try:
                self.native.signal(event)
            finally:
                self.native.k.CloseHandle(event)

    def signal_waiters(self, state):
        # Every waiter must re-arm the new head's exit handle, even if the old
        # owner released its ticket but keeps its supervising process alive.
        for ticket in state["tickets"]:
            self.signal_head({"tickets": [ticket]})

    def register(self):
        if self.ticket is not None:
            raise RuntimeError("Ticket already registered")
        handle, ticks = self.native.process(os.getpid())
        if not handle:
            raise RuntimeError("Cannot establish ticket owner identity")
        self.native.k.CloseHandle(handle)
        ticket = {"id": uuid.uuid4().hex, "pid": os.getpid(), "created_ticks": ticks}
        self.event = self.native.event(self.namespace + ".Ticket." + ticket["id"])
        try:
            with NamedMutex(self.namespace):
                state = read_state(self.root)
                self.prune(state)
                ticket["number"] = state["next_number"]
                state["next_number"] += 1
                state["tickets"].append(ticket)
                self.save(state)
                self.ticket = ticket
                self.signal_head(state)
            print(json.dumps({"state": "queued", "ticket": ticket["number"], "ticket_id": ticket["id"]}), file=sys.stderr, flush=True)
        except BaseException:
            if self.ticket is not None:
                self.release()
            else:
                self.native.k.CloseHandle(self.event)
                self.event = None
            raise

    def wait_turn(self):
        if self.ticket is None:
            raise RuntimeError("Register before waiting")
        while True:
            with NamedMutex(self.namespace):
                state = read_state(self.root)
                changed = self.prune(state)
                if not any(t["id"] == self.ticket["id"] for t in state["tickets"]):
                    raise RuntimeError("Own execution ticket missing; refusing to launch")
                if changed:
                    self.save(state)
                    self.signal_waiters(state)
                head = state["tickets"][0]
                if head["id"] == self.ticket["id"]:
                    return
                if not self.native.k.ResetEvent(self.event):
                    raise ctypes.WinError(ctypes.get_last_error())
                process, _ = self.native.process(head["pid"], head["created_ticks"])
            if process is None:
                continue  # Proven head exit during inspection; recheck under lock.
            try:
                self.native.wait(self.event, process)
            finally:
                self.native.k.CloseHandle(process)

    def release(self):
        try:
            if self.ticket is not None:
                with NamedMutex(self.namespace):
                    state = read_state(self.root)
                    state["tickets"] = [t for t in state["tickets"] if t["id"] != self.ticket["id"]]
                    self.prune(state)
                    self.save(state)
                    self.signal_waiters(state)
                self.ticket = None
        finally:
            if self.event:
                self.native.k.CloseHandle(self.event)
                self.event = None

    def __enter__(self):
        try:
            self.register()
            self.wait_turn()
            return self
        except BaseException:
            self.release()
            raise

    def __exit__(self, *args):
        self.release()
