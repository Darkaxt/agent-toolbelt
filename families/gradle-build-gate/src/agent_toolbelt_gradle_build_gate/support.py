"""Ticket-scoped diagnostics and owner responses; never execution deadlines."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid

from .gate import NamedMutex, NO_WINDOW
from .queue import NativeWait, default_root


def ticket_path(ticket_id, root=None):
    if not re.fullmatch(r"[0-9a-f]{32}", ticket_id):
        raise ValueError("Invalid build ticket ID")
    return (Path(root) if root else default_root()) / "support" / (ticket_id + ".json")


def state_lock(ticket_id):
    return NamedMutex(r"Local\Darka.GradleOwnerSupport." + ticket_id)


def save(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(uuid.uuid4().hex + ".pending")
    try:
        with pending.open("x", encoding="utf-8") as stream:
            json.dump(state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def read(ticket_id, root=None):
    with state_lock(ticket_id):
        state = json.loads(ticket_path(ticket_id, root).read_text(encoding="utf-8"))
        if state.get("schema") != 1 or state.get("ticket", {}).get("id") != ticket_id:
            raise ValueError("Invalid support record")
        return state


def complete(ticket_id, root=None):
    path = ticket_path(ticket_id, root)
    with state_lock(ticket_id):
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("status") != "wrapper_exited":
            raise ValueError("Wrapper completion has not been verified")
        state.update(status="completed", completion_verified=True)
        save(path, state)


def validate_response(state, request_id, decision, reason):
    if decision not in ("continue", "cancel") or not reason.strip():
        raise ValueError("Choose continue/cancel and provide a diagnostic reason")
    if state.get("status") != "running":
        raise ValueError("Build is not running; response refused")
    if state.get("support_available", True) is not True:
        raise ValueError("Support monitor unavailable; response refused")
    request = state.get("request")
    if not request or request.get("id") != request_id or request.get("response") is not None:
        raise ValueError("Request is stale, missing or already answered")
    if request.get("revision") != state.get("revision"):
        raise ValueError("Build made progress after this request; stale response refused")


def respond(ticket_id, request_id, decision, reason, root=None):
    path = ticket_path(ticket_id, root)
    native = NativeWait()
    with state_lock(ticket_id):
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("schema") != 1 or state.get("ticket", {}).get("id") != ticket_id:
            raise ValueError("Invalid support record")
        validate_response(state, request_id, decision, reason)
        owner = state["ticket"]
        process, _ = native.process(owner["pid"], owner["created_ticks"])
        if process is None:
            raise ValueError("Supervisor exited or identity changed; response refused")
        try:
            state["request"]["response"] = {"decision": decision, "reason": reason.strip(),
                                               "responded_at": time.time()}
            save(path, state)
            event = native.event(event_name(ticket_id))
            try:
                native.signal(event)
            finally:
                native.k.CloseHandle(event)
        finally:
            native.k.CloseHandle(process)
    return {"ok": True, "operation": "respond", "ticket_id": ticket_id,
            "decision": decision, "state": "response_submitted",
            "completion_verified": False}


def event_name(ticket_id):
    return r"Local\Darka.GradleOwnerResponse." + ticket_id


def codex_message(owner, prompt):
    """Use the installed MCP, preserving executor metadata and model selection."""
    node = os.environ.get("CODEX_MCP_NODE_PATH")
    pipe = os.environ.get("CODEX_APP_TOOLS_PIPE_PATH")
    if not node or not pipe or not owner:
        return {"state": "unavailable", "reason": "codex_executor_transport_missing"}
    root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    candidates = sorted((root / "plugins/cache/openai-bundled/codex-app-tools").glob("*/server.mjs"),
                        key=lambda p: p.stat().st_mtime_ns, reverse=True)
    if not candidates:
        return {"state": "unavailable", "reason": "installed_app_tools_mcp_missing"}
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "gradle-owner-support", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "send_message_to_thread", "arguments": {"threadId": owner, "prompt": prompt},
            "_meta": {"threadId": owner}}},
    ]
    try:
        child = subprocess.Popen([node, str(candidates[0])], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 text=True, encoding="utf-8", creationflags=NO_WINDOW)
    except OSError:
        return {"state": "unavailable", "reason": "app_tools_mcp_launch_failed"}
    finished = threading.Event()
    response = {}
    def exchange():
        try:
            for message in messages:
                child.stdin.write(json.dumps(message) + "\n"); child.stdin.flush()
                if "id" not in message:
                    continue
                while True:
                    line = child.stdout.readline()
                    if not line:
                        raise OSError("MCP closed before reply")
                    result = json.loads(line)
                    if result.get("id") == message["id"]:
                        break
                if "error" in result:
                    raise OSError("MCP rejected request")
                if message["id"] == 2:
                    response.update(result)
        except (OSError, ValueError):
            response.clear()
        finally:
            finished.set()
    worker = threading.Thread(target=exchange, name="gradle-codex-notification")
    worker.start()
    try:
        # The timeout bounds this diagnostic transport only, never the build.
        completed = finished.wait(30)
        if not completed:
            return {"state": "delivery_unknown", "reason": "diagnostic_transport_wait_elapsed"}
        if not response or response.get("result", {}).get("isError"):
            return {"state": "unavailable", "reason": "app_tools_rejected_or_closed"}
        return {"state": "accepted_unacknowledged", "transport": "codex_app_tools_mcp"}
    finally:
        if finished.is_set():
            child.stdin.close()
        if child.poll() is None:
            child.kill()  # Only our diagnostic MCP process, never Gradle.
        child.wait()
        worker.join()
        child.stdout.close()
        if not child.stdin.closed:
            child.stdin.close()


def notify(owner, ticket, request, path):
    prompt = (f"Gradle owner support requested for ticket {ticket['id']}. This is a diagnostic "
              f"quiet-period alert, NOT proof of deadlock. Read {path}. Request ID: {request['id']}. "
              "Inspect the owned build and diagnostics. Respond with the gradle-build-gate helper's "
              "respond command (continue with evidence, or cancel with a reason). Keep the original "
              "supervisor session alive; do not launch another build, stop daemons or change permissions.")
    print(json.dumps({"state": "owner_support_requested", "ticket_id": ticket["id"],
                      "request_id": request["id"], "record": str(path), "prompt": prompt}),
          file=sys.stderr, flush=True)
    return codex_message(owner, prompt) if owner else {
        "state": "tool_session_emitted_unacknowledged", "transport": "owned_tool_session"}


def owned_processes(snapshot, wrapper, connections=()):
    """Only stable parent chains rooted in this exact wrapper; no guessed daemon."""
    rows = {r["pid"]: r for r in snapshot}
    first = rows.get(wrapper["pid"])
    if not first or first.get("created_ticks") != wrapper["created_ticks"]:
        return []
    selected = {first["pid"]: first}
    changed = True
    while changed:
        changed = False
        for row in rows.values():
            parent = selected.get(row.get("parent_pid"))
            if (row["pid"] not in selected and parent and row.get("created_ticks", 0) >= parent["created_ticks"]):
                selected[row["pid"]] = row
                changed = True
        # A reused daemon requires reciprocal live TCP endpoints with our client.
        endpoints = {(c["local_address"], c["local_port"], c["remote_address"], c["remote_port"]): c["pid"]
                     for c in connections}
        clients = {pid for pid, row in selected.items() if row.get("gradle_client")}
        for endpoint, pid in endpoints.items():
            peer = endpoints.get((endpoint[2], endpoint[3], endpoint[0], endpoint[1]))
            if pid in clients and peer in rows and peer not in selected and rows[peer].get("gradle_daemon"):
                selected[peer] = rows[peer]
                changed = True
    return list(selected.values())


def diagnostics(wrapper, directory):
    from .gate import powershell
    directory.mkdir(parents=True, exist_ok=True)
    child = powershell("support-snapshot.ps1", env={**os.environ,
                       "GRADLE_GATE_SUPPORT_WRAPPER_PID": str(wrapper["pid"])})
    try:
        out, _ = child.communicate(timeout=30)
        if child.returncode:
            return {"state": "unavailable", "reason": "process_snapshot_failed"}
        snapshot = json.loads(out.lstrip("\ufeff"))
        rows = owned_processes(snapshot["processes"], wrapper, snapshot.get("connections", []))
        if not rows:
            return {"state": "unavailable", "reason": "wrapper_identity_not_observed"}
        dumps = []
        native = NativeWait()
        for row in rows[:8]:
            java = Path(row.get("executable") or "")
            jcmd = java.with_name("jcmd.exe")
            if java.name.lower() not in ("java.exe", "javaw.exe") or not jcmd.is_file():
                continue
            handle, _ = native.process(row["pid"], row["created_ticks"])
            if not handle:
                continue
            try:
                dump = directory / f"jvm-{row['pid']}-{row['created_ticks']}.txt"
                with dump.open("x", encoding="utf-8") as stream:
                    probe = subprocess.Popen([str(jcmd), str(row["pid"]), "Thread.print", "-l"],
                                             stdout=stream, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
                    try:
                        code = probe.wait(timeout=30)
                        dumps.append({"pid": row["pid"], "path": str(dump), "exit_code": code})
                    except subprocess.TimeoutExpired:
                        probe.kill(); probe.wait()  # Diagnostic attach only.
                        dumps.append({"pid": row["pid"], "state": "diagnostic_attach_unavailable"})
            finally:
                native.k.CloseHandle(handle)
        return {"state": "captured", "processes": rows, "thread_dumps": dumps,
                "limits": "Exact wrapper descendants and reciprocal client-daemon bindings only; no unbound JVM inference"}
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return {"state": "unavailable", "reason": "diagnostic_capture_failed"}
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()


def signal_private_console(pid, ticks):
    """Run in a disposable process, never detach the supervisor's own console."""
    native = NativeWait()
    handle, _ = native.process(pid, ticks)
    if not handle:
        return False
    k = native.k
    for name, args in (("FreeConsole", []), ("AttachConsole", [wintypes.DWORD]),
                       ("SetConsoleCtrlHandler", [ctypes.c_void_p, wintypes.BOOL]),
                       ("GenerateConsoleCtrlEvent", [wintypes.DWORD, wintypes.DWORD])):
        getattr(k, name).argtypes = args
        getattr(k, name).restype = wintypes.BOOL
    attached = False
    try:
        k.FreeConsole()
        if not k.AttachConsole(pid):
            raise ctypes.WinError(ctypes.get_last_error())
        attached = True
        if k.WaitForSingleObject(handle, 0) != 258:
            return False
        if not k.SetConsoleCtrlHandler(None, True) or not k.GenerateConsoleCtrlEvent(0, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return True
    finally:
        if attached:
            k.FreeConsole()
        native.k.CloseHandle(handle)


def request_console_cancel(wrapper):
    source = ("from agent_toolbelt_gradle_build_gate.support import signal_private_console; "
              f"raise SystemExit(0 if signal_private_console({wrapper['pid']}, {wrapper['created_ticks']}) else 3)")
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent), "PYTHONDONTWRITEBYTECODE": "1"}
    child = subprocess.Popen([sys.executable, "-B", "-c", source], env=env, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
    return {"state": "ctrl_c_requested" if child.wait() == 0 else "cancel_not_delivered",
            "completion_verified": False}


class BuildSupport:
    def __init__(self, ticket, project, log_path, *, quiet_seconds=300, root=None):
        if quiet_seconds <= 0:
            raise ValueError("Diagnostic quiet interval must be positive")
        self.ticket = ticket
        self.path = ticket_path(ticket["id"], root)
        self.quiet_seconds = quiet_seconds
        self.native = NativeWait()
        self.event = self.native.event(event_name(ticket["id"]))
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.last_progress = time.monotonic()
        self.last_review = self.last_progress
        self.revision = 0
        self.requested_revision = None
        self.captures = []
        self.state = {"schema": 1, "ticket": ticket, "project": str(project), "log_path": str(log_path),
                      "owner_task": os.environ.get("CODEX_THREAD_ID"), "status": "running",
                      "progress": {"task": None, "test": None, "source": "not_observed"},
                      "request": None, "cancellation": None, "revision": 0,
                      "support_available": True}

    def update(self, **fields):
        with self.lock, state_lock(self.ticket["id"]):
            # Preserve independently submitted responses during monitor writes.
            if self.path.exists():
                disk = json.loads(self.path.read_text(encoding="utf-8"))
                request = fields.get("request", self.state["request"])
                if request and (disk.get("request") or {}).get("id") == request["id"]:
                    request = dict(request)
                    request["response"] = disk["request"].get("response")
                    fields["request"] = request
            self.state.update(fields)
            save(self.path, self.state)

    def start(self, child):
        handle, ticks = self.native.process(child.pid)
        if not handle:
            raise RuntimeError("Cannot bind running wrapper identity")
        self.native.k.CloseHandle(handle)
        self.wrapper = {"pid": child.pid, "created_ticks": ticks}
        self.update(wrapper=self.wrapper)
        print(json.dumps({"state": "build_support_ready", "ticket_id": self.ticket["id"],
                          "record": str(self.path)}), file=sys.stderr, flush=True)
        self.monitor = threading.Thread(target=self.watch, name="gradle-owner-support")
        self.monitor.start()

    def progress(self, line):
        task = re.fullmatch(r"> Task (:\S+)(?: .*)?", line.strip())
        test = re.fullmatch(r"(.+ > .+) (STARTED|PASSED|SKIPPED|FAILED)", line.strip())
        if not task and not test:
            return
        with self.lock:
            self.revision += 1
            self.last_progress = time.monotonic()
            progress = dict(self.state["progress"])
            if task:
                progress.update(task=task[1], test=None, source="gradle_console_task")
            else:
                progress.update(test=test[1], test_state=test[2], source="gradle_test_logging")
            self.update(progress=progress, revision=self.revision)
        self.native.signal(self.event)

    def watch(self):
        try:
            self._watch()
        except (OSError, ValueError, RuntimeError) as exc:
            try:
                self.update(support_available=False)
            except (OSError, ValueError):
                pass
            print(json.dumps({"state": "support_monitor_unavailable", "failure_kind": type(exc).__name__,
                              "build_still_supervised": True}), file=sys.stderr, flush=True)

    def capture(self, request):
        try:
            notification = notify(self.state["owner_task"], self.ticket, request, self.path)
            evidence = diagnostics(self.wrapper, self.path.parent / self.ticket["id"] / request["id"])
            with self.lock:
                current = self.state["request"]
                if current and current["id"] == request["id"]:
                    current = dict(current)
                    current.update(notification=notification, diagnostics=evidence)
                    self.update(request=current)
        except (OSError, ValueError, RuntimeError) as exc:
            print(json.dumps({"state": "support_capture_unavailable", "failure_kind": type(exc).__name__,
                              "ticket_id": self.ticket["id"]}), file=sys.stderr, flush=True)

    def _watch(self):
        handled = set()
        while not self.stop_event.is_set():
            with self.lock:
                remaining = max(0, self.quiet_seconds - (time.monotonic() - max(self.last_progress, self.last_review)))
                due = self.requested_revision != self.revision and remaining == 0
                request = self.state["request"]
            if due:
                with self.lock:
                    self.requested_revision = self.revision
                    request = {"id": uuid.uuid4().hex, "revision": self.revision,
                               "reason": "diagnostic_quiet_period", "response": None}
                    self.update(request=request)
                # Keep responses live during MCP/JVM diagnostic operations.
                capture = threading.Thread(target=self.capture, args=(request,), name="gradle-support-evidence")
                self.captures = [t for t in self.captures if t.is_alive()]
                if not self.captures:
                    self.captures.append(capture)
                    capture.start()
                else:
                    notification = notify(None, self.ticket, request, self.path)
                    request = dict(self.state["request"])
                    request.update(notification=notification, diagnostics={"state": "previous_capture_still_running"})
                    self.update(request=request)
            else:
                # Native event for responses/progress; the finite wait schedules diagnostics ONLY.
                timeout = 0xFFFFFFFF if self.requested_revision == self.revision else max(1, int(remaining * 1000))
                outcome = self.native.k.WaitForSingleObject(self.event, timeout)
                if outcome not in (0, 258):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.native.k.ResetEvent(self.event)
            if self.stop_event.is_set():
                break
            with self.lock:
                self.update()
                request = self.state["request"]
                response = request.get("response") if request else None
                if response and request["id"] not in handled:
                    handled.add(request["id"])
                    if request["revision"] != self.revision:
                        print(json.dumps({"state": "stale_owner_response_ignored", "ticket_id": self.ticket["id"]}),
                              file=sys.stderr, flush=True)
                        continue
                    if response["decision"] == "cancel":
                        self.update(cancellation=request_console_cancel(self.wrapper))
                    else:
                        # Continuing is not evidence of new build progress or a
                        # permanent mute. Schedule the next diagnostic review.
                        self.last_review = time.monotonic()
                        self.requested_revision = None
                    print(json.dumps({"state": "owner_response_handled", "ticket_id": self.ticket["id"],
                                      "decision": response["decision"], "cancellation": self.state["cancellation"]}),
                          file=sys.stderr, flush=True)

    def finish(self, exit_code):
        self.stop_event.set()
        self.update(status="wrapper_exited", exit_code=exit_code)
        self.native.signal(self.event)
        if hasattr(self, "monitor"):
            self.monitor.join()
        for capture in self.captures:
            capture.join()
        self.native.k.CloseHandle(self.event)
        return {"record": str(self.path), "request": self.state["request"],
                "cancellation": self.state["cancellation"]}
