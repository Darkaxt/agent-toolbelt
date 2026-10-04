"""Known-project usage metadata, not an upgrade or deletion authority."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from .gate import NamedMutex, inspect_activity, observation_homes, wrapper_version


VERSION = re.compile(r"\d+\.\d+(?:[.a-zA-Z0-9+-]*)\Z")


def catalog_root(root=None):
    return Path(root or Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Tools/gradle-build-gate").resolve()


def path_key(path):
    return os.path.normcase(str(Path(path).expanduser().resolve()))


def catalog_mutex_name(root=None):
    digest = hashlib.sha256(path_key(catalog_root(root)).encode()).hexdigest()[:24]
    return "Global\\Darka.AndroidGradleUsageCatalog." + digest


def valid_version(version):
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError("Invalid Gradle version identifier")
    return version


def load_catalog(root=None):
    path = catalog_root(root) / "usage.json"
    if not path.exists():
        return {"schema": 1, "projects": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("projects"), dict):
        raise ValueError("Unsupported or corrupt Gradle usage catalog; not reset automatically")
    for key, entry in data["projects"].items():
        if not isinstance(entry, dict) or not isinstance(entry.get("project"), str):
            raise ValueError("Invalid project catalog entry")
        if not Path(entry["project"]).is_absolute() or path_key(entry["project"]) != key:
            raise ValueError("Invalid project identity in catalog")
        if entry.get("wrapper_version") is not None:
            valid_version(entry["wrapper_version"])
        if not isinstance(entry.get("keep_versions"), list):
            raise ValueError("Invalid version reservations")
        for version in entry["keep_versions"]:
            valid_version(version)
        home = entry.get("gradle_home")
        if home is not None and (not isinstance(home, str) or not Path(home).is_absolute()):
            raise ValueError("Invalid Gradle home in catalog")
    return data


def save_catalog(root, data):
    root.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, suffix=".pending", delete=False) as stream:
            name = stream.name
            json.dump(data, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, root / "usage.json")
    finally:
        if name and Path(name).exists():
            Path(name).unlink()


def read_version(project):
    try:
        return valid_version(wrapper_version(project))
    except (ValueError, OSError):
        return None


def record_project(project, *, root=None, keep_versions=None, home=None):
    project = Path(project).expanduser().resolve()
    if not (project / "gradlew.bat").is_file():
        raise ValueError("Registered project must contain gradlew.bat")
    reservations = None if keep_versions is None else sorted(set(valid_version(v) for v in keep_versions))
    root = catalog_root(root)
    with NamedMutex(catalog_mutex_name(root)):
        data = load_catalog(root)
        previous = data["projects"].get(path_key(project), {})
        entry = {"project": str(project), "wrapper_version": read_version(project),
                 "keep_versions": previous.get("keep_versions", []) if reservations is None else reservations,
                 "gradle_home": str(Path(home).expanduser().resolve()) if home is not None else previous.get("gradle_home"),
                 "last_requested_at": datetime.now(timezone.utc).isoformat()}
        data["projects"][path_key(project)] = entry
        save_catalog(root, data)
    return {"ok": True, **entry, "warnings": [] if entry["wrapper_version"] else ["Wrapper version unknown; cleanup proposals will be protected"]}


def unregister_project(project, *, root=None):
    root = catalog_root(root)
    with NamedMutex(catalog_mutex_name(root)):
        data = load_catalog(root)
        removed = data["projects"].pop(path_key(project), None) is not None
        save_catalog(root, data)
    return {"ok": True, "removed": removed, "project": path_key(project), "project_files_changed": False}


def is_link(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def measure_tree(path):
    """Metadata only; never follow reparse points or count linked bytes as reclaimable."""
    result = {"bytes": 0, "file_count": 0, "linked_content": False, "errors": 0}
    pending = [path]
    while pending:
        current = pending.pop()
        try:
            info = current.lstat()
            if is_link(info):
                result["linked_content"] = True
            elif stat.S_ISDIR(info.st_mode):
                with os.scandir(current) as entries:
                    pending.extend(Path(e.path) for e in entries)
            elif stat.S_ISREG(info.st_mode):
                result["bytes"] += info.st_size
                result["file_count"] += 1
                result["linked_content"] |= info.st_nlink > 1
            else:
                result["errors"] += 1
        except OSError:
            result["errors"] += 1
    return result


def inventory(*, root=None, projects=(), extra_homes=()):
    catalog = load_catalog(root)
    entries = dict(catalog["projects"])
    for project in projects:
        entries.setdefault(path_key(project), {"project": path_key(project), "wrapper_version": None,
                                             "keep_versions": [], "gradle_home": None})
    references, protected, uncertain = [], set(), not bool(entries)
    for entry in entries.values():
        path = Path(entry["project"])
        version = read_version(path) if (path / "gradlew.bat").is_file() else None
        uncertain |= version is None
        protected.update(entry["keep_versions"])
        if version:
            protected.add(version)
        elif entry.get("wrapper_version"):
            protected.add(entry["wrapper_version"])
        references.append({**entry, "current_wrapper_version": version,
                           "reference_status": "readable" if version else "unknown_or_unavailable"})
    homes = observation_homes(extra=[*extra_homes, *(e["gradle_home"] for e in entries.values() if e.get("gradle_home"))])
    activity = inspect_activity(homes)
    activity_clear = activity.get("safe_to_start") is True and activity.get("connections_known") is True
    live_versions = {p["version"] for p in activity.get("processes", []) if p.get("version")}
    activity_clear &= all(p.get("state") == "idle" and p.get("version") for p in activity.get("processes", []))
    artifacts, incomplete = [], False
    for home in homes:
        for relative, kind in (("wrapper/dists", "distribution"), ("caches", "version_cache")):
            parent = home / relative
            try:
                # Guard ancestors too: a linked cache parent must not be traversed.
                chain = [home, parent] + ([home / "wrapper"] if kind == "distribution" else [])
                if any(p.exists() and is_link(p.lstat()) for p in chain):
                    incomplete = True
                    continue
                if not parent.exists():
                    continue
                with os.scandir(parent) as children:
                    paths = [Path(e.path) for e in children]
                for path in paths:
                    name = path.name
                    match = re.fullmatch(r"gradle-(\d+\.\d+[.a-zA-Z0-9+-]*)-(bin|all)", name) if kind == "distribution" else VERSION.fullmatch(name)
                    if not match:
                        continue
                    info = path.lstat()
                    if not stat.S_ISDIR(info.st_mode) and not is_link(info):
                        continue
                    version = match.group(1) if kind == "distribution" else name
                    metrics = measure_tree(path)
                    reasons = []
                    if version in protected:
                        reasons.append("project_reference_or_reservation")
                    if uncertain:
                        reasons.append("incomplete_known_project_references")
                    if not activity_clear:
                        reasons.append("build_activity_not_clear")
                    if version in live_versions:
                        reasons.append("live_daemon_version")
                    if metrics["linked_content"]:
                        reasons.append("linked_or_reparse_content")
                    if metrics["errors"]:
                        reasons.append("incomplete_inventory")
                        incomplete = True
                    artifacts.append({"path": str(path), "kind": kind, "version": version,
                                      **metrics, "protected_reasons": reasons, "eligible_for_review": not reasons})
            except OSError:
                incomplete = True
    if incomplete:
        for artifact in artifacts:
            if "incomplete_inventory" not in artifact["protected_reasons"]:
                artifact["protected_reasons"].append("incomplete_inventory")
            artifact["eligible_for_review"] = False
    stable = {a["version"] for a in artifacts if a["kind"] == "distribution" and re.fullmatch(r"\d+(?:\.\d+)+", a["version"]) and not a["errors"] and not a["linked_content"]}
    candidates = [{"version": v, "compatibility_verified": False} for v in sorted(stable, key=lambda v: tuple(map(int, v.split("."))), reverse=True)]
    return {"ok": True, "operation": "inventory", "read_only": True, "deletes_files": False,
            "projects": references, "homes": list(map(str, homes)), "artifacts": artifacts,
            "activity": activity, "reference_uncertainty": uncertain, "inventory_incomplete": incomplete,
            "baseline_candidates": candidates, "coverage": "known_projects_only",
            "warnings": ["Not referenced by known projects is not proof of global non-use. Register relevant projects and rollback/offline reservations before review.",
                         "Baseline candidates are installed stable versions, not verified AGP/Kotlin/plugin/JDK compatibility."]}


def cleanup_plan(**options):
    result = inventory(**options)
    proposals = [a for a in result["artifacts"] if a["eligible_for_review"]]
    return {**result, "operation": "cleanup-plan", "proposals": proposals,
            "estimated_bytes": sum(a["bytes"] for a in proposals), "transactional_cleanup_required": True,
            "deletion_authorized": False,
            "application_requirement": "Review exact roots; recheck references and activity under the shared build gate before separate transactional cleanup. This report is not a deletion ticket."}
