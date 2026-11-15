from __future__ import annotations

import base64
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote

FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FAMILY / "src"))

from agent_toolbelt_adb_saf import saf as saf_module  # noqa: E402
from agent_toolbelt_adb_saf.device import Completed, Device, SafError  # noqa: E402
from agent_toolbelt_adb_saf.saf import Saf, apply_plan, make_plan  # noqa: E402

AUTH = "com.example.documents"
DIR = "vnd.android.document/directory"
SCRATCH_PARENT = Path(os.environ.get("ADB_SAF_TEST_SCRATCH", tempfile.gettempdir()))


class FakeAndroid:
    """In-memory documents provider answering the shell commands adb-saf issues."""

    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.files: dict[str, bytes] = {}  # /data/local/tmp staging
        self.serial = "SER123"
        self.fingerprint = "fp/1"
        self.clock = 1000
        self.denied = False
        self.exec_out_corrupt = False
        self.rename_suffix = ""  # provider-side renaming on create
        self.commands: list[str] = []
        self.add("root", None, "root", DIR)

    def add(self, doc_id, parent, name, mime, data=None):
        self.clock += 1
        self.docs[doc_id] = {"parent": parent, "name": name, "mime": mime, "data": data, "mtime": self.clock}

    def row(self, doc_id):
        d = self.docs[doc_id]
        size = len(d["data"]) if d["data"] is not None else 4096
        flags = 0x8 | 0x4 | 0x40 if d["mime"] == DIR else 0x2 | 0x4 | 0x40
        return [doc_id, d["name"], d["mime"], str(size), str(d["mtime"]), str(flags)]

    def format_rows(self, rows, columns):
        out = []
        for n, values in enumerate(rows):
            out.append(f"Row: {n} " + ", ".join(f"{c}={v}" for c, v in zip(columns, values)))
        return ("\n".join(out) + "\n") if out else "No result found.\n"

    def query(self, uri, columns):
        assert uri.startswith(f"content://{AUTH}/")
        path = uri[len(f"content://{AUTH}/"):]
        if path == "root":
            all_cols = {"root_id": "main", "document_id": "root", "title": "Example", "flags": "1", "available_bytes": "99"}
            return self.format_rows([[all_cols[c] for c in columns]], columns)
        parts = path.split("/")
        doc_id = unquote(parts[1])
        names = ["document_id", "_display_name", "mime_type", "_size", "last_modified", "flags"]
        pick = lambda r: [r[names.index(c)] for c in columns]  # noqa: E731
        if len(parts) == 3 and parts[2] == "children":
            kids = [k for k, v in self.docs.items() if v["parent"] == doc_id]
            return self.format_rows([pick(self.row(k)) for k in kids], columns)
        if doc_id not in self.docs:
            return "No result found.\n"
        return self.format_rows([pick(self.row(doc_id))], columns)

    def client(self, request):
        op = request["op"]
        if self.denied:
            return {"ok": False, "error_class": "java.lang.SecurityException", "message": "Permission Denial: writing"}
        if op == "create":
            name = request["display_name"] + self.rename_suffix
            new_id = request["parent_id"] + "/" + name
            self.add(new_id, request["parent_id"], name, request["mime_type"], None if request["mime_type"] == DIR else b"")
            return {"ok": True, "op": op, "document_id": new_id}
        if op == "write":
            data = self.files[request["source"]]
            self.docs[request["document_id"]]["data"] = data
            self.clock += 1
            self.docs[request["document_id"]]["mtime"] = self.clock
            return {"ok": True, "op": op, "bytes_written": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        if op == "rename":
            old = request["document_id"]
            doc = self.docs.pop(old)
            new_id = doc["parent"] + "/" + request["display_name"]
            doc["name"] = request["display_name"]
            self.docs[new_id] = doc
            return {"ok": True, "op": op, "document_id": new_id}
        if op == "delete":
            del self.docs[request["document_id"]]
            return {"ok": True, "op": op}
        raise AssertionError(op)

    def __call__(self, argv, stdin=None, stdout_file=None):
        args = list(argv[1:])
        if args[:1] in (["-s"], ["-t"]):
            args = args[2:]
        if args == ["get-serialno"]:
            return Completed(0, (self.serial + "\n").encode(), b"")
        if args[0] == "push":
            self.files[args[2]] = Path(args[1]).read_bytes()
            return Completed(0, b"", b"1 file pushed")
        if args[0] == "exec-out":
            # Binary reads must use exec-out: `adb shell` stdout is LF->CRLF on Windows.
            command = args[1]
            self.commands.append("exec-out " + command)
            assert command.startswith("content read") and "|" not in command, command
            doc_id = unquote(shlex.split(command)[shlex.split(command).index("--uri") + 1].split("/document/")[1])
            data = self.docs[doc_id]["data"] if doc_id in self.docs else b""
            stdout_file.write(data[:-1] if self.exec_out_corrupt else data)
            return Completed(0, b"", b"")
        assert args[0] == "shell" and len(args) == 2, args
        command = args[1]
        self.commands.append(command)
        if command.startswith("getprop"):
            values = [self.serial, "Model", "dev", self.fingerprint, "35"]
            return Completed(0, ("\n".join(values) + "\n").encode(), b"")
        if command.startswith("content query"):
            tokens = shlex.split(command)
            uri = tokens[tokens.index("--uri") + 1]
            columns = tokens[tokens.index("--projection") + 1].split(":")
            if self.denied:
                return Completed(0, b"", b"Error while accessing provider:x\njava.lang.SecurityException: Permission Denial\n")
            return Completed(0, self.query(uri, columns).encode(), b"")
        if command.startswith("content read"):
            tokens = shlex.split(command.split("|")[0])
            doc_id = unquote(tokens[tokens.index("--uri") + 1].split("/document/")[1])
            data = self.docs[doc_id]["data"]
            if "| sha256sum" in command:
                return Completed(0, (hashlib.sha256(data).hexdigest() + "  -\n").encode(), b"")
            stdout_file.write(data.replace(b"\n", b"\r\n"))  # Windows adb shell stdout is text mode
            return Completed(0, b"", b"")
        if command.startswith("test -e"):
            path = shlex.split(command)[2]
            if any(name.startswith(path + "/") for name in self.files):
                return Completed(0, b"exists\n", b"")
            return Completed(0, b"", b"")
        if command.startswith("sha256sum"):
            path = shlex.split(command)[1]
            return Completed(0, f"{hashlib.sha256(self.files[path]).hexdigest()}  {path}\n".encode(), b"")
        if command.startswith("CLASSPATH="):
            request = json.loads(base64.b64decode(command.split()[-1]))
            result = self.client(request)
            return Completed(0 if result["ok"] else 1, (json.dumps(result) + "\n").encode(), b"")
        if command.startswith("rm -rf"):
            path = shlex.split(command)[2]
            self.files = {k: v for k, v in self.files.items() if not k.startswith(path + "/")}
            return Completed(0, b"", b"")
        raise AssertionError(command)


class SafTestCase(unittest.TestCase):
    def setUp(self):
        self.android = FakeAndroid()
        self.android.add("root/dir", "root", "dir", DIR)
        self.android.add("root/dir/a.txt", "root/dir", "a.txt", "text/plain", b"old content")
        self.saf = Saf(Device("adb", ["-s", "SER123"], "SER123", self.android))
        self.temp = tempfile.TemporaryDirectory(dir=SCRATCH_PARENT)
        self.work = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def source(self, data: bytes, name="src.bin") -> Path:
        path = self.work / name
        path.write_bytes(data)
        return path


class ParsingTests(unittest.TestCase):
    def test_target_splits_at_first_colon(self):
        self.assertEqual(saf_module.parse_target("a.b.documents:primary:Download/x"), ("a.b.documents", "primary:Download/x"))
        with self.assertRaises(SafError):
            saf_module.parse_target("no-colon")

    def test_encoded_ids_carry_no_shell_metacharacters(self):
        uri = saf_module.document_uri(AUTH, "/data/user/0/p/it's (1)!*.txt")
        self.assertNotRegex(uri.split("/document/")[1], r"[^A-Za-z0-9%._~-]")

    def test_row_with_separator_inside_value_is_ambiguous(self):
        cols = ["document_id", "_display_name", "mime_type"]
        self.assertIsNone(saf_module.parse_row("document_id=x, _display_name=a, mime_type=b, mime_type=c", cols))
        self.assertEqual(saf_module.parse_row("document_id=x, _display_name=we, ird=n, mime_type=t", cols)["_display_name"],
                         "we, ird=n")

    def test_permission_denial_is_classified(self):
        error = saf_module.classify_failure("Error while accessing provider:x\njava.lang.SecurityException: Permission Denial: reading")
        self.assertEqual(error.kind, "permission_denied")

    def test_discovery_joins_resolvers_and_authorities(self):
        resolvers = ("    Provider Resolver Table:\n      android.content.action.DOCUMENTS_PROVIDER:\n"
                     "        e465478 com.android.mtp/.MtpDocumentsProvider\n        3ab8450 com.x/.Docs\n"
                     "      com.android.settings.OTHER:\n        ce75a62 com.android.settings/.B\n")
        providers = ("  [com.x.documents]:\n    Provider{3ab8450 com.x/.Docs}\n"
                     "  [com.android.mtp.documents]:\n    Provider{e465478 com.android.mtp/.MtpDocumentsProvider}\n")
        self.assertEqual(saf_module.parse_documents_resolvers(resolvers), ["com.android.mtp/.MtpDocumentsProvider", "com.x/.Docs"])
        self.assertEqual(saf_module.parse_provider_authorities(providers)["com.x/.Docs"], ["com.x.documents"])

    def test_bundled_dex_matches_source(self):
        assets = FAMILY / "src" / "agent_toolbelt_adb_saf" / "assets"
        record = json.loads((assets / "saf-client.json").read_text())
        self.assertEqual(record["source_sha256"], hashlib.sha256((assets / "SafClient.java").read_bytes()).hexdigest(),
                         "SafClient.java changed: run scripts/build_client_dex.py")
        self.assertEqual(record["dex_sha256"], hashlib.sha256((assets / "saf-client.dex").read_bytes()).hexdigest())


class ReadTests(SafTestCase):
    def test_list_stat_hash_and_path_walk(self):
        children = self.saf.children(AUTH, "root/dir")
        self.assertEqual([c["name"] for c in children], ["a.txt"])
        self.assertIn("write", children[0]["capabilities"])
        self.assertEqual(self.saf.resolve_path(AUTH, "root", "dir/a.txt"), "root/dir/a.txt")
        self.assertEqual(self.saf.sha256(AUTH, "root/dir/a.txt"), hashlib.sha256(b"old content").hexdigest())

    def test_ambiguous_names_fall_back_to_per_column_queries(self):
        self.android.add("root/dir/w", "root/dir", "odd, mime_type=x", "text/plain", b"1")
        names = sorted(c["name"] for c in self.saf.children(AUTH, "root/dir"))
        self.assertEqual(names, ["a.txt", "odd, mime_type=x"])

    def test_pull_verifies_and_refuses_existing_output(self):
        result = self.saf.pull(AUTH, "root/dir/a.txt", self.work / "out.txt")
        self.assertEqual((self.work / "out.txt").read_bytes(), b"old content")
        self.assertEqual(result["sha256"], hashlib.sha256(b"old content").hexdigest())
        with self.assertRaises(SafError) as raised:
            self.saf.pull(AUTH, "root/dir/a.txt", self.work / "out.txt")
        self.assertEqual(raised.exception.kind, "output_exists")

    def test_pull_is_byte_exact_for_newlines_and_rejects_short_reads(self):
        data = b"line\nbin\x00\xff\r\n\n"
        self.android.add("root/dir/b.bin", "root/dir", "b.bin", "application/octet-stream", data)
        self.saf.pull(AUTH, "root/dir/b.bin", self.work / "b.bin")
        self.assertEqual((self.work / "b.bin").read_bytes(), data)
        self.assertTrue(any(c.startswith("exec-out content read") for c in self.android.commands))
        self.android.exec_out_corrupt = True
        with self.assertRaises(SafError) as raised:
            self.saf.pull(AUTH, "root/dir/b.bin", self.work / "short.bin")
        self.assertEqual(raised.exception.kind, "verification_failed")
        self.assertFalse((self.work / "short.bin").exists())
        self.assertFalse((self.work / "short.bin.partial").exists())

    def test_denied_provider_reports_permission_denied(self):
        self.android.denied = True
        with self.assertRaises(SafError) as raised:
            self.saf.roots(AUTH)
        self.assertEqual(raised.exception.kind, "permission_denied")


class ChangeTests(SafTestCase):
    def plan(self, action, **kwargs):
        manifest = self.work / f"{action}-{len(list(self.work.iterdir()))}.json"
        make_plan(self.saf, action=action, manifest=manifest, **kwargs)
        return manifest

    def test_overwrite_backs_up_writes_verifies_and_cleans_staging(self):
        manifest = self.plan("put", target=f"{AUTH}:root/dir/a.txt", source=self.source(b"new"))
        result = apply_plan(self.saf, manifest, confirm=True)
        self.assertEqual(self.android.docs["root/dir/a.txt"]["data"], b"new")
        self.assertEqual(Path(result["backup"]["path"]).read_bytes(), b"old content")
        self.assertTrue(result["staging_removed"])
        self.assertEqual(self.android.files, {})
        with self.assertRaises(SafError):
            apply_plan(self.saf, manifest, confirm=True)

    def test_apply_requires_confirmation(self):
        manifest = self.plan("put", target=f"{AUTH}:root/dir/a.txt", source=self.source(b"new"))
        with self.assertRaises(SafError) as raised:
            apply_plan(self.saf, manifest, confirm=False)
        self.assertEqual(raised.exception.kind, "confirmation_required")

    def test_target_drift_refuses_before_any_change(self):
        manifest = self.plan("put", target=f"{AUTH}:root/dir/a.txt", source=self.source(b"new"))
        self.android.docs["root/dir/a.txt"]["data"] = b"edited elsewhere"
        with self.assertRaises(SafError) as raised:
            apply_plan(self.saf, manifest, confirm=True)
        self.assertEqual(raised.exception.kind, "target_changed")
        self.assertEqual(self.android.docs["root/dir/a.txt"]["data"], b"edited elsewhere")
        self.assertFalse(any(c.startswith("CLASSPATH=") for c in self.android.commands))

    def test_source_drift_and_device_change_refuse(self):
        source = self.source(b"new")
        manifest = self.plan("put", target=f"{AUTH}:root/dir/a.txt", source=source)
        source.write_bytes(b"changed")
        with self.assertRaises(SafError) as raised:
            apply_plan(self.saf, manifest, confirm=True)
        self.assertEqual(raised.exception.kind, "source_changed")
        manifest2 = self.plan("delete", target=f"{AUTH}:root/dir/a.txt")
        self.android.fingerprint = "fp/2"
        self.saf.device._identity = None
        with self.assertRaises(SafError) as raised:
            apply_plan(self.saf, manifest2, confirm=True)
        self.assertEqual(raised.exception.kind, "device_changed")

    def test_create_mkdir_rename_delete(self):
        apply_plan(self.saf, self.plan("mkdir", parent=f"{AUTH}:root/dir", name="sub"), confirm=True)
        self.assertEqual(self.android.docs["root/dir/sub"]["mime"], DIR)
        created = apply_plan(self.saf, self.plan("put", parent=f"{AUTH}:root/dir/sub", name="b.txt",
                                                 source=self.source(b"bee")), confirm=True)
        self.assertEqual(created["document_id"], "root/dir/sub/b.txt")
        self.assertEqual(self.android.docs["root/dir/sub/b.txt"]["data"], b"bee")
        renamed = apply_plan(self.saf, self.plan("rename", target=f"{AUTH}:root/dir/sub/b.txt",
                                                 parent=f"{AUTH}:root/dir/sub", name="c.txt"), confirm=True)
        self.assertEqual(renamed["document_id"], "root/dir/sub/c.txt")
        deleted = apply_plan(self.saf, self.plan("delete", target=f"{AUTH}:root/dir/sub/c.txt"), confirm=True)
        self.assertEqual(Path(deleted["backup"]["path"]).read_bytes(), b"bee")
        self.assertNotIn("root/dir/sub/c.txt", self.android.docs)

    def test_existing_name_and_non_empty_directory_are_refused_at_plan(self):
        with self.assertRaises(SafError) as raised:
            self.plan("put", parent=f"{AUTH}:root/dir", name="a.txt", source=self.source(b"x"))
        self.assertEqual(raised.exception.kind, "name_exists")
        with self.assertRaises(SafError) as raised:
            self.plan("delete", target=f"{AUTH}:root/dir")
        self.assertEqual(raised.exception.kind, "directory_not_empty")

    def test_name_appearing_after_plan_refuses(self):
        manifest = self.plan("put", parent=f"{AUTH}:root/dir", name="b.txt", source=self.source(b"x"))
        self.android.add("root/dir/b.txt", "root/dir", "b.txt", "text/plain", b"other")
        with self.assertRaises(SafError) as raised:
            apply_plan(self.saf, manifest, confirm=True)
        self.assertEqual(raised.exception.kind, "name_exists")

    def test_provider_renaming_new_document_is_rolled_back(self):
        self.android.rename_suffix = " (1)"
        manifest = self.plan("put", parent=f"{AUTH}:root/dir", name="b.txt", source=self.source(b"x"))
        with self.assertRaises(SafError) as raised:
            apply_plan(self.saf, manifest, confirm=True)
        self.assertEqual(raised.exception.kind, "name_changed")
        self.assertEqual(raised.exception.details["rolled_back"], "root/dir/b.txt (1)")
        self.assertNotIn("root/dir/b.txt (1)", self.android.docs)
        self.assertEqual(self.android.files, {})

    def test_denied_mutation_reports_permission_and_cleans_staging(self):
        manifest = self.plan("mkdir", parent=f"{AUTH}:root/dir", name="sub")
        self.android.denied = True
        with self.assertRaises(SafError) as raised:
            # Plan checks run before denial; the client then refuses.
            with patch.object(Saf, "children", return_value=[]):
                apply_plan(self.saf, manifest, confirm=True)
        self.assertEqual(raised.exception.kind, "permission_denied")
        self.assertEqual(self.android.files, {})


class BindingTests(unittest.TestCase):
    def test_reserved_transport_must_match_serial(self):
        android = FakeAndroid()
        with patch.dict(os.environ, {"COORDINATOR_ADB_TRANSPORT_ID": "7"}), \
                patch("agent_toolbelt_adb_saf.device.resolve_adb", return_value="adb"):
            device = Device.bind(serial="SER123", runner=android)
            self.assertEqual(device.selector, ["-t", "7"])
            with self.assertRaises(SafError) as raised:
                Device.bind(serial="OTHER", runner=android)
        self.assertEqual(raised.exception.kind, "device_binding_mismatch")

    def test_emulator_lease_serial_binds_without_enumeration(self):
        calls = []

        def runner(argv, stdin=None, out=None):
            calls.append(list(argv))
            return Completed(0, b"device\n", b"")
        with patch.dict(os.environ, {"COORDINATOR_ADB_TRANSPORT_ID": "", "COORDINATOR_ADB_SERIAL": "emulator-5584"}), \
                patch("agent_toolbelt_adb_saf.device.resolve_adb", return_value="adb"):
            device = Device.bind(serial="emulator-5584", runner=runner)
            self.assertEqual(device.selector, ["-s", "emulator-5584"])
            self.assertEqual(calls, [["adb", "-s", "emulator-5584", "get-state"]])
            with self.assertRaises(SafError):
                Device.bind(serial="emulator-5586", runner=runner)

    def test_several_ready_devices_need_serial(self):
        listing = b"List of devices attached\nA device model:x\nB device model:y\n"
        runner = lambda argv, stdin=None, out=None: Completed(0, listing, b"")  # noqa: E731
        with patch.dict(os.environ, {"COORDINATOR_ADB_TRANSPORT_ID": "", "COORDINATOR_ADB_SERIAL": ""}), \
                patch("agent_toolbelt_adb_saf.device.resolve_adb", return_value="adb"):
            with self.assertRaises(SafError) as raised:
                Device.bind(serial=None, runner=runner)
            self.assertEqual(raised.exception.kind, "ambiguous_device")
            self.assertEqual(Device.bind(serial="B", runner=runner).selector, ["-s", "B"])


class InstallTests(unittest.TestCase):
    def test_installed_skill_runs_from_its_own_copy(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH_PARENT) as home:
            subprocess.run([sys.executable, "-B", str(FAMILY / "scripts" / "install.py"), "--home", home],
                           check=True, capture_output=True)
            for root in (".codex/skills", ".claude/skills"):
                script = Path(home) / root / "adb-saf" / "scripts" / "invoke_adb_saf.py"
                self.assertTrue((script.parents[1] / "lib" / "agent_toolbelt_adb_saf" / "assets" / "saf-client.dex").is_file())
                out = subprocess.run([sys.executable, "-B", "-I", str(script), "--version"], capture_output=True, text=True)
                self.assertEqual(out.stdout.strip(), "0.1.0", out.stderr)
            subprocess.run([sys.executable, "-B", str(FAMILY / "scripts" / "install.py"), "--home", home],
                           check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
