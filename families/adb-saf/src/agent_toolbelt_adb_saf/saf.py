"""Android documents-provider (Storage Access Framework) access over ADB.

Reads use the platform `content` command as the ADB shell user. Mutations use
an on-device client (assets/saf-client.dex, run through app_process) because
`content call` cannot pass the Uri extras DocumentsContract operations need.
Every mutation is a reviewed plan applied once: apply re-verifies the device,
source and target state recorded in the plan, backs up content it overwrites or
deletes, and verifies the result by hash.
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
import secrets
import time
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .device import Device, SafError, shell_quote

DOC_COLUMNS = ["document_id", "_display_name", "mime_type", "_size", "last_modified", "flags"]
ROOT_COLUMNS = ["root_id", "document_id", "title", "flags", "available_bytes"]
DIRECTORY_MIME = "vnd.android.document/directory"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
PLAN_SCHEMA = 1

DOCUMENT_FLAGS = {
    0x1: "thumbnail", 0x2: "write", 0x4: "delete", 0x8: "dir_create", 0x10: "dir_grid",
    0x20: "dir_last_modified", 0x40: "rename", 0x80: "copy", 0x100: "move", 0x200: "virtual",
    0x400: "remove", 0x800: "settings", 0x1000: "web_linkable", 0x2000: "partial",
    0x4000: "metadata", 0x8000: "dir_blocks_tree",
}
ROW_START = re.compile(r"^Row: (\d+) ")


# ---------------------------------------------------------------- addressing

def parse_target(target: str) -> tuple[str, str]:
    """`AUTHORITY:DOCUMENT_ID`; the document ID is everything after the first colon."""
    authority, sep, document_id = target.partition(":")
    if not sep or not authority or not document_id:
        raise SafError("invalid_target", f"Target must be AUTHORITY:DOCUMENT_ID, got {target!r}.")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", authority):
        raise SafError("invalid_target", f"Invalid provider authority {authority!r}.")
    return authority, document_id


def encode_id(document_id: str) -> str:
    # Stricter than Uri.encode; providers decode path segments, so over-encoding
    # is harmless and keeps shell metacharacters out of the URI.
    return quote(document_id, safe="-_.~")


def root_uri(authority: str) -> str:
    return f"content://{authority}/root"


def document_uri(authority: str, document_id: str) -> str:
    return f"content://{authority}/document/{encode_id(document_id)}"


def children_uri(authority: str, document_id: str) -> str:
    return document_uri(authority, document_id) + "/children"


def decode_flags(flags: Any) -> list[str]:
    try:
        value = int(flags)
    except (TypeError, ValueError):
        return []
    return [name for bit, name in DOCUMENT_FLAGS.items() if value & bit]


# ---------------------------------------------------------------- content output

def classify_failure(text: str) -> SafError | None:
    lowered = text.lower()
    if "error while accessing provider" not in lowered and "exception" not in lowered and "[error]" not in lowered:
        return None
    first = next((line.strip() for line in text.splitlines()
                  if "Exception" in line or line.startswith("[ERROR]")), text.strip()[:300])
    if "SecurityException" in text or "Permission Denial" in text:
        kind = "permission_denied"
    elif "FileNotFoundException" in text:
        kind = "not_found"
    elif "Unknown authority" in text or "Could not find provider" in text or "provider not found" in lowered:
        kind = "provider_not_found"
    elif "UnsupportedOperationException" in text:
        kind = "unsupported"
    else:
        kind = "provider_error"
    return SafError(kind, first[:500])


def split_rows(text: str) -> list[str]:
    rows: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        match = ROW_START.match(line)
        if match:
            if int(match.group(1)) != len(rows):
                raise SafError("parse_error", f"Unexpected row number in content output: {line[:80]!r}")
            rows.append(line[match.end():])
        elif rows and line:
            rows[-1] += "\n" + line
    return rows


def parse_row(body: str, columns: list[str]) -> dict[str, Any] | None:
    """Split one row by the known projection order; None when a value is ambiguous."""
    if not body.startswith(columns[0] + "="):
        return None
    values: dict[str, Any] = {}
    rest = body[len(columns[0]) + 1:]
    for index, column in enumerate(columns):
        if index + 1 < len(columns):
            separator = ", " + columns[index + 1] + "="
            if rest.count(separator) != 1:
                return None
            value, rest = rest.split(separator, 1)
        else:
            value = rest
        values[column] = None if value == "NULL" else value
    return values


def parse_query(text: str, columns: list[str]) -> list[dict[str, Any]] | None:
    failure = classify_failure(text)
    if failure:
        raise failure
    if text.strip() == "No result found.":
        return []
    rows = split_rows(text)
    if not rows and text.strip():
        raise SafError("parse_error", f"Unrecognised content output: {text.strip()[:200]!r}")
    parsed = [parse_row(row, columns) for row in rows]
    return None if any(row is None for row in parsed) else parsed  # type: ignore[return-value]


def normalise(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("_size", "last_modified", "flags", "available_bytes"):
        if out.get(key) is not None:
            try:
                out[key] = int(out[key])
            except ValueError:
                pass
    if "_display_name" in out:
        out["name"] = out.pop("_display_name")
    if "_size" in out:
        out["size"] = out.pop("_size")
    if "flags" in out:
        out["capabilities"] = decode_flags(out["flags"])
    if "mime_type" in out:
        out["is_directory"] = out["mime_type"] == DIRECTORY_MIME
    return out


class Saf:
    def __init__(self, device: Device):
        self.device = device

    # ------------------------------------------------------------ reads

    def content_query(self, uri: str, columns: list[str]) -> list[dict[str, Any]]:
        command = f"content query --uri {shell_quote(uri)} --projection {':'.join(columns)}"
        out = self.device.shell(command)
        rows = parse_query(out.text + ("\n" + out.error_text if out.error_text.strip() else ""), columns)
        if rows is not None:
            return [normalise(row) for row in rows]
        # A value contains ", <column>=": fall back to one query per column.
        per_column: list[list[str]] = []
        for column in columns:
            single = self.device.shell(f"content query --uri {shell_quote(uri)} --projection {column}")
            failure = classify_failure(single.text + single.error_text)
            if failure:
                raise failure
            values = []
            for row in split_rows(single.text):
                if not row.startswith(column + "="):
                    raise SafError("parse_error", f"Unexpected column output for {column}.")
                values.append(row[len(column) + 1:])
            per_column.append(values)
        if len({len(values) for values in per_column}) != 1:
            raise SafError("parse_error", "Provider returned inconsistent rows between queries.")
        merged = [{column: (None if per_column[i][r] == "NULL" else per_column[i][r]) for i, column in enumerate(columns)}
                  for r in range(len(per_column[0]))]
        return [normalise(row) for row in merged]

    def roots(self, authority: str) -> list[dict[str, Any]]:
        return self.content_query(root_uri(authority), ROOT_COLUMNS)

    def stat(self, authority: str, document_id: str) -> dict[str, Any]:
        rows = self.content_query(document_uri(authority, document_id), DOC_COLUMNS)
        if not rows:
            raise SafError("not_found", f"Document {document_id!r} not found in {authority}.")
        if len(rows) != 1:
            raise SafError("provider_error", f"Provider returned {len(rows)} rows for one document.")
        return rows[0]

    def try_stat(self, authority: str, document_id: str) -> dict[str, Any] | None:
        try:
            return self.stat(authority, document_id)
        except SafError as error:
            if error.kind == "not_found":
                return None
            raise

    def children(self, authority: str, document_id: str) -> list[dict[str, Any]]:
        return self.content_query(children_uri(authority, document_id), DOC_COLUMNS)

    def resolve_path(self, authority: str, document_id: str, path: str | None) -> str:
        if not path:
            return document_id
        current = document_id
        for part in [p for p in path.replace("\\", "/").split("/") if p]:
            matches = [row for row in self.children(authority, current) if row.get("name") == part]
            if not matches:
                raise SafError("not_found", f"No child named {part!r} under {current!r}.")
            if len(matches) > 1:
                raise SafError("ambiguous_path", f"Several children named {part!r} under {current!r}.")
            current = matches[0]["document_id"]
        return current

    def sha256(self, authority: str, document_id: str) -> str:
        uri = shell_quote(document_uri(authority, document_id))
        out = self.device.shell(f"content read --uri {uri} | sha256sum")
        failure = classify_failure(out.error_text)
        if failure:
            raise failure
        digest = out.text.split()[0] if out.text.split() else ""
        if out.returncode != 0 or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SafError("hash_failed", "Device-side hashing failed.", details={"stderr": out.error_text[:300]})
        return digest

    def pull(self, authority: str, document_id: str, output: Path) -> dict[str, Any]:
        info = self.stat(authority, document_id)
        if info.get("is_directory"):
            raise SafError("is_directory", "Pull reads documents, not directories.")
        if output.exists():
            raise SafError("output_exists", f"Output {output} already exists; choose an absent path.")
        if not output.parent.is_dir():
            raise SafError("output_parent_missing", f"Output parent {output.parent} does not exist.")
        partial = output.with_name(output.name + ".partial")
        if partial.exists():
            raise SafError("output_exists", f"Stale partial file {partial} exists.")
        try:
            # The device-side hash goes through `adb shell`, which reports provider
            # errors. The bytes go through `exec-out`, which is byte-exact but has no
            # error channel, so they are accepted only if hash and size match.
            device_sha = self.sha256(authority, document_id)
            with open(partial, "xb") as handle:
                self.device.exec_out(f"content read --uri {shell_quote(document_uri(authority, document_id))}",
                                     stdout_file=handle)
            host_sha, size = file_sha256(partial)
            if host_sha != device_sha:
                raise SafError("verification_failed", "Pulled bytes differ from the device-side hash.",
                               details={"host_sha256": host_sha, "device_sha256": device_sha})
            if info.get("size") is not None and info["size"] != size:
                raise SafError("verification_failed", "Pulled size differs from the provider-reported size.",
                               details={"pulled": size, "reported": info["size"]})
            partial.replace(output)
        finally:
            if partial.exists():
                partial.unlink()
        return {"document": info, "output": str(output), "size": size, "sha256": host_sha}

    def providers(self, *, probe: bool = True) -> list[dict[str, Any]]:
        resolvers = self.device.shell("dumpsys package resolvers").text
        provider_map = self.device.shell("dumpsys package providers").text
        components = parse_documents_resolvers(resolvers)
        authorities = parse_provider_authorities(provider_map)
        found = []
        for component in components:
            for authority in authorities.get(component, []):
                entry: dict[str, Any] = {"authority": authority, "component": component}
                if probe:
                    try:
                        entry["roots"] = self.roots(authority)
                        entry["access"] = "readable"
                    except SafError as error:
                        entry["access"] = error.kind
                        entry["error"] = str(error)
                found.append(entry)
        return found

    # ------------------------------------------------------------ device client

    def run_client(self, staging: str, request: dict[str, Any]) -> dict[str, Any]:
        encoded = base64.b64encode(json.dumps(request).encode("utf-8")).decode("ascii")
        out = self.device.shell(f"CLASSPATH={shell_quote(staging + '/client.dex')} app_process / SafClient {encoded}")
        lines = [line for line in out.text.splitlines() if line.strip().startswith("{")]
        if not lines:
            raise SafError("client_failed", "Device client produced no result.",
                           details={"stdout": out.text[-500:], "stderr": out.error_text[-500:]})
        result = json.loads(lines[-1])
        if not result.get("ok"):
            failure = classify_failure(result.get("error_class", "") + ": " + result.get("message", "")) \
                or SafError("client_failed", result.get("message", "Device client failed."))
            failure.details.update({"error_class": result.get("error_class"), "op": request.get("op")})
            raise failure
        return result

    def stage(self, plan_id: str, payload: Path | None) -> str:
        staging = f"/data/local/tmp/adb-saf-{plan_id}"
        probe = self.device.shell(f"test -e {shell_quote(staging)} && echo exists || mkdir {shell_quote(staging)}")
        if probe.text.strip() == "exists" or probe.returncode != 0:
            raise SafError("staging_conflict", f"Device staging {staging} already exists or cannot be created.")
        dex = client_dex()
        self.push_verified(dex, staging + "/client.dex", hashlib.sha256(dex.read_bytes()).hexdigest())
        if payload is not None:
            self.push_verified(payload, staging + "/payload", file_sha256(payload)[0])
        return staging

    def push_verified(self, local: Path, remote: str, expected: str) -> None:
        out = self.device.adb("push", str(local), remote)
        if out.returncode != 0:
            raise SafError("push_failed", f"adb push failed for {local.name}.", details={"stderr": out.error_text[-300:]})
        check = self.device.shell(f"sha256sum {shell_quote(remote)}")
        if check.text.split()[:1] != [expected]:
            raise SafError("verification_failed", f"Staged {local.name} hash differs on the device.")

    def unstage(self, staging: str) -> bool:
        if not re.fullmatch(r"/data/local/tmp/adb-saf-[0-9a-f]{16}", staging):
            return False
        return self.device.shell(f"rm -rf {shell_quote(staging)}").returncode == 0


def client_dex() -> Path:
    path = Path(str(resources.files("agent_toolbelt_adb_saf") / "assets" / "saf-client.dex"))
    if not path.is_file():
        raise SafError("client_unavailable", "Bundled saf-client.dex is missing.")
    return path


def file_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def parse_documents_resolvers(text: str) -> list[str]:
    components: list[str] = []
    active = False
    indent = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "android.content.action.DOCUMENTS_PROVIDER:":
            active, indent = True, len(line) - len(line.lstrip())
            continue
        if active:
            depth = len(line) - len(line.lstrip())
            if not stripped or depth <= (indent or 0):
                active = False
                continue
            parts = stripped.split()
            if len(parts) >= 2 and "/" in parts[1] and parts[1] not in components:
                components.append(parts[1])
    return components


def parse_provider_authorities(text: str) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    authority = None
    for line in text.splitlines():
        stripped = line.strip()
        match = re.fullmatch(r"\[([^\]]+)\]:", stripped)
        if match:
            authority = match.group(1)
            continue
        match = re.match(r"Provider\{[0-9a-f]+ ([^}\s]+)\}", stripped)
        if match and authority:
            for name in authority.split(";"):
                mapping.setdefault(match.group(1), [])
                if name not in mapping[match.group(1)]:
                    mapping[match.group(1)].append(name)
            authority = None
    return mapping


# ---------------------------------------------------------------- plan / apply

def guess_mime(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def validate_name(name: str) -> str:
    if not name or name in (".", "..") or "/" in name or "\x00" in name:
        raise SafError("invalid_name", f"Invalid document name {name!r}.")
    return name


def make_plan(saf: Saf, *, action: str, manifest: Path, target: str | None = None, parent: str | None = None,
              name: str | None = None, source: Path | None = None, mime_type: str | None = None) -> dict[str, Any]:
    if manifest.exists():
        raise SafError("manifest_exists", f"Manifest {manifest} already exists.")
    if not manifest.parent.is_dir():
        raise SafError("manifest_parent_missing", f"Manifest directory {manifest.parent} does not exist.")
    plan: dict[str, Any] = {"schema": PLAN_SCHEMA, "plan_id": secrets.token_hex(8), "action": action,
                            "created_at": int(time.time()), "device": saf.device.identity(), "warnings": []}
    if action == "put":
        if source is None or not source.is_file():
            raise SafError("source_missing", "put requires an existing --source file.")
        sha, size = file_sha256(source)
        plan["source"] = {"path": str(source.resolve()), "size": size, "sha256": sha,
                          "mtime_ns": source.stat().st_mtime_ns}
        if target:
            authority, document_id = parse_target(target)
            info = saf.stat(authority, document_id)
            if info.get("is_directory"):
                raise SafError("is_directory", "put --target must name an existing document, not a directory.")
            plan.update(authority=authority, mode="overwrite",
                        target={**info, "sha256": saf.sha256(authority, document_id)})
            if "write" not in info.get("capabilities", []):
                plan["warnings"].append("Provider does not advertise write support for the target.")
        else:
            if not parent or not name:
                raise SafError("invalid_plan", "put needs --target, or --parent and --name.")
            authority, parent_id = parse_target(parent)
            plan.update(authority=authority, mode="create", name=validate_name(name),
                        mime_type=mime_type or guess_mime(name), parent=plan_parent(saf, authority, parent_id, name, plan))
    elif action == "mkdir":
        if not parent or not name:
            raise SafError("invalid_plan", "mkdir needs --parent and --name.")
        authority, parent_id = parse_target(parent)
        plan.update(authority=authority, name=validate_name(name), mime_type=DIRECTORY_MIME,
                    parent=plan_parent(saf, authority, parent_id, name, plan))
    elif action == "rename":
        if not target or not name:
            raise SafError("invalid_plan", "rename needs --target and --name.")
        authority, document_id = parse_target(target)
        info = saf.stat(authority, document_id)
        plan.update(authority=authority, name=validate_name(name), target=info)
        if parent:
            parent_authority, parent_id = parse_target(parent)
            if parent_authority != authority:
                raise SafError("invalid_plan", "Parent and target belong to different providers.")
            plan["parent"] = plan_parent(saf, authority, parent_id, name, plan, child=document_id)
        else:
            plan["warnings"].append("No --parent given: the absence of a sibling with the new name is not checked.")
        if "rename" not in info.get("capabilities", []):
            plan["warnings"].append("Provider does not advertise rename support for the target.")
    elif action == "delete":
        if not target:
            raise SafError("invalid_plan", "delete needs --target.")
        authority, document_id = parse_target(target)
        info = saf.stat(authority, document_id)
        plan.update(authority=authority, target=info)
        if info.get("is_directory"):
            if saf.children(authority, document_id):
                raise SafError("directory_not_empty", "delete removes files and empty directories only.")
        else:
            plan["target"]["sha256"] = saf.sha256(authority, document_id)
        if "delete" not in info.get("capabilities", []):
            plan["warnings"].append("Provider does not advertise delete support for the target.")
    else:
        raise SafError("invalid_plan", f"Unknown action {action!r}.")
    manifest.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {"manifest": str(manifest), "plan": plan}


def plan_parent(saf: Saf, authority: str, parent_id: str, name: str, plan: dict[str, Any],
                child: str | None = None) -> dict[str, Any]:
    info = saf.stat(authority, parent_id)
    if not info.get("is_directory"):
        raise SafError("not_a_directory", f"Parent {parent_id!r} is not a directory.")
    siblings = saf.children(authority, parent_id)
    if child is not None and not any(row["document_id"] == child for row in siblings):
        raise SafError("invalid_plan", "Target is not a child of the given parent.")
    if any(row.get("name") == name for row in siblings):
        raise SafError("name_exists", f"{name!r} already exists in the parent directory.")
    if child is None and "dir_create" not in info.get("capabilities", []):
        plan["warnings"].append("Provider does not advertise create support for the parent directory.")
    return {"document_id": parent_id, "name": info.get("name"), "children": len(siblings)}


def same_state(recorded: dict[str, Any], current: dict[str, Any]) -> bool:
    keys = ("document_id", "name", "mime_type", "size", "last_modified")
    return all(recorded.get(key) == current.get(key) for key in keys)


def apply_plan(saf: Saf, manifest: Path, *, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise SafError("confirmation_required", "Pass --confirm to apply the reviewed plan.")
    plan = json.loads(manifest.read_text(encoding="utf-8"))
    if plan.get("schema") != PLAN_SCHEMA or plan.get("applied"):
        raise SafError("invalid_plan", "Manifest is not an unapplied adb-saf plan.")
    if not re.fullmatch(r"[0-9a-f]{16}", str(plan.get("plan_id"))):
        raise SafError("invalid_plan", "Manifest plan_id is malformed.")
    identity = saf.device.identity()
    if identity["identity_hash"] != plan["device"]["identity_hash"]:
        raise SafError("device_changed", "The bound device differs from the planned device.")
    authority, action = plan["authority"], plan["action"]
    backup_dir = manifest.with_name(manifest.stem + ".backup")
    result: dict[str, Any] = {"plan_id": plan["plan_id"], "action": action}

    # Drift checks: nothing has changed since the plan was reviewed.
    source = None
    if plan.get("source"):
        source = Path(plan["source"]["path"])
        if not source.is_file() or file_sha256(source) != (plan["source"]["sha256"], plan["source"]["size"]):
            raise SafError("source_changed", "The source file changed since planning.")
    target_id = None
    if plan.get("target"):
        target_id = plan["target"]["document_id"]
        current = saf.try_stat(authority, target_id)
        if current is None or not same_state(plan["target"], current):
            raise SafError("target_changed", "The target document changed since planning.",
                           details={"planned": plan["target"], "current": current})
        if plan["target"].get("sha256") and saf.sha256(authority, target_id) != plan["target"]["sha256"]:
            raise SafError("target_changed", "The target content hash changed since planning.")
    if plan.get("parent"):
        siblings = saf.children(authority, plan["parent"]["document_id"])
        if any(row.get("name") == plan["name"] for row in siblings):
            raise SafError("name_exists", f"{plan['name']!r} appeared in the parent since planning.")
    if action == "delete" and plan["target"].get("is_directory") and saf.children(authority, target_id):
        raise SafError("directory_not_empty", "The directory gained children since planning.")

    # Back up content that will be overwritten or deleted.
    if plan.get("target", {}).get("sha256") and (action == "delete" or plan.get("mode") == "overwrite"):
        if backup_dir.exists():
            raise SafError("backup_exists", f"Backup folder {backup_dir} exists from an earlier attempt; "
                           "inspect it, then plan again with a new manifest.")
        backup_dir.mkdir()
        backup = backup_dir / (re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", plan["target"]["name"] or "") or "document")
        pulled = saf.pull(authority, target_id, backup)
        if pulled["sha256"] != plan["target"]["sha256"]:
            raise SafError("backup_failed", "Backup content differs from the planned target hash.")
        result["backup"] = {"path": str(backup), "sha256": pulled["sha256"], "size": pulled["size"]}

    staging = saf.stage(plan["plan_id"], source)
    try:
        request = {"authority": authority}
        if action == "put" and plan["mode"] == "overwrite":
            written = saf.run_client(staging, {**request, "op": "write", "document_id": target_id,
                                               "source": staging + "/payload"})
            result["document_id"] = target_id
            result["write"] = written
        elif action in ("put", "mkdir"):
            created = saf.run_client(staging, {**request, "op": "create", "parent_id": plan["parent"]["document_id"],
                                               "mime_type": plan["mime_type"], "display_name": plan["name"]})
            new_id = created.get("document_id")
            if not new_id:
                raise SafError("client_failed", "Provider created a document but returned no ID.")
            result["document_id"] = new_id
            try:
                info = saf.stat(authority, new_id)
                if info.get("name") != plan["name"]:
                    raise SafError("name_changed", f"Provider named the new document {info.get('name')!r}.",
                                   details={"document_id": new_id})
                if action == "put":
                    result["write"] = saf.run_client(staging, {**request, "op": "write", "document_id": new_id,
                                                               "source": staging + "/payload"})
            except SafError as error:
                # Roll back only the document this apply created.
                try:
                    saf.run_client(staging, {**request, "op": "delete", "document_id": new_id})
                    error.details["rolled_back"] = new_id
                except SafError as rollback:
                    error.details["rollback_failed"] = str(rollback)
                raise
        elif action == "rename":
            renamed = saf.run_client(staging, {**request, "op": "rename", "document_id": target_id,
                                               "display_name": plan["name"]})
            result["document_id"] = renamed["document_id"]
        elif action == "delete":
            saf.run_client(staging, {**request, "op": "delete", "document_id": target_id})
    finally:
        result["staging_removed"] = saf.unstage(staging)

    # Verify the outcome independently of the client's own report.
    if action == "put":
        info = saf.stat(authority, result["document_id"])
        digest = saf.sha256(authority, result["document_id"])
        if digest != plan["source"]["sha256"] or (info.get("size") not in (None, plan["source"]["size"])):
            raise SafError("verification_failed", "Written document does not match the source.",
                           details={"document": info, "sha256": digest, "backup": result.get("backup")})
        result["document"] = info
        result["sha256"] = digest
    elif action == "mkdir":
        result["document"] = saf.stat(authority, result["document_id"])
    elif action == "rename":
        info = saf.stat(authority, result["document_id"])
        if info.get("name") != plan["name"]:
            raise SafError("verification_failed", "Renamed document does not carry the new name.",
                           details={"document": info})
        result["document"] = info
    elif action == "delete":
        if saf.try_stat(authority, target_id) is not None:
            raise SafError("verification_failed", "Deleted document is still present.")
        result["deleted"] = target_id
    plan["applied"] = {"at": int(time.time()), "result": result}
    manifest.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8", newline="\n")
    return result
