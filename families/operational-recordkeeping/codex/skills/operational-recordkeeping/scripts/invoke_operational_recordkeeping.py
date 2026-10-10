"""Read-only, event-scoped reconciliation of existing operational records."""

import argparse
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
SCOPE = "Declared facts and affected records only; not a financial or semantic audit."


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    require(isinstance(value, dict), "Profile, event and packet JSON roots must be objects")
    return value


def resolve_path(value, base):
    require(isinstance(value, str) and bool(value.strip()), "Unbound record/evidence path")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def snapshot(path):
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        data = stream.read()
        after = os.fstat(stream.fileno())
    current = path.stat()
    identity = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    require(identity(before) == identity(after) == identity(current),
            f"File changed during read: {path}")
    return data, hashlib.sha256(data).hexdigest()


def format_of(binding, path):
    result = binding.get("format", {".json": "json", ".xlsx": "xlsx"}.get(path.suffix.lower(), "text"))
    require(result in {"text", "json", "xlsx"}, f"Unsupported record format: {result}")
    return result


def section_text(text, heading):
    lines = text.splitlines()
    matches = [i for i, line in enumerate(lines) if line.strip() == heading]
    require(len(matches) == 1, f"Expected one section: {heading}")
    level = re.match(r"^(#{1,6})\s+", heading)
    require(level is not None, "Text proofs require a Markdown heading")
    start = matches[0]
    end = len(lines)
    for i in range(start + 1, len(lines)):
        next_heading = re.match(r"^(#{1,6})\s+", lines[i])
        if next_heading and len(next_heading[1]) <= len(level[1]):
            end = i
            break
    return "\n".join(lines[start:end])


def equal(actual, expected):
    # JSON booleans are not amounts even though bool subclasses int in Python.
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    return actual == expected


def contains_fact(body, expected):
    require(isinstance(expected, (str, int, float)) and not isinstance(expected, bool)
            and str(expected).strip(), "Text facts must be nonempty text or numbers")
    boundary = r"[\w.,]" if isinstance(expected, (int, float)) else r"\w"
    return re.search(r"(?<!" + boundary + ")" + re.escape(str(expected))
                     + r"(?!" + boundary + ")", body) is not None


def xlsx_rows(data, sheet_name):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = [s for s in workbook.findall("s:sheets/s:sheet", NS) if s.get("name") == sheet_name]
        require(len(sheets) == 1, f"Missing/ambiguous worksheet: {sheet_name}")
        rel_id = sheets[0].get(f"{{{REL}}}id")
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in relationships if r.get("Id") == rel_id)
        part = target.lstrip("/") if target.startswith("/") else "xl/" + target
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(si.itertext()) for si in strings]
        sheet = ET.fromstring(archive.read(part))
        rows = {}
        for row in sheet.findall("s:sheetData/s:row", NS):
            cells = {}
            for cell in row.findall("s:c", NS):
                column = re.match(r"[A-Z]+", cell.get("r", ""))
                require(column is not None, "Invalid XLSX cell address")
                value = cell.find("s:v", NS)
                text = value.text if value is not None else None
                if cell.get("t") == "inlineStr":
                    text = "".join(t.text or "" for t in cell.findall("s:is//s:t", NS))
                elif cell.get("t") == "s" and text is not None:
                    text = shared[int(text)]
                elif cell.get("t") == "b" and text is not None:
                    text = text == "1"
                elif cell.get("t") not in {"str", "e"} and text is not None:
                    text = float(text)
                cells[column[0]] = (text, cell.find("s:f", NS) is not None)
            rows[int(row.get("r"))] = cells
        return rows


def xlsx_value(rows, check, facts):
    header_row = check.get("header_row", 1)
    require(type(header_row) is int and header_row > 0, "Invalid header_row")
    headers = {}
    for column, (value, formula) in rows.get(header_row, {}).items():
        require(not formula, "Formula headers are not supported")
        if value is not None:
            require(value not in headers, f"Duplicate XLSX header: {value}")
            headers[value] = column
    key_column, column = headers[check["key_column"]], headers[check["column"]]
    key = facts[check["key_fact"]]
    matches = []
    for number, row in rows.items():
        if number <= header_row:
            continue
        value, formula = row.get(key_column, (None, False))
        require(not formula, "Formula keys cannot prove current state")
        if equal(value, key):
            matches.append(row)
    require(len(matches) == 1, f"Expected one XLSX row for key {key!r}; found {len(matches)}")
    value, formula = matches[0].get(column, (None, False))
    require(not formula, "Formula results cannot prove current state")
    return value


def evaluate(data, fmt, checks, facts):
    results = []
    sheets = {}
    document = json.loads(data.decode("utf-8-sig")) if fmt == "json" else None
    text = data.decode("utf-8-sig") if fmt == "text" else None
    for check in checks:
        fact = check["fact"]
        expected = facts[fact]
        mode = check.get("mode", "equals" if fmt != "text" else "contains")
        if fmt == "text":
            require(mode in {"contains", "absent"}, "Text proof mode must be contains or absent")
            body = section_text(text, check["section"])
            found = contains_fact(body, expected)
            passed = found if mode == "contains" else not found
        else:
            require(mode in ({"equals", "contains", "absent"} if fmt == "json" else {"equals"}),
                    "Unsupported structured proof mode")
            if fmt == "json":
                at = check["at"]
                require(isinstance(at, list) and bool(at), "JSON at must be a nonempty key/index list")
                actual = document
                for key in at:
                    if isinstance(actual, list):
                        require(type(key) is int and 0 <= key < len(actual), "Invalid JSON array index")
                    else:
                        require(isinstance(actual, dict) and isinstance(key, str), "Invalid JSON object path")
                    actual = actual[key]
            else:
                sheet = check["sheet"]
                if sheet not in sheets:
                    sheets[sheet] = xlsx_rows(data, sheet)
                actual = xlsx_value(sheets[sheet], check, facts)
            if mode == "equals":
                passed = equal(actual, expected)
            else:
                require(isinstance(actual, str), "JSON contains/absent requires a string value")
                found = contains_fact(actual, expected)
                passed = found if mode == "contains" else not found
        results.append({"fact": fact, "ok": passed})
    return results


def validate_checks(checks, facts, required):
    require(isinstance(checks, list) and bool(checks), "Checks must be a nonempty list")
    for check in checks:
        require(isinstance(check, dict) and check.get("fact") in facts, "Unknown/missing proof fact")
    positive = {c["fact"] for c in checks if c.get("mode") != "absent"}
    require(set(required) <= positive, f"Missing positive fact coverage: {sorted(set(required) - positive)}")


def profile_path(value):
    if value.endswith(".json") or "/" in value or "\\" in value:
        return Path(value).expanduser().resolve()
    base = os.environ.get("OPERATIONAL_RECORDKEEPING_PROFILES")
    if not base:
        base = str(Path(os.environ["LOCALAPPDATA"]) / "Tools/operational-recordkeeping/profiles") if os.name == "nt" else str(Path.home() / ".config/operational-recordkeeping/profiles")
    return (Path(base) / (value + ".json")).resolve()


def prepare(profile_file, event_file):
    profile, event = load_json(profile_file), load_json(event_file)
    require(all(isinstance(event.get(key), str) and event[key].strip()
                for key in ("event_id", "summary", "kind")), "event_id, summary and kind strings required")
    facts = event["facts"]
    require(isinstance(facts, dict) and all(isinstance(facts.get(key), str) and facts[key].strip()
                                          for key in ("record_key", "state")), "record_key and state string facts required")
    route = profile["routes"][event["kind"]]
    required_facts = route.get("facts", ["record_key", "state"])
    require(set(required_facts) <= facts.keys(), "Missing required event facts")
    extras = event.get("extra_records", [])
    require(isinstance(extras, list) and all(isinstance(r, str) for r in extras), "extra_records must be an ID list")
    record_ids = set(route["records"]) | set(extras)
    require(record_ids, "Event route must affect at least one record")
    require(set(event["checks"]) == record_ids, "Record checks must cover exactly the route plus extra_records")
    evidence = event["evidence"]
    require(isinstance(evidence, list) and bool(evidence), "Readable evidence required")
    combined = [c for binding in evidence for c in binding.get("checks", [])]
    validate_checks(combined, facts, required_facts)
    packet = {"version": 1, "event_id": event["event_id"], "kind": event["kind"],
              "required_facts": required_facts, "required_records": sorted(record_ids),
              "summary": event["summary"], "facts": facts, "records": [], "evidence": []}
    for binding in evidence:
        path = resolve_path(binding["path"], event_file.parent)
        data, digest = snapshot(path)
        source_only = binding.get("source_only", False)
        require(type(source_only) is bool, "source_only must be boolean")
        if source_only:
            require(not binding.get("checks"), "Source-only evidence cannot declare content proofs")
            packet["evidence"].append({"path": str(path), "source_only": True, "checks": [], "sha256": digest})
            continue
        validate_checks(binding["checks"], facts, [])
        fmt = format_of(binding, path)
        proofs = evaluate(data, fmt, binding["checks"], facts)
        require(all(p["ok"] for p in proofs), f"Evidence does not support event facts: {path}")
        packet["evidence"].append({"path": str(path), "format": fmt, "checks": binding["checks"], "sha256": digest})
    for record_id in sorted(record_ids):
        binding = profile["records"][record_id]
        path = resolve_path(binding["path"], profile_file.parent)
        checks = event["checks"][record_id]
        validate_checks(checks, facts, required_facts)
        data, digest = snapshot(path)
        fmt = format_of(binding, path)
        # A new row or section is allowed to be absent before the action.
        packet["records"].append({"id": record_id, "path": str(path), "format": fmt,
                                  "checks": checks, "before_sha256": digest})
    paths = [os.path.normcase(r["path"]) for r in packet["records"]]
    require(len(set(paths)) == len(paths), "Two record IDs alias the same file")
    return packet


def check_packet(packet):
    require(packet.get("version") == 1 and packet.get("records") and packet.get("evidence"), "Invalid packet")
    facts = packet["facts"]
    required = packet["required_facts"]
    require(sorted(r["id"] for r in packet["records"]) == packet["required_records"], "Packet record coverage changed")
    validate_checks([c for r in packet["evidence"] for c in r["checks"]], facts, required)
    fingerprints = {}
    results = []
    for binding in packet["evidence"]:
        path = Path(binding["path"])
        data, digest = snapshot(path)
        require(digest == binding["sha256"], f"Evidence changed; prepare a new packet: {path}")
        if not binding.get("source_only", False):
            require(all(p["ok"] for p in evaluate(data, binding["format"], binding["checks"], facts)), "Evidence no longer supports facts")
        fingerprints[path] = digest
    for binding in packet["records"]:
        validate_checks(binding["checks"], facts, required)
        path = Path(binding["path"])
        data, digest = snapshot(path)
        try:
            proofs = evaluate(data, binding["format"], binding["checks"], facts)
            passed = all(p["ok"] for p in proofs)
            result = {"id": binding["id"], "ok": passed, "proofs": proofs}
        except (ValueError, KeyError, IndexError) as error:
            result = {"id": binding["id"], "ok": False, "error": str(error)}
        change = "changed" if digest != binding["before_sha256"] else "already_consistent" if result["ok"] else "unchanged"
        result.update(sha256=digest, change=change)
        results.append(result)
        fingerprints[path] = digest
    for path, digest in fingerprints.items():
        require(snapshot(path)[1] == digest, f"Record/evidence changed during reconciliation: {path}")
    passed = all(r["ok"] for r in results)
    return {"ok": passed, "operation": "check", "event_id": packet["event_id"],
            "status": "reconciled" if passed else "needs_update", "records": results,
            "verified_at": datetime.now(timezone.utc).isoformat(), "verification_scope": SCOPE}


def inspect_profile(path):
    profile = load_json(path)
    records = []
    for name, binding in profile["records"].items():
        try:
            target = resolve_path(binding.get("path"), path.parent)
            with target.open("rb") as stream:
                stream.read(1)
            records.append({"id": name, "path": str(target), "readable": True})
        except (OSError, ValueError) as error:
            records.append({"id": name, "readable": False, "error": str(error)})
    readable = {r["id"]: r["readable"] for r in records}
    return {"ok": all(readable.values()), "operation": "inspect",
            "profile_id": profile["profile_id"], "instructions": profile.get("instructions", ""),
            "historical_reference": profile.get("historical_reference"), "records": records,
            "routes": profile["routes"], "ready_routes": [kind for kind, route in profile["routes"].items()
                                                           if all(readable.get(name, False) for name in route["records"])]}


def write_new(path, value):
    # Never overwrite a ledger, profile, existing packet or evidence artifact.
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)
        stream.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--profile", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--profile", required=True)
    prep.add_argument("--event", required=True)
    prep.add_argument("--output", required=True)
    check = commands.add_parser("check")
    check.add_argument("--packet", required=True)
    check.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect_profile(profile_path(args.profile))
        elif args.command == "prepare":
            packet = prepare(profile_path(args.profile), Path(args.event).resolve())
            write_new(args.output, packet)
            result = {"ok": True, "operation": "prepare", "packet": str(Path(args.output).resolve()),
                      "event_id": packet["event_id"], "status": "prepared_not_reconciled"}
        else:
            result = check_packet(load_json(args.packet))
            if args.output:
                write_new(args.output, result)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0 if result["ok"] else 1
    except (OSError, ValueError, KeyError, TypeError, IndexError, StopIteration, zipfile.BadZipFile, ET.ParseError) as error:
        print(json.dumps({"ok": False, "operation": args.command, "status": "invalid_or_unavailable",
                          "error": str(error), "verification_scope": SCOPE}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
