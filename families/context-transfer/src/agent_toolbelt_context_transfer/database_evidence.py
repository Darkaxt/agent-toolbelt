"""Scoped read-only database preservation; never restores or mutates app state."""

from contextlib import closing
import base64
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from .rollout_io import open_rollout, resolve_rollout


DATABASES = ("state_5.sqlite", "thread_history_1.sqlite", "goals_1.sqlite",
             "queue_1.sqlite", "memories_1.sqlite")


def fork_references(home, ids):
    """Expose known cross-thread lineage that is not represented by spawn edges."""
    result = []
    path = Path(home) / "state_5.sqlite"
    if not path.is_file():
        return result
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        for tid, rollout in conn.execute("SELECT id,rollout_path FROM threads"):
            p = resolve_rollout(rollout)
            if not p.is_file():
                continue
            try:
                with open_rollout(p) as stream:
                    meta = json.loads(stream.readline(65536)).get("payload", {})
                source = meta.get("forked_from_id")
                if source in ids and tid not in ids:
                    result.append({"source_thread_id": source, "dependent_thread_id": tid,
                                   "fork_boundary": meta.get("forked_from_ordinal_exclusive")})
            except (OSError, ValueError):
                if p.name.endswith('.jsonl.zst'):
                    raise
                continue
    return result


def history_ancestors(home, thread_id):
    result, seen = [], {thread_id}
    path = Path(home) / "state_5.sqlite"
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        while True:
            row = conn.execute("SELECT rollout_path FROM threads WHERE id=?", (thread_id,)).fetchone()
            if not row:
                break
            p = resolve_rollout(row[0])
            if not p.is_file():
                break
            try:
                with open_rollout(p) as stream:
                    meta = json.loads(stream.readline(65536)).get("payload", {})
            except (OSError, ValueError):
                if p.name.endswith('.jsonl.zst'):
                    raise
                break
            parent = meta.get("forked_from_id")
            if not parent:
                break
            if parent in seen:
                raise ValueError("Fork history lineage contains a cycle")
            result.append({"thread_id": parent, "dependent_thread_id": thread_id,
                           "fork_boundary": meta.get("forked_from_ordinal_exclusive"),
                           "requires_separate_preservation": True})
            seen.add(parent)
            thread_id = parent
    return result


def selected_tables(conn, ids):
    marks = ",".join("?" for _ in ids)
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        # Table names originate in the schema, not caller-controlled SQL.
        quoted = '"' + table.replace('"', '""') + '"'
        columns = [r[1] for r in conn.execute(f"PRAGMA table_info({quoted})")]
        keys = [key for key in ("thread_id", "source_thread_id", "parent_thread_id", "child_thread_id") if key in columns]
        if table == "threads" and "id" in columns:
            keys.append("id")
        if not keys:
            continue
        predicate = " OR ".join(f'"{key}" IN ({marks})' for key in keys)
        yield table, quoted, columns, predicate, tuple(ids) * len(keys)


def database_inventory(home, ids):
    result = []
    for name in DATABASES:
        path = Path(home) / name
        if not path.exists():
            continue
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.execute("BEGIN")
            tables = []
            for table, quoted, columns, predicate, params in selected_tables(conn, ids):
                count = conn.execute(f"SELECT count(*) FROM {quoted} WHERE {predicate}", params).fetchone()[0]
                tables.append({"table": table, "rows": count})
            result.append({"database": name, "tables": tables})
    return result


def export_database_evidence(home, ids, output):
    """Stream selected rows from a consistent read snapshot per database."""
    output = Path(output)
    counts = []
    with output.open("xb") as target:
        for name in DATABASES:
            path = Path(home) / name
            if not path.exists():
                continue
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
                conn.execute("BEGIN")
                for table, quoted, columns, predicate, params in selected_tables(conn, ids):
                    count = 0
                    for row in conn.execute(f"SELECT * FROM {quoted} WHERE {predicate}", params):
                        values = {key: {"base64": base64.b64encode(value).decode("ascii")} if isinstance(value, bytes) else value
                                  for key, value in zip(columns, row)}
                        packet = {"database": name, "table": table, "row": values}
                        target.write((json.dumps(packet, ensure_ascii=True, sort_keys=True) + "\n").encode())
                        count += 1
                    counts.append({"database": name, "table": table, "rows": count})
        target.flush()
        __import__("os").fsync(target.fileno())
    digest = hashlib.sha256()
    with output.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"archive_path": "context-transfer/database-evidence.jsonl", "sha256": digest.hexdigest(),
            "size": output.stat().st_size, "tables": counts, "thread_ids": list(ids),
            "format": "scoped_database_rows.v1", "live_databases_mutated": False}


def read_archive_evidence(archive, seven_zip, *, thread_id, table=None, pattern=None, limit=10):
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    process = subprocess.Popen([str(seven_zip), "x", "-so", str(archive), "context-transfer/database-evidence.jsonl"],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    matches, total = [], 0
    assert process.stdout is not None
    try:
        for line in process.stdout:
            packet = json.loads(line)
            row = packet["row"]
            if thread_id not in [row.get(key) for key in ("id", "thread_id", "source_thread_id", "parent_thread_id", "child_thread_id")]:
                continue
            if table and packet["table"] != table:
                continue
            if pattern and pattern.casefold() not in line.decode().casefold():
                continue
            total += 1
            if len(matches) < limit:
                matches.append(packet)
    finally:
        process.stdout.close()
        code = process.wait()
    if code:
        raise ValueError(f"7-Zip evidence read failed: exit {code}")
    return {"matches": matches, "total_matches": total, "truncated": total > len(matches),
            "live_databases_mutated": False}
