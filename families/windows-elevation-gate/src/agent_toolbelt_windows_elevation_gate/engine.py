"""Explain -> native UAC -> supervised exact command; feedback is never code."""
from __future__ import annotations

from collections import deque
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from .dialog import explain
from .native import Native, Mutex
from .queue import Queue, atomic_json

OUTPUT_LIMIT = 64000


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare(command, *, cwd, task, thread_name, reason, changes, targets, bind_files=()):
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("An exact executable and argument array are required after --")
    executable = Path(command[0]).expanduser()
    if not executable.is_absolute() or not executable.is_file() or executable.suffix.lower() != ".exe":
        raise ValueError("Use an absolute existing .exe path, not a shell alias, .cmd or .bat")
    directory = Path(cwd).expanduser().resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("Working directory must be a directory")
    labels = {"task": task, "thread_name": thread_name, "reason": reason, "changes": changes}
    if any(not str(value).strip() or len(str(value)) > 2000 for value in labels.values()):
        raise ValueError("Task, actual thread name, reason and expected changes must be nonempty and bounded")
    if not targets or any(not str(target).strip() for target in targets):
        raise ValueError("At least one explicit target is required")
    command = [str(executable.resolve()), *map(str, command[1:])]
    if len(subprocess.list2cmdline(command)) > 16000:
        raise ValueError("Command is too large; use an explicitly bound script file")
    host = Path(sys.executable).resolve()
    bindings = {str(executable.resolve()): sha256(executable), str(host): sha256(host)}
    # Explicit script flags must be hash-bound too; arbitrary runtime dependencies
    # still require caller provenance and are not a security sandbox.
    inputs = list(bind_files)
    for index, value in enumerate(command[1:], 1):
        if value.lower() in ("-file", "-f", "--file") and index + 1 < len(command):
            inputs.append(command[index + 1])
        elif value.lower().endswith((".ps1", ".py", ".cmd", ".bat")):
            inputs.append(value)
    for value in inputs:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = directory / path
        path = path.resolve(strict=True)
        if not path.is_file():
            raise ValueError("Bound input must be an existing regular file")
        bindings[str(path)] = sha256(path)
    request = {"schema": 1, **labels, "targets": list(map(str, targets)), "cwd": str(directory),
               "command": command, "bindings": bindings, "elevation_host": str(host)}
    if len(json.dumps(request).encode("utf-8")) > 32000:
        raise ValueError("Request metadata is too large")
    return request


def verify(request):
    for path, expected in request["bindings"].items():
        if sha256(path) != expected:
            raise ValueError("input_changed: an executable or declared input changed; submit a revised request")


class ElevationDenied(OSError):
    pass


class ElevationLaunchFailed(OSError):
    pass


class ElevatedProcess:
    def __init__(self, handle, native):
        self.handle, self.n = handle, native

    def wait(self):
        try:
            self.n.wait(self.handle)
            code = w.DWORD()
            if not self.n.k.GetExitCodeProcess(self.handle, ctypes.byref(code)):
                raise ctypes.WinError(ctypes.get_last_error())
            return code.value
        finally:
            self.n.close(self.handle)


def shell_launch(host, args, *, show_window=False):
    class ShellInfo(ctypes.Structure):
        _fields_ = [("cbSize", w.DWORD), ("fMask", w.ULONG), ("hwnd", w.HWND),
                    ("lpVerb", w.LPCWSTR), ("lpFile", w.LPCWSTR), ("lpParameters", w.LPCWSTR),
                    ("lpDirectory", w.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", w.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p), ("lpClass", w.LPCWSTR), ("hkeyClass", w.HKEY),
                    ("dwHotKey", w.DWORD), ("hIconOrMonitor", w.HANDLE), ("hProcess", w.HANDLE)]

    n = Native()
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.ShellExecuteExW.argtypes, shell.ShellExecuteExW.restype = [ctypes.POINTER(ShellInfo)], w.BOOL
    info = ShellInfo()
    info.cbSize, info.fMask = ctypes.sizeof(info), 0x40 | 0x100  # process handle + synchronous launch
    info.lpVerb, info.lpFile = "runas", host
    info.lpParameters, info.lpDirectory = subprocess.list2cmdline(args), str(Path(host).parent)
    info.nShow = 1 if show_window else 0
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.get_last_error()
        if error == 1223:
            raise ElevationDenied("Windows UAC was declined; the payload did not start")
        raise ElevationLaunchFailed(str(ctypes.WinError(error)))
    if not info.hProcess:
        raise RuntimeError("launch_ambiguous: no supervised worker handle; inspect before recovery")
    return ElevatedProcess(info.hProcess, n)


def elevate(request_path, digest, host):
    cli = Path(__file__).with_name("cli.py").resolve()
    return shell_launch(host, ["-I", "-B", str(cli), "worker", "--request", str(request_path), "--sha256", digest])


def execute(command, cwd):
    process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    outputs = {}

    def collect(name, stream):
        tail, count = deque(), 0
        while block := stream.read(4096):
            tail.append(block)
            count += len(block)
            while sum(map(len, tail)) > OUTPUT_LIMIT + 4096:
                tail.popleft()
        outputs[name] = b"".join(tail)[-OUTPUT_LIMIT:].decode("utf-8", errors="replace")
        outputs[name + "_truncated"] = count > OUTPUT_LIMIT
        stream.close()

    readers = [threading.Thread(target=collect, args=(name, stream))
               for name, stream in (("stdout", process.stdout), ("stderr", process.stderr))]
    for reader in readers:
        reader.start()
    code = process.wait()
    for reader in readers:
        reader.join()
    return {"ok": code == 0, "command_exit_code": code, **outputs}


def worker(path, digest):
    path = Path(path).resolve(strict=True)
    output = path.with_suffix(".result.json")
    try:
        if sha256(path) != digest:
            raise ValueError("Request bytes changed before elevated execution")
        request = json.loads(path.read_text(encoding="utf-8"))
        if os.name != "nt" or not ctypes.windll.shell32.IsUserAnAdmin():
            raise ValueError("Worker is not elevated; payload not executed")
        verify(request)
        n = Native()
        handle, ticks = n.process(os.getpid())
        n.close(handle)
        atomic_json(path.with_suffix(".worker.json"), {"pid": os.getpid(), "ticks": ticks})
        result = execute(request["command"], request["cwd"])
        result.update(elevated=True, request_id=request["request_id"], request_sha256=digest)
    except Exception as exc:
        result = {"ok": False, "failure_kind": "worker_failed", "error": str(exc),
                  "command_exit_code": None, "request_sha256": digest}
    atomic_json(output, result)
    return 0 if result["ok"] else 1


def finalize(request_id, queue=None):
    """Remove only completed intrinsic metadata after both exact processes exit."""
    import re
    if not re.fullmatch(r"[0-9a-f]{32}", request_id):
        raise ValueError("Invalid request identity")
    q = queue or Queue()
    with q.lock():
        if any(t["id"] == request_id for t in q.read()["tickets"]):
            raise ValueError("Request still owns a queue ticket; do not finalize it")
        path = q.root / "requests" / (request_id + ".json")
        request = json.loads(path.read_text(encoding="utf-8"))
        identity = json.loads(path.with_suffix(".worker.json").read_text(encoding="utf-8"))
        result = json.loads(path.with_suffix(".result.json").read_text(encoding="utf-8"))
        if (request.get("request_id") != request_id or result.get("request_sha256") != sha256(path)):
            raise ValueError("Completed metadata does not match this request")
        if q.alive(request["owner"]) or q.alive(identity):
            raise ValueError("Supervisor or worker is still alive; preserve its metadata")
        for suffix in (".json", ".worker.json", ".result.json"):
            path.with_suffix(suffix).unlink()
    return {"ok": True, "operation": "finalize", "request_id": request_id}


def run(request, *, queue=None, dialog=explain, launcher=elevate):
    q = queue or Queue()
    ticket = q.register(request)
    request = {**request, "request_id": ticket["id"], "owner": {"pid": ticket["pid"], "ticks": ticket["ticks"]}}
    path = q.root / "requests" / (ticket["id"] + ".json")
    result = {"ok": False, "operation": "run", "request_id": ticket["id"],
              "ticket": ticket["number"], "feedback": "", "failure_kind": None, "launched": False}
    settled = True
    released = False
    finished = False
    launched = False
    try:
        atomic_json(path, request)
        digest = sha256(path)
        print(json.dumps({"state": "queued", "request_id": ticket["id"], "ticket": ticket["number"]}),
              file=sys.stderr, flush=True)
        q.wait_turn()
        with Mutex(q.namespace + ".Prompt", q.n):
            q.phase("explaining")
            print(json.dumps({"state": "explaining", "request_id": ticket["id"]}), file=sys.stderr, flush=True)
            verify(request)
            answer = dialog(request)
            result["feedback"] = answer["feedback"]
            if not answer["accepted"]:
                result["failure_kind"] = "user_declined"
                return result
            if sha256(path) != digest:
                raise ValueError("input_changed: request changed while the dialog was open")
            verify(request)
            q.phase("uac")
            settled = False
            try:
                child = launcher(path, digest, request["elevation_host"])
            except ElevationDenied:
                settled = True
                result["failure_kind"] = "uac_declined"
                return result
            except ElevationLaunchFailed as exc:
                settled = True
                result.update(failure_kind="elevation_launch_failed", error=str(exc))
                return result
            settled = True
            launched = True
            result["launched"] = True
            q.phase("launched")
            q.release("worker_launched")
            released = True
        print(json.dumps({"state": "worker_launched", "request_id": ticket["id"], "prompt_gate_released": True}),
              file=sys.stderr, flush=True)
        worker_code = child.wait()
        finished = True
        worker_result = json.loads(path.with_suffix(".result.json").read_text(encoding="utf-8"))
        if worker_result.get("request_sha256") != digest:
            raise ValueError("Elevated result does not match the requested payload")
        if worker_result.get("ok") and (worker_code != 0 or worker_result.get("command_exit_code") != 0 or
                                       worker_result.get("request_id") != request["request_id"] or
                                       worker_result.get("elevated") is not True):
            raise ValueError("Worker success contradicts its exit, identity or elevation evidence")
        return {**result, **worker_result, "worker_exit_code": worker_code, "prompt_gate_released": True}
    except Exception as exc:
        result.update(failure_kind="request_failed" if settled else "owner_recovery_required", error=str(exc))
        return result
    finally:
        if settled:
            if not released:
                q.release(result["failure_kind"] or "request_failed")
            # Exact intrinsic request metadata, not general artifact deletion.
            if not launched or finished:
                path.unlink(missing_ok=True)
                path.with_suffix(".result.json").unlink(missing_ok=True)
                path.with_suffix(".worker.json").unlink(missing_ok=True)
        else:
            q.n.close(q.event)
            q.event = None
