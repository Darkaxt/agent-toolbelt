"""Reviewed exact conversation deletion; Codex mutations use its app-server API."""

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from uuid import UUID


class CleanupError(RuntimeError):
    pass


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(part)
    return result.hexdigest()


def exact_id(value):
    if str(UUID(value)) != value:
        raise CleanupError("Use a complete canonical UUID, not a shortened ID or title")
    return value


def readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=0)


def filesystem():
    """Reuse the installed exact-handle deletion primitive, not a shell sweep."""
    active = Path(os.environ.get("LOCALAPPDATA", "")) / "Tools/transactional-cleanup/active.json"
    if not active.is_file():
        raise CleanupError("Installed transactional-cleanup filesystem runtime is required")
    source = Path(json.loads(active.read_text(encoding="utf-8"))["source"])
    if not (source / "agent_toolbelt_transactional_cleanup/filesystem.py").is_file():
        raise CleanupError("Installed exact-handle deletion runtime is incomplete")
    sys.path.insert(0, str(source))
    from agent_toolbelt_transactional_cleanup import filesystem as fs
    return fs


def table_rows(home, thread_id):
    """Inventory targeted app data without printing bodies or altering databases."""
    result = []
    for database in ("state_5.sqlite", "thread_history_1.sqlite", "goals_1.sqlite", "queue_1.sqlite", "memories_1.sqlite"):
        path = Path(home) / database
        if not path.exists():
            continue
        with closing(readonly(path)) as conn:
            conn.execute("BEGIN")
            for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
                quoted = '"' + table.replace('"', '""') + '"'
                columns = [r[1] for r in conn.execute(f"PRAGMA table_info({quoted})")]
                keys = [k for k in ("thread_id", "source_thread_id", "parent_thread_id", "child_thread_id") if k in columns]
                if table == "threads" and "id" in columns:
                    keys.append("id")
                if not keys:
                    continue
                where = " OR ".join(f'"{k}"=?' for k in keys)
                hashes = []
                for row in conn.execute(f"SELECT * FROM {quoted} WHERE {where}", [thread_id] * len(keys)):
                    raw = json.dumps(row, default=lambda v: {"hex": v.hex()}, sort_keys=True).encode()
                    hashes.append(hashlib.sha256(raw).hexdigest())
                result.append({"database": database, "table": table, "rows": len(hashes),
                               "rows_sha256": hashlib.sha256("".join(sorted(hashes)).encode()).hexdigest()})
    return result


def safe_file(path, home):
    path, home = Path(path).absolute(), Path(home).resolve()
    if not path.is_relative_to(home):
        raise CleanupError("Conversation path escaped its application home")
    for item in (path, *path.parents):
        if item == home:
            break
        if item.is_symlink() or getattr(item.lstat(), "st_file_attributes", 0) & 0x400:
            raise CleanupError("Reparse/symlink conversation paths are not supported")
    stat = path.stat()
    return {"path": str(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "sha256": digest(path), **(filesystem().identity(path) if os.name == "nt" else {})}


def codex_snapshot(home, thread_id):
    with closing(readonly(Path(home) / "state_5.sqlite")) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
        if row is None:
            raise CleanupError("Codex thread not found")
        children = [r[0] for r in conn.execute("SELECT child_thread_id FROM thread_spawn_edges WHERE parent_thread_id=? ORDER BY child_thread_id", (thread_id,))]
        paths = {Path(row["rollout_path"])}
        for name in ("sessions", "archived_sessions"):
            root = Path(home) / name
            if root.exists():
                for path in root.rglob(f"*{thread_id}*.jsonl"):
                    with path.open("rb") as stream:
                        header = json.loads(stream.readline())
                    if header.get("type") == "session_meta" and header.get("payload", {}).get("id") == thread_id:
                        paths.add(path)
        return {"id": thread_id, "name": row["name"] if "name" in row.keys() else row["title"],
                "archived": bool(row["archived"]), "children": children,
                "fork_dependents": fork_dependents(home, thread_id),
                "files": [safe_file(p, home) for p in sorted(paths) if p.exists()],
                "database_rows": table_rows(home, thread_id)}


def fork_dependents(home, thread_id):
    result = []
    with closing(readonly(Path(home) / "state_5.sqlite")) as conn:
        for tid, path in conn.execute("SELECT id,rollout_path FROM threads WHERE id!=?", (thread_id,)):
            p = Path(path)
            if not p.is_file() or p.suffix == ".zst":
                continue
            try:
                with p.open("rb") as stream:
                    meta = json.loads(stream.readline(65536)).get("payload", {})
                if meta.get("forked_from_id") == thread_id:
                    result.append({"thread_id": tid, "source_thread_id": thread_id,
                                   "fork_boundary": meta.get("forked_from_ordinal_exclusive")})
            except (OSError, ValueError):
                continue
    return sorted(result, key=lambda r: r["thread_id"])


def claude_snapshot(home, thread_id):
    home = Path(home)
    projects = list((home / "projects").glob(f"*/{thread_id}.jsonl"))
    if len(projects) != 1:
        raise CleanupError("Claude session must resolve to one exact project history")
    main = projects[0]
    paths = {main}
    owned_roots = [main.with_suffix(""), home / "file-history" / thread_id,
                   home / "session-env" / thread_id, home / "tasks" / thread_id]
    for root in owned_roots:
        if root.exists():
            if root.is_symlink() or getattr(root.lstat(), "st_file_attributes", 0) & 0x400:
                raise CleanupError("Linked session directory is not supported")
            paths.update(p for p in root.rglob("*") if p.is_file())
    for p in (home / "debug" / f"{thread_id}.txt", home / f"security_warnings_state_{thread_id}.json"):
        if p.is_file():
            paths.add(p)
    directories = []
    for root in owned_roots:
        if root.exists():
            directories.extend({"path": str(p), **filesystem().identity(p)}
                               for p in [root, *root.rglob("*")] if p.is_dir())
    return {"id": thread_id, "files": [safe_file(p, home) for p in sorted(paths)],
            "directories": sorted(directories, key=lambda p: p["path"]),
            "database_rows": [], "shared_indexes": [str(home / "history.jsonl"), str(main.parent / "sessions-index.json")]}


def live_claude_ids(home):
    ids = set()
    if os.name != "nt":
        raise CleanupError("Live Claude registration verification is Windows-only")
    # Process identity matters; no elapsed-age or missing-registration inference.
    cmd = "Get-CimInstance Win32_Process | Select-Object Name,ProcessId,CommandLine | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True, check=True)
    processes = json.loads(result.stdout)
    processes = processes if isinstance(processes, list) else [processes]
    by_pid = {r["ProcessId"]: r.get("CommandLine") for r in processes}
    for path in (Path(home) / "sessions").glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("pid") in by_pid:
            ids.add(record.get("sessionId"))
    # Explicit command references catch forks that still read an older history.
    import re
    for process in processes:
        command = process.get("CommandLine")
        name = (process.get("Name") or "").casefold()
        is_claude = name == "claude.exe" or (name == "node.exe" and command and "@anthropic-ai" in command.casefold() and "claude-code" in command.casefold())
        if is_claude and command:
            ids.update(re.findall(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", command))
    return sorted(value for value in ids if value)


class CodexRPC:
    def __init__(self, executable, home):
        env = os.environ.copy()
        env["CODEX_HOME"] = str(Path(home).resolve())
        self.process = subprocess.Popen([str(executable), "app-server", "--listen", "stdio://"],
                                        env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        self.counter = 0
        try:
            self.request("initialize", {"clientInfo": {"name": "thread_cleanup", "version": "0.1.0"},
                                        "capabilities": {"experimentalApi": True, "explicitGatewayOauth": True}})
            self.process.stdin.write(json.dumps({"method": "initialized"}) + "\n")
            self.process.stdin.flush()
        except BaseException:
            self.close()
            raise

    def request(self, method, params):
        self.counter += 1
        self.process.stdin.write(json.dumps({"id": self.counter, "method": method, "params": params}) + "\n")
        self.process.stdin.flush()
        for line in self.process.stdout:
            packet = json.loads(line)
            if packet.get("id") == self.counter and ("result" in packet or "error" in packet):
                if "error" in packet:
                    raise CleanupError(f"Codex {method} rejected: {packet['error'].get('message', 'RPC error')}")
                return packet["result"]
            if "id" in packet and "method" in packet:
                raise CleanupError("Unexpected app-server approval/request; no implicit approval is permitted")
        raise CleanupError("Codex app-server closed before returning a result")

    def close(self):
        self.process.stdin.close()
        self.process.stdout.close()
        self.process.wait()


def plan(system, home, thread_id, protected=()):
    exact_id(thread_id)
    if thread_id in set(protected) | {os.environ.get("CODEX_THREAD_ID"), os.environ.get("CLAUDE_SESSION_ID")}:
        raise CleanupError("This session is protected/current")
    snapshot = codex_snapshot(home, thread_id) if system == "codex" else claude_snapshot(home, thread_id)
    return {"schema": "thread_cleanup.plan.v1", "system": system, "home": str(Path(home).resolve()),
            "protected_ids": sorted(protected), "snapshot": snapshot,
            "permanent_deletion": True, "authority_required": "explicit exact conversation retirement"}


def delete_codex(packet, executable, activity):
    if packet.get("schema") != "thread_cleanup.plan.v1" or packet["system"] != "codex":
        raise CleanupError("Expected a reviewed Codex deletion plan")
    tid, home = packet["snapshot"]["id"], Path(packet["home"])
    exact_id(tid)
    if tid in set(packet["protected_ids"]) | {os.environ.get("CODEX_THREAD_ID")}:
        raise CleanupError("Protected/current thread")
    if activity.get("thread_id") != tid or activity.get("source") != "codex_task_api" or activity.get("status") not in ("idle", "notLoaded", "completed", "failed", "cancelled", "closed"):
        raise CleanupError("Fresh owning-app inactive status evidence is required")
    if packet["snapshot"] != codex_snapshot(home, tid):
        raise CleanupError("Selected history changed after review; inspect a new plan")
    if packet["snapshot"]["children"]:
        raise CleanupError("Delete verified inactive children first, then review this parent again")
    if packet["snapshot"].get("fork_dependents"):
        raise CleanupError("Surviving forks still reference this history: " + ", ".join(r["thread_id"] for r in packet["snapshot"]["fork_dependents"]))
    rpc = CodexRPC(executable, home)
    try:
        rpc.request("thread/delete", {"threadId": tid})
    finally:
        rpc.close()
    orphan_revisions = prune_orphan_queue_revision(home, tid)
    recall_cache = purge_recall_cache(home, tid)
    rows = [r for r in table_rows(home, tid) if r["rows"]]
    rollout_cleanup = []
    if not rows:
        fs = filesystem()
        for member in packet["snapshot"]["files"]:
            if Path(member["path"]).exists():
                target = Path(member["path"]).absolute()
                if not any(target.is_relative_to(home / root) for root in ("sessions", "archived_sessions")):
                    raise CleanupError("Reviewed residual is outside exact rollout roots")
                outcome, reclaimed = fs.delete_exact(member | {"content_sha256": member["sha256"]})
                rollout_cleanup.append({"path": member["path"], "outcome": outcome, "deleted_bytes": reclaimed})
    residual_files = [f["path"] for f in packet["snapshot"]["files"] if Path(f["path"]).exists()]
    return {"thread_id": tid, "application_delete_completed": True, "database_residuals": rows,
            "file_residuals": residual_files, "complete": not rows and not residual_files and recall_cache.get("ok", False),
            "recall_cache": recall_cache,
            "earlier_rollout_cleanup": rollout_cleanup,
            "database_compacted": False, "application_history_sql_mutated": False,
            "orphan_queue_revision_rows_deleted": orphan_revisions,
            "direct_sql_mutation": bool(orphan_revisions)}


def purge_recall_cache(home, tid):
    if not (Path(home) / "cache/codex-thread-recall/index.sqlite").exists():
        return {"ok": True, "cache_exists": False}
    wrapper = Path(home) / "skills/codex-thread-recall/scripts/invoke_codex_thread_recall.py"
    if not wrapper.is_file():
        return {"ok": False, "failure_kind": "installed_recall_helper_missing"}
    result = subprocess.run([sys.executable, "-B", str(wrapper), "--codex-home", str(home),
                             "--thread-id", tid, "purge-thread-cache", "--confirm-thread-id", tid],
                            capture_output=True, text=True, encoding="utf-8")
    try:
        output = json.loads(result.stdout)
    except ValueError:
        return {"ok": False, "failure_kind": "recall_purge_invalid_response"}
    return output


def prune_orphan_queue_revision(home, tid):
    """Known app deletion omission: remove only content-free orphan queue revisions."""
    path = Path(home) / "queue_1.sqlite"
    if not path.exists():
        return 0
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=0)) as queue:
        queue.execute("BEGIN IMMEDIATE")
        columns = [(r[1], r[2]) for r in queue.execute("PRAGMA table_info(queued_thread_revisions)")]
        if columns != [("revision", "INTEGER"), ("thread_id", "TEXT")]:
            raise CleanupError("Unknown queue revision schema; no orphan SQL cleanup performed")
        with closing(readonly(Path(home) / "state_5.sqlite")) as state:
            if state.execute("SELECT 1 FROM threads WHERE id=?", (tid,)).fetchone():
                raise CleanupError("Thread still exists; orphan revision removal is forbidden")
        if queue.execute("SELECT 1 FROM queued_items WHERE thread_id=?", (tid,)).fetchone():
            raise CleanupError("Queued content remains; no orphan revision removal is allowed")
        count = queue.execute("DELETE FROM queued_thread_revisions WHERE thread_id=?", (tid,)).rowcount
        queue.commit()
        return count


def prune_index(path, tid):
    """Exclude concurrent appenders while editing only matching session rows."""
    if not path.exists():
        return 0
    import ctypes
    import msvcrt
    fs = filesystem()
    fs.check_chain(path)
    opened = fs.kernel.CreateFileW(str(path), 0xC0000000, 0, None, 3, 0x00200000, None)
    if opened == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    # fd owns the handle after successful transfer.
    fd = msvcrt.open_osfhandle(opened, os.O_RDWR | os.O_BINARY)
    with os.fdopen(fd, "r+b") as stream:
        original = stream.read()
        if path.name == "history.jsonl":
            lines = original.splitlines(keepends=True)
            records = [json.loads(line) for line in lines if line.strip()]
            if len(records) != len(lines):
                raise CleanupError("Unexpected blank/shared history format; index preserved")
            kept = [line for line, record in zip(lines, records) if record.get("sessionId") != tid]
            updated = b"".join(kept)
            removed = len(lines) - len(kept)
        else:
            data = json.loads(original)
            if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
                raise CleanupError("Unsupported Claude session-index format; preserved")
            old = data["entries"]
            data["entries"] = [r for r in old if r.get("sessionId") != tid]
            removed = len(old) - len(data["entries"])
            updated = (json.dumps(data, indent=2) + "\n").encode()
        if removed:
            try:
                stream.seek(0)
                stream.write(updated)
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException:
                stream.seek(0)
                stream.write(original)
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
                raise
        return removed


def delete_claude(packet, resume=False):
    if packet.get("schema") != "thread_cleanup.plan.v1" or packet["system"] != "claude":
        raise CleanupError("Expected a reviewed Claude deletion plan")
    tid, home = packet["snapshot"]["id"], Path(packet["home"])
    if tid in set(packet["protected_ids"]) | {os.environ.get("CLAUDE_SESSION_ID")}:
        raise CleanupError("Protected/current Claude session")
    if tid in live_claude_ids(home):
        raise CleanupError("Claude session has a live registration or command reference")
    if not resume and packet["snapshot"] != claude_snapshot(home, tid):
        raise CleanupError("Session artifacts changed after review; create a new plan")
    if resume:
        mains = [Path(r["path"]) for r in packet["snapshot"]["files"] if Path(r["path"]).name == tid + ".jsonl" and Path(r["path"]).parent.parent == home / "projects"]
        if len(mains) != 1:
            raise CleanupError("Original plan does not bind an exact Claude project session")
        roots = (mains[0].with_suffix(""), home / "file-history" / tid, home / "session-env" / tid, home / "tasks" / tid)
        exact = (mains[0], home / "debug" / (tid + ".txt"), home / ("security_warnings_state_" + tid + ".json"))
        for member in packet["snapshot"]["files"] + packet["snapshot"]["directories"]:
            path = Path(member["path"])
            if path not in exact and not any(path == root or path.is_relative_to(root) for root in roots):
                raise CleanupError("Resume plan includes an out-of-scope artifact")
    fs = filesystem()
    results = []
    # Prune indexes first: a sharing violation leaves histories intact.
    indexes = [{"path": path, "removed_entries": prune_index(Path(path), tid)}
               for path in packet["snapshot"]["shared_indexes"]]
    for member in packet["snapshot"]["files"]:
        outcome, reclaimed = fs.delete_exact(member | {"content_sha256": member["sha256"],
                                                     "allow_hardlinks": member.get("links", 1) > 1})
        results.append({"path": member["path"], "outcome": outcome, "deleted_bytes": reclaimed})
    for member in sorted(packet["snapshot"]["directories"], key=lambda r: len(r["path"]), reverse=True):
        outcome, reclaimed = fs.delete_exact(member)
        results.append({"path": member["path"], "outcome": outcome, "deleted_bytes": reclaimed})
    return {"thread_id": tid, "complete": all(r["outcome"] in ("deleted", "already_missing") for r in results),
            "members": results, "indexes": indexes, "direct_sql_mutation": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("plan")
    inspect.add_argument("--system", choices=("codex", "claude"), required=True)
    inspect.add_argument("--home", required=True)
    inspect.add_argument("--thread-id", required=True)
    inspect.add_argument("--protect-id", action="append", default=[])
    inspect.add_argument("--output", required=True)
    apply = commands.add_parser("delete-codex")
    apply.add_argument("--plan", required=True)
    apply.add_argument("--plan-sha256", required=True)
    apply.add_argument("--activity-evidence", required=True)
    apply.add_argument("--codex-executable", required=True)
    apply.add_argument("--confirm-thread-id", required=True)
    claude = commands.add_parser("delete-claude")
    claude.add_argument("--plan", required=True)
    claude.add_argument("--plan-sha256", required=True)
    claude.add_argument("--confirm-thread-id", required=True)
    claude.add_argument("--resume", action="store_true", help="Retry only original reviewed residual names; new files survive")
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = plan(args.system, args.home, args.thread_id, args.protect_id)
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, indent=2)
            result = {"plan": str(output), "plan_sha256": digest(output), "thread_id": args.thread_id,
                      "files": len(result["snapshot"]["files"]), "children": result["snapshot"].get("children", [])}
        else:
            if digest(args.plan) != args.plan_sha256:
                raise CleanupError("Reviewed plan digest mismatch")
            packet = json.loads(Path(args.plan).read_text(encoding="utf-8"))
            if packet["snapshot"]["id"] != args.confirm_thread_id:
                raise CleanupError("Exact confirmation ID mismatch")
            if args.command == "delete-codex":
                evidence = json.loads(Path(args.activity_evidence).read_text(encoding="utf-8"))
                if evidence.get("plan_sha256") != args.plan_sha256:
                    raise CleanupError("Activity evidence is not bound to this reviewed plan")
                result = delete_codex(packet, args.codex_executable, evidence)
            else:
                result = delete_claude(packet, resume=args.resume)
        print(json.dumps({"ok": result.get("complete", True), "result": result}, indent=2))
        return 0 if result.get("complete", True) else 1
    except (CleanupError, ValueError, KeyError, OSError, sqlite3.Error, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "failure_kind": "thread_cleanup_blocked", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
