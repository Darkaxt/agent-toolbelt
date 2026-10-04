from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import uuid
from urllib.parse import unquote, urlparse


MUTEX_NAME = r"Local\Darka.AndroidGradleBuildGate"
ASSETS = Path(__file__).with_name("assets")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_LOG_CURSORS = {}


def wrapper_version(project):
    url = read_properties(project / "gradle/wrapper/gradle-wrapper.properties").get("distributionUrl", "")
    match = re.fullmatch(r"gradle-([0-9][A-Za-z0-9.+-]*)-(?:bin|all)\.zip", unquote(urlparse(url).path).split("/")[-1])
    if not match:
        raise ValueError("Cannot identify pinned wrapper version for daemon retirement; use --retire-daemons none for a custom distribution")
    return match[1]


def retirement_candidates(inspection, version, heap, policy):
    if policy == "none":
        return []
    if policy not in ("incompatible", "all-idle"):
        raise ValueError("Invalid daemon retirement policy")
    if not inspection["safe_to_start"]:
        raise ValueError("Active or ambiguous processes prevent daemon retirement")
    candidates = []
    for row in inspection["processes"]:
        if row["state"] != "idle" or not row.get("version") or not row.get("max_heap"):
            raise ValueError("Unknown daemon identity/version/heap prevents retirement")
        reason = ("all_idle_requested" if policy == "all-idle" else
                  "different_version" if row["version"] != version else
                  "different_heap" if heap_bytes(row["max_heap"]) != heap_bytes(heap) else None)
        if reason:
            candidates.append({**row, "retirement_reason": reason})
    return candidates


def heap_bytes(value):
    match = re.fullmatch(r"-xmx(\d+)([kmg])", value, re.I)
    if not match:
        raise ValueError("Unknown daemon maximum heap")
    return int(match[1]) * {"k": 1024, "m": 1024**2, "g": 1024**3}[match[2].lower()]


def daemon_details(row):
    command = row.get("command") or ""
    version = re.search(r"org\.gradle\.launcher\.daemon\.bootstrap\.GradleDaemon\s+([^\s\"]+)", command)
    heaps = re.findall(r"(?<!\S)(-Xmx[0-9]+[kmg])(?=\s|$)", command, re.I)
    # Distribution comes from the running daemon's classpath, not a global guess.
    paths = re.findall(r'(?:"([^"\r\n]*\.jar)"|([^\s";]+\.jar))', command)
    distribution = None
    for quoted, bare in paths:
        for item in (quoted or bare).split(";"):
            path = Path(item)
            if version and path.name in (f"gradle-launcher-{version[1]}.jar", f"gradle-daemon-main-{version[1]}.jar"):
                distribution = str(path.parent.parent)
    return {"version": version[1] if version else None, "max_heap": heaps[-1].lower() if heaps else None,
            "distribution": distribution, "java_executable": row.get("executable")}


class RetirementFailure(RuntimeError):
    def __init__(self, candidate, exit_code, diagnostics, compilation_failed):
        self.failure_kind = "adapter_compilation_failure" if compilation_failed else "retirement_verification_failure"
        self.diagnostics = {"pid": candidate["pid"], "target_version": candidate.get("version"),
                            "adapter_exit_code": exit_code, "details": diagnostics}
        super().__init__(f"Daemon retirement blocked for PID {candidate['pid']} (Gradle {candidate.get('version')}, "
                         f"{self.failure_kind}, exit {exit_code}): " + "; ".join(diagnostics))


def retirement_diagnostics(stderr):
    """Allow compiler symbols and our fixed runtime codes, never raw exception data."""
    details = []
    compiled = False
    for line in stderr.splitlines():
        line = line.strip()
        error = re.search(r"(?:^|: )error: (.*)$", line)
        text = error[1] if error else line
        if error:
            compiled = compiled or text == "compilation failed" or "RetireDaemon.java:" in line
        if text in ("cannot find symbol", "compilation failed"):
            details.append(text)
        elif re.fullmatch(r"(?:symbol|location):\s+(?:class|variable|package|interface) [A-Za-z0-9_.$]+", text):
            details.append(re.sub(r"\s+", " ", text))
        elif re.fullmatch(r"(?:<anonymous RetireDaemon\$\d+>|RetireDaemon\$\d+) is not abstract and does not override abstract method [A-Za-z0-9_<>., ()]+ in [A-Za-z0-9_.$]+", text):
            details.append(text)
        elif re.fullmatch(r"Retirement blocked: stage=(?:arguments|identity|registry|connection|shutdown_request|process_exit) reason=(?:operation_failed|pid_identity_changed|daemon_not_idle|target_jvm_mismatch|shutdown_rejected) kind=[A-Za-z0-9_]+", text):
            details.append(text)
    return list(dict.fromkeys(details))[:12] or ["No safe diagnostic code available; adapter launch/protocol failed"], compiled


def retire_daemon(candidate, *, inspect_only=False):
    java = Path(candidate.get("java_executable") or "")
    distribution = Path(candidate.get("distribution") or "")
    log = Path(candidate.get("daemon_log") or "")
    registry = log.parent / "registry.bin"
    if not java.is_file() or not (distribution / "lib").is_dir() or not registry.is_file():
        raise ValueError("Cannot verify candidate JDK/distribution/registry; retirement and build blocked")
    child = subprocess.Popen([str(java), "-Xmx128m", "--class-path", str(distribution / "lib/*"),
                           str(ASSETS / "RetireDaemon.java"), "inspect" if inspect_only else "retire",
                           str(registry), str(candidate["pid"]), str(round(candidate["created"] * 1000))],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    signals = [signal.SIGINT] + ([signal.SIGBREAK] if hasattr(signal, "SIGBREAK") else [])
    handlers = {s: signal.getsignal(s) for s in signals}
    def retain_retirement(signum, frame):
        print("Retirement interrupted; retaining gate until shutdown supervision completes.", file=sys.stderr, flush=True)
    for s in signals:
        signal.signal(s, retain_retirement)
    try:
        output, stderr = child.communicate()
    finally:
        child.wait()
        child.stdout.close(); child.stderr.close()
        for s, handler in handlers.items():
            signal.signal(s, handler)
    outcome = output.strip()
    allowed = ("registry_idle_verified", "already_exited") if inspect_only else ("process_exit_verified", "already_exited")
    if child.returncode or outcome not in allowed:
        diagnostics, compiled = retirement_diagnostics(stderr)
        raise RetirementFailure(candidate, child.returncode, diagnostics, compiled)
    return {"pid": candidate["pid"], "created": candidate["created"], "version": candidate["version"],
            "reason": candidate.get("retirement_reason"), "outcome": outcome,
            "process_exit_verified": outcome in ("process_exit_verified", "already_exited")}


class NamedMutex:
    """The OS thread that enters owns the mutex until it explicitly releases it."""

    def __init__(self, name=None):
        if os.name != "nt":
            raise OSError("Gradle build gate requires Windows")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
        self.kernel.ReleaseMutex.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.name = name or MUTEX_NAME
        self.handle = self.kernel.CreateMutexW(None, False, self.name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.owner = None
        self.abandoned = False

    def __enter__(self):
        if self.name == MUTEX_NAME:
            print("Waiting for shared Gradle gate.", file=sys.stderr, flush=True)
        result = self.kernel.WaitForSingleObject(self.handle, 0xFFFFFFFF)
        if result not in (0, 0x80):
            self.kernel.CloseHandle(self.handle)
            raise ctypes.WinError(ctypes.get_last_error())
        self.owner = threading.get_ident()
        self.abandoned = result == 0x80
        return self

    def __exit__(self, *args):
        if self.owner != threading.get_ident():
            raise RuntimeError("Mutex must be released by its owning thread")
        try:
            if not self.kernel.ReleaseMutex(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.kernel.CloseHandle(self.handle)


def classify_process(process, log="", log_modified=0, connected=False, connections_known=True):
    name = process.get("name", "").lower()
    command = process.get("command")
    if not command:
        return "ambiguous" if name in ("java.exe", "javaw.exe", "gradle.exe", "cmd.exe") else "unrelated"
    lowered = command.lower()
    if "org.gradle.launcher.daemon.bootstrap.gradledaemon" in lowered:
        if connected:
            return "active"
        if not connections_known or log_modified < process["created"]:
            return "ambiguous"
        markers = list(re.finditer(r"Marking the daemon as (idle|busy)", log, re.I))
        if not markers:
            return "ambiguous"
        return "idle" if markers[-1].group(1).lower() == "idle" else "active"
    if any(token in lowered for token in ("org.gradle.wrapper.gradlewrappermain", "org.gradle.launcher.gradlemain")):
        return "active"
    if name in ("cmd.exe", "gradle.exe") and re.search(r"(?:^|[\\/\s\"])(?:gradlew(?:\.bat)?|gradle(?:\.bat|\.exe)?)(?=[\s\"]|$)", lowered):
        return "active"
    return "unrelated"


def daemon_lifecycle(path, process_identity=None):
    stat = path.stat()
    key = (str(path), stat.st_ino, process_identity)
    offset, stamp, last, carry = _LOG_CURSORS.get(key, (0, 0, "", b""))
    if stat.st_size < offset or (stat.st_mtime_ns != stamp and stat.st_size <= offset):
        offset, last, carry = 0, "", b""
    with path.open("rb") as handle:
        handle.seek(offset)
        while chunk := handle.read(256 * 1024):
            data = carry + chunk
            matches = list(re.finditer(rb"Marking the daemon as (idle|busy)", data, re.I))
            if matches:
                last = matches[-1].group().decode("ascii")
            carry = data[-128:]
        _LOG_CURSORS[key] = (handle.tell(), stat.st_mtime_ns, last, carry)
    return last


def read_properties(path):
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8-sig")
    text = re.sub(r"(?<!\\)(?:\\\\)*\\\r?\n\s*", lambda m: m.group(0).split("\\\n")[0].split("\\\r\n")[0].rstrip("\\") + " ", text)
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "!")):
            continue
        match = re.match(r"([^:=\s]+)\s*(?:[:=]\s*|\s+)(.*)$", line)
        if match:
            value = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), match[2])
            value = re.sub(r"\\([ :=\\])", r"\1", value)
            values[match[1]] = value
    return values


def heap_args(arguments, gb):
    tokens = re.findall(r'"[^"\r\n]*"|\S+', arguments)
    kept = [token for token in tokens if not re.match(r"^-Xm[xs]", token, re.I)]
    initial = [token for token in tokens if token.lower().startswith("-xms")]
    for token in initial:
        m = re.fullmatch(r"-Xms(\d+)([kmg])", token, re.I)
        if not m or int(m[1]) * {"k": 1024, "m": 1024**2, "g": 1024**3}[m[2].lower()] > gb * 1024**3:
            raise ValueError("Existing initial heap exceeds selected maximum; resolve it explicitly")
    return " ".join(initial + kept + [f"-Xmx{gb}g"])


def validate_arguments(arguments):
    if not arguments:
        raise ValueError("Provide Gradle tasks/arguments after --")
    for value in arguments:
        if re.search(r"[&|<>^%!\r\n]", value):
            raise ValueError("Batch-shell metacharacters are not accepted")
        if value in ("--stop", "--foreground", "--parallel", "-t", "--continuous", "-p", "--project-dir") or value.startswith("--project-dir="):
            raise ValueError(f"Unsafe or conflicting Gradle option: {value}")
        if value.startswith(("--max-workers", "-Dorg.gradle.workers.max", "-Dorg.gradle.parallel", "-Porg.gradle.parallel",
                             "-Porg.gradle.workers.max")):
            raise ValueError("Use the helper resource profile, not conflicting Gradle worker options")


def observation_homes(arguments=(), extra=(), project=None):
    homes = [Path.home() / ".gradle"]
    if os.getenv("GRADLE_USER_HOME"):
        homes.append(Path(os.environ["GRADLE_USER_HOME"]))
    for index, arg in enumerate(arguments):
        if arg in ("--gradle-user-home", "-g") and index + 1 < len(arguments):
            homes.append(Path(arguments[index + 1]))
        elif arg.startswith("--gradle-user-home="):
            homes.append(Path(arg.split("=", 1)[1]))
    homes.extend(Path(p).expanduser() for p in extra)
    base = Path(project) if project is not None else Path.cwd()
    return list(dict.fromkeys((p if p.is_absolute() else base / p).resolve() for p in homes))


def make_profile(project, arguments, homes, *, gradle_heap=3, kotlin_heap=3, memory_reason=None, kotlin_strategy=None):
    if any(not 1 <= n <= 64 for n in (gradle_heap, kotlin_heap)):
        raise ValueError("Heap budgets must be between 1 and 64 GB")
    if max(gradle_heap, kotlin_heap) > 3 and not memory_reason:
        raise ValueError("Larger heaps require --memory-reason with diagnosed evidence")
    validate_arguments(arguments)
    properties = read_properties(project / "gradle.properties")
    # Gradle user-home properties override project properties. Extra observation
    # homes do not participate in configuration precedence.
    user_home = observation_homes(arguments, project=project)[-1]
    properties.update(read_properties(user_home / "gradle.properties"))
    clean = []
    keys = ("org.gradle.jvmargs", "kotlin.daemon.jvmargs")
    for key in keys:
        env_key = "ORG_GRADLE_PROJECT_" + key
        if env_key in os.environ:
            properties[key] = os.environ[env_key]
    for arg in arguments:
        handled = False
        for key in keys:
            for prefix in ("-D" + key + "=", "-P" + key + "="):
                if arg.startswith(prefix):
                    properties[key] = arg[len(prefix):]
                    handled = True
        if not handled:
            clean.append(arg)
    # Do not allow an inherited launcher property to invisibly override the
    # selected profile. Other JAVA/GRADLE options are passed through unchanged.
    for key in ("JAVA_OPTS", "GRADLE_OPTS", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"):
        value = os.environ.get(key, "")
        if "org.gradle.jvmargs" in value or "org.gradle.parallel" in value or "org.gradle.workers.max" in value:
            raise ValueError(f"Resolve profile overrides in {key} before building")
        if key == "_JAVA_OPTIONS" and re.search(r"(?:^|\s)-Xmx", value, re.I):
            raise ValueError("_JAVA_OPTIONS can override JVM heap budgets; resolve it before building")
    gradle_args = heap_args(properties.get("org.gradle.jvmargs", ""), gradle_heap)
    kotlin_args = heap_args(properties.get("kotlin.daemon.jvmargs", ""), kotlin_heap)
    full = clean + ["--max-workers=2", "--no-parallel", f"-Dorg.gradle.jvmargs={gradle_args}",
                    f"-Pkotlin.daemon.jvmargs={kotlin_args}", "--init-script", str(ASSETS / "profile.init.gradle")]
    if kotlin_strategy:
        full.append(f"-Pkotlin.compiler.execution.strategy={kotlin_strategy}")
    validate_arguments(full[:len(clean)])
    for arg in full:
        if re.search(r"[&|<>^%!\r\n]", arg):
            raise ValueError("JVM/path settings contain unsafe batch-shell metacharacters")
    env = dict(os.environ)
    env["CMAKE_BUILD_PARALLEL_LEVEL"] = "2"
    env["MAKEFLAGS"] = re.sub(r"(?:^|\s)(?:-j\s*\d*|--jobs(?:=\d+)?)", "", env.get("MAKEFLAGS", "")).strip() + " -j2"
    return {"arguments": full, "environment": env, "gradle_jvmargs": gradle_args,
            "kotlin_daemon_jvmargs": kotlin_args, "kotlin_strategy": kotlin_strategy or "project_default",
            "max_workers": 2, "parallel": False, "test_max_parallel_forks": 1,
            "native_environment_budget": 2, "native_effective_verified": False,
            "memory_reason": memory_reason}


def powershell(script, *, env=None):
    exe = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe")
    return subprocess.Popen([exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                             "-File", str(ASSETS / script)], env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)


def attribute_cleanup_activity(snapshot, results):
    """Scope cleanup only; never substitute inferred identity for build retirement."""
    raw = {row["pid"]: row for row in snapshot["processes"]}
    observed = {row["pid"]: row for row in results}
    for row in results:
        row["cleanup_versions"] = [row["version"]] if row.get("version") else []
        row["cleanup_activity_source"] = "observed_version" if row.get("version") else "unattributed"
    if snapshot.get("connections_known") is not True or snapshot.get("cleanup_identity_known", True) is not True:
        return
    endpoints = {}
    for connection in snapshot.get("connections", []):
        key = (connection["local_address"], connection["local_port"],
               connection["remote_address"], connection["remote_port"])
        endpoints.setdefault(key, set()).add(connection["pid"])
    for row in results:
        process = raw[row["pid"]]
        command = (process.get("command") or "").lower()
        if row["cleanup_versions"] or not any(token in command for token in
                ("org.gradle.wrapper.gradlewrappermain", "org.gradle.launcher.gradlemain")):
            continue
        peers = set()
        for key, owners in endpoints.items():
            if row["pid"] in owners:
                peers.update(endpoints.get((key[2], key[3], key[0], key[1]), set()))
        daemons = [observed[pid] for pid in peers if pid in observed and
                   "org.gradle.launcher.daemon.bootstrap.gradledaemon" in
                   (raw[pid].get("command") or "").lower()]
        if (len(daemons) == 1 and daemons[0].get("version") and
                process.get("session") is not None and
                process["session"] == raw[daemons[0]["pid"]].get("session")):
            row["cleanup_versions"] = [daemons[0]["version"]]
            row["cleanup_activity_source"] = "daemon_connection"
    # An explicit Gradle batch launcher may wrap another launcher. Resolve only
    # complete child bindings; a reused parent PID must not inherit a child's scope.
    changed = True
    while changed:
        changed = False
        for row in results:
            process = raw[row["pid"]]
            if row["cleanup_versions"] or process.get("name", "").lower() not in ("cmd.exe", "gradle.exe"):
                continue
            if classify_process(process) != "active":
                continue
            children = [child for child in results if raw[child["pid"]].get("parent_pid") == row["pid"]]
            if children and all(child["cleanup_versions"] and
                    process.get("session") is not None and
                    process["session"] == raw[child["pid"]].get("session") and
                    process["created"] <= raw[child["pid"]]["created"] for child in children):
                row["cleanup_versions"] = sorted({v for child in children for v in child["cleanup_versions"]})
                row["cleanup_activity_source"] = "launcher_child"
                changed = True


def inspect_activity(homes=()):
    if os.name != "nt":
        raise OSError("Activity inspection requires Windows")
    process = powershell("snapshot.ps1")
    output, error = process.communicate()
    if process.returncode:
        raise OSError("Could not inspect Windows process state: " + error.strip())
    snapshot = json.loads(output.lstrip("\ufeff"))
    results = []
    for row in snapshot["processes"]:
        command = row.get("command") or ""
        lowered = command.lower()
        log_text, modified, log_path = "", 0, None
        if "org.gradle.launcher.daemon.bootstrap.gradledaemon" in lowered:
            logs = []
            for home in homes:
                for path in (home / "daemon").glob(f"*/daemon-{row['pid']}.out.log"):
                    try:
                        stamp = path.stat().st_mtime
                        tail = daemon_lifecycle(path, row["created"])
                        if stamp >= row["created"]:
                            logs.append((stamp, tail, str(path)))
                    except OSError:
                        pass
            if len(logs) == 1:
                modified, log_text, log_path = logs[0]
        connected = row["pid"] in snapshot["connected_pids"]
        state = classify_process(row, log_text, modified, connected, snapshot["connections_known"])
        if state == "idle" and row.get("session") != snapshot.get("session"):
            state = "ambiguous"
        if state != "unrelated":
            results.append({"pid": row["pid"], "created": row["created"], "name": row["name"],
                            "state": state, "connected": connected, "daemon_log": log_path, **daemon_details(row)})
    attribute_cleanup_activity(snapshot, results)
    return {"safe_to_start": all(p["state"] == "idle" for p in results), "processes": results,
            "connections_known": snapshot["connections_known"],
            "cleanup_identity_known": snapshot.get("cleanup_identity_known", False),
            "scope": "participating_launchers_in_current_windows_session; external launches not prevented"}


class LifecycleObserver:
    def __init__(self, homes):
        self.homes = homes

    def __enter__(self):
        env = {**os.environ, "GRADLE_GATE_WATCH_ROOTS": json.dumps([str(p) for p in self.homes])}
        self.process = powershell("watch.ps1", env=env)
        # No output deadline: readiness is a real watcher subscription transition.
        ready = self.process.stdout.readline().strip()
        if not ready.startswith("ready:"):
            error = self.process.stderr.read()
            self.process.wait()
            self.process.stdout.close(); self.process.stderr.close()
            raise OSError("Lifecycle watcher could not subscribe: " + error)
        self.pids = set(json.loads(ready.split(":", 1)[1]))
        return self

    def wait(self):
        if self.process.stdout.readline().strip() != "changed":
            raise OSError("Lifecycle watcher stopped; build launch blocked")

    def __exit__(self, *args):
        # This is our observer only, never a Gradle/client/Studio process.
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait()
        self.process.stdout.close()
        self.process.stderr.close()


def execute_wrapper(project, profile, log_path):
    wrapper = project / "gradlew.bat"
    if re.search(r'[&|<>^%!\r\n"]', str(wrapper)):
        raise ValueError("Unsafe wrapper path")
    log_path = Path(log_path).resolve()
    if log_path.exists():
        raise ValueError("Log path already exists; refusing to overwrite it")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = subprocess.list2cmdline([str(wrapper), *profile["arguments"]])
    observed, test_profiles, memory_evidence = [], [], []
    with log_path.open("x", encoding="utf-8") as log:
        shell_command = subprocess.list2cmdline([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c"]) + ' "' + command + '"'
        child = subprocess.Popen(shell_command,
                                 cwd=project, env=profile["environment"], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                 creationflags=NO_WINDOW)
        interrupted = False
        def retain_supervision(signum, frame):
            nonlocal interrupted
            interrupted = True
            print("Supervisor interrupted; retaining gate until command completion.", file=sys.stderr, flush=True)
        signals = [signal.SIGINT] + ([signal.SIGBREAK] if hasattr(signal, "SIGBREAK") else [])
        previous_handlers = {s: signal.getsignal(s) for s in signals}
        for s in signals:
            signal.signal(s, retain_supervision)
        try:
            while True:
                line = child.stdout.readline()
                if not line:
                    break
                log.write(line); log.flush()
                print(line, end="", file=sys.stderr, flush=True)
                if line.startswith("GRADLE_GATE_PROFILE_JSON:"):
                    try:
                        observed.append(json.loads(line.split(":", 1)[1]))
                    except ValueError:
                        pass
                if line.startswith("GRADLE_GATE_TEST_PROFILE_JSON:"):
                    try:
                        test_profiles.append(json.loads(line.split(":", 1)[1]))
                    except ValueError:
                        pass
                if re.search(r"OutOfMemoryError|Java heap space|GC overhead limit exceeded|unable to create native thread", line, re.I):
                    memory_evidence.append(line.strip()[:500])
        finally:
            # Output/logging failures must not release ownership over a live build.
            while child.stdout.read(64 * 1024):
                pass
            exit_code = child.wait()
            child.stdout.close()
            for s, handler in previous_handlers.items():
                signal.signal(s, handler)
    worker_verified = bool(observed) and all(p.get("max_workers") == 2 and p.get("parallel") is False for p in observed)
    expected_heap = profile["gradle_jvmargs"].split()[-1].lower()
    expected_bytes = int(expected_heap[4:-1]) * 1024**3
    heap_verified = bool(observed) and all(
        [arg.lower() for arg in p.get("gradle_jvmargs", []) if arg.lower().startswith("-xmx")][-1:] == [expected_heap]
        and 0 < p.get("gradle_max_heap_bytes", 0) <= expected_bytes for p in observed)
    return {"exit_code": exit_code, "log_path": str(log_path), "observed_profile": observed,
            "test_profile_evidence": test_profiles,
            "memory_failure_evidence": memory_evidence[-10:], "supervisor_interrupted": interrupted,
            "gradle_profile_verified": worker_verified and heap_verified,
            "verification_gaps": ["Native/task-specific Kotlin/test overrides require project-specific verification; test markers are configuration-time evidence"] +
                ([] if observed else ["No Gradle profile marker observed; requested profile not verified"])}


def run_build(project, arguments, *, extra_homes=(), log_path=None, retire_daemons="incompatible", **options):
    from .queue import TicketQueue
    from .usage import record_project
    project = Path(project).expanduser().resolve()
    if not (project / "gradlew.bat").is_file():
        raise ValueError("Project must contain gradlew.bat")
    homes = observation_homes(arguments, extra_homes, project)
    profile = make_profile(project, arguments, homes, **options)
    version = wrapper_version(project) if retire_daemons != "none" else None
    retired = []
    if log_path is None:
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        log_path = local / "Tools/gradle-build-gate/logs" / (uuid.uuid4().hex + ".log")
    with TicketQueue() as request, NamedMutex() as mutex:
        ticket = dict(request.ticket)
        try:
            usage_tracking = record_project(project, home=observation_homes(arguments, project=project)[-1])
        except (ValueError, OSError, RuntimeError) as exc:
            # Catalog diagnostics must not expose URLs or replace the build result.
            usage_tracking = {"ok": False, "failure_kind": type(exc).__name__,
                              "warning": "Usage catalog could not be updated; repair it before requesting cleanup proposals"}
            print(json.dumps({"state": "usage_tracking_warning", **usage_tracking}), file=sys.stderr, flush=True)
        while True:
            with LifecycleObserver(homes) as observer:
                inspection = inspect_activity(homes)
                while not inspection["safe_to_start"]:
                    pids = getattr(observer, "pids", None)
                    if pids is not None and any(p["pid"] not in pids for p in inspection["processes"]):
                        # A process appeared during subscription. Re-arm its exit
                        # handle, then inspect again before trusting the snapshot.
                        break
                    print(json.dumps({"state": "waiting_for_existing_build", "activity": inspection}), file=sys.stderr, flush=True)
                    observer.wait()
                    inspection = inspect_activity(homes)
                if inspection["safe_to_start"]:
                    candidates = retirement_candidates(inspection, version, profile.get("gradle_jvmargs", "").split()[-1] if profile.get("gradle_jvmargs") else "", retire_daemons)
                    if candidates:
                        candidate = candidates[0]
                        # Reinspect before each request; new activity goes back through
                        # event-driven waiting. The daemon handles the final race safely.
                        fresh = inspect_activity(homes)
                        if not fresh["safe_to_start"]:
                            continue
                        current = next((p for p in retirement_candidates(fresh, version, profile["gradle_jvmargs"].split()[-1], retire_daemons)
                                        if (p["pid"], p["created"]) == (candidate["pid"], candidate["created"])), None)
                        if current:
                            print(json.dumps({"state": "retiring_idle_daemon", "pid": current["pid"], "reason": current["retirement_reason"]}), file=sys.stderr, flush=True)
                            retired.append(retire_daemon(current))
                        continue
                    result = execute_wrapper(project, profile, log_path)
                    break
    public_profile = {key: value for key, value in profile.items() if key not in ("arguments", "environment")}
    return {"ok": result["exit_code"] == 0, "operation": "run", "project": str(project),
            "gate_acquired": True, "mutex": MUTEX_NAME, "abandoned_mutex_rechecked": mutex.abandoned,
            "queue_ticket": ticket, "queue_ordering": "fifo_registration",
            "usage_tracking": usage_tracking,
            "requested_profile": public_profile, "preflight_activity": inspection,
            "daemon_retirement": {"policy": retire_daemons, "target_version": version, "retired": retired}, **result}
