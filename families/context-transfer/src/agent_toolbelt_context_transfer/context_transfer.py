from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
from typing import Any


TERMINAL_CHILD_STATUSES = frozenset(
    {"closed", "completed", "failed", "cancelled", "canceled"}
)
SAFE_THREAD_METADATA_FIELDS = (
    "created_at",
    "updated_at",
    "source",
    "model_provider",
    "cwd",
    "title",
    "name",
    "sandbox_policy",
    "approval_mode",
    "tokens_used",
    "archived",
    "archived_at",
    "git_sha",
    "git_branch",
    "git_origin_url",
    "cli_version",
    "agent_nickname",
    "agent_role",
)


class ContextTransferError(RuntimeError):
    def __init__(
        self,
        kind: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.details = details or {}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _native_windows_path(value: str | os.PathLike[str]) -> Path:
    raw = os.fspath(value)
    if raw.startswith("\\\\?\\UNC\\"):
        raw = "\\\\" + raw[8:]
    elif raw.startswith("\\\\?\\"):
        raw = raw[4:]
    return Path(raw)


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _is_within(path: Path, root: Path) -> bool:
    candidate = _normalized_path(path)
    boundary = _normalized_path(root)
    try:
        return os.path.commonpath((candidate, boundary)) == boundary
    except ValueError:
        return False


def _is_reparse_or_symlink(path: Path) -> bool:
    if path.is_symlink():
        return True
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    reparse_flag = getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _open_read_only_database(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise ContextTransferError(
            "state_database_missing",
            f"Codex state database was not found: {path}",
        )
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _thread_row(connection: sqlite3.Connection, thread_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM threads WHERE id = ?",
        (thread_id,),
    ).fetchone()


def _collect_tree(
    source_thread_id: str,
    edge_rows: list[sqlite3.Row],
) -> tuple[list[tuple[str, int]], list[dict[str, str]], list[list[str]]]:
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in edge_rows:
        adjacency[str(row["parent_thread_id"])].append(
            (str(row["child_thread_id"]), str(row["status"]))
        )
    for children in adjacency.values():
        children.sort(key=lambda item: item[0])

    order: list[tuple[str, int]] = []
    reachable_edges: list[dict[str, str]] = []
    cycles: list[list[str]] = []
    visited: set[str] = set()

    def visit(thread_id: str, depth: int, stack: list[str]) -> None:
        if thread_id in visited:
            return
        visited.add(thread_id)
        order.append((thread_id, depth))
        next_stack = [*stack, thread_id]
        for child_id, status in adjacency.get(thread_id, []):
            reachable_edges.append(
                {
                    "parent_thread_id": thread_id,
                    "child_thread_id": child_id,
                    "status": status,
                }
            )
            if child_id in next_stack:
                start = next_stack.index(child_id)
                cycles.append([*next_stack[start:], child_id])
                continue
            visit(child_id, depth + 1, next_stack)

    visit(source_thread_id, 0, [])
    return order, reachable_edges, cycles


def _metadata_from_row(row: sqlite3.Row) -> dict[str, Any]:
    available = set(row.keys())
    return {
        field: row[field]
        for field in SAFE_THREAD_METADATA_FIELDS
        if field in available
    }


def _inspect_rollout(path_value: str, allowed_roots: tuple[Path, ...]) -> dict[str, Any]:
    path = _native_windows_path(path_value)
    record: dict[str, Any] = {
        "rollout_path": str(path),
        "file_state": "unknown",
        "size": None,
        "mtime_ns": None,
        "sha256": None,
    }
    if not any(_is_within(path, root) for root in allowed_roots):
        record["file_state"] = "unsafe_path"
        return record
    if not path.exists():
        record["file_state"] = "missing"
        return record
    try:
        if _is_reparse_or_symlink(path) or not path.is_file():
            record["file_state"] = "unsafe_path"
            return record
        stat_result = path.stat()
        record.update(
            {
                "file_state": "readable",
                "size": stat_result.st_size,
                "mtime_ns": stat_result.st_mtime_ns,
                "sha256": _sha256_file(path),
            }
        )
    except OSError as exc:
        record["file_state"] = "unreadable"
        record["file_error"] = f"{type(exc).__name__}: {exc}"
    return record


def inventory_thread_tree(
    *,
    source_thread_id: str,
    destination_thread_id: str | None,
    codex_home: str | os.PathLike[str],
    archive_root: str | os.PathLike[str],
) -> dict[str, Any]:
    source_thread_id = source_thread_id.strip()
    destination_thread_id = (destination_thread_id or "").strip() or None
    if destination_thread_id == source_thread_id:
        raise ContextTransferError(
            "source_is_destination",
            "The destination task cannot retire itself.",
        )

    codex_home_path = _native_windows_path(codex_home)
    database_path = codex_home_path / "state_5.sqlite"
    allowed_roots = (
        codex_home_path / "sessions",
        codex_home_path / "archived_sessions",
    )

    with closing(_open_read_only_database(database_path)) as connection:
        source_row = _thread_row(connection, source_thread_id)
        if source_row is None:
            raise ContextTransferError(
                "source_thread_not_found",
                f"Source thread was not found: {source_thread_id}",
            )
        edge_rows = connection.execute(
            "SELECT parent_thread_id, child_thread_id, status "
            "FROM thread_spawn_edges ORDER BY parent_thread_id, child_thread_id"
        ).fetchall()
        order, edges, cycles = _collect_tree(source_thread_id, edge_rows)

        missing_thread_ids: list[str] = []
        records: list[dict[str, Any]] = []
        for thread_id, depth in order:
            row = _thread_row(connection, thread_id)
            if row is None:
                missing_thread_ids.append(thread_id)
                continue
            rollout = _inspect_rollout(str(row["rollout_path"]), allowed_roots)
            records.append(
                {
                    "thread_id": thread_id,
                    "depth": depth,
                    **rollout,
                    "metadata": _metadata_from_row(row),
                }
            )

    state_counts = Counter(item["file_state"] for item in records)
    status_counts = Counter(edge["status"] for edge in edges)
    path_counts = Counter(
        _normalized_path(_native_windows_path(str(item["rollout_path"])))
        for item in records
    )
    duplicate_paths = sorted(path for path, count in path_counts.items() if count > 1)
    non_terminal = sorted(
        {
            edge["child_thread_id"]
            for edge in edges
            if edge["status"].casefold() not in TERMINAL_CHILD_STATUSES
        }
    )

    blockers: list[str] = []
    if cycles:
        blockers.append("spawn_cycle")
    if missing_thread_ids:
        blockers.append("missing_thread_rows")
    if non_terminal:
        blockers.append("non_terminal_children")
    if state_counts["missing"]:
        blockers.append("missing_rollouts")
    if state_counts["unreadable"]:
        blockers.append("unreadable_rollouts")
    if state_counts["unsafe_path"]:
        blockers.append("unsafe_rollout_paths")
    if duplicate_paths:
        blockers.append("duplicate_rollout_paths")

    return {
        "schema": "agent_toolbelt_context_transfer.inventory.v1",
        "source_thread_id": source_thread_id,
        "destination_thread_id": destination_thread_id,
        "codex_home": str(codex_home_path),
        "archive_root": str(_native_windows_path(archive_root)),
        "thread_count": len(order),
        "resolved_thread_count": len(records),
        "edge_count": len(edges),
        "total_rollout_bytes": sum(
            int(item["size"])
            for item in records
            if item["file_state"] == "readable"
        ),
        "terminal_status_counts": dict(sorted(status_counts.items())),
        "file_state_counts": dict(sorted(state_counts.items())),
        "threads": records,
        "edges": edges,
        "missing_thread_ids": sorted(missing_thread_ids),
        "non_terminal_child_ids": non_terminal,
        "duplicate_rollout_paths": duplicate_paths,
        "cycle_paths": cycles,
        "blockers": blockers,
        "retirement_ready": not blockers,
        "database_access": "read_only",
        "mutations_performed": False,
    }
