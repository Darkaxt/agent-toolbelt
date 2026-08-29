from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[3]
FAMILY_SRC = REPO_ROOT / "families" / "adb-archive-transfer" / "src"
if str(FAMILY_SRC) not in sys.path:
    sys.path.insert(0, str(FAMILY_SRC))

from agent_toolbelt_adb_archive_transfer import transfer
from agent_toolbelt_adb_archive_transfer import cli


TEMP_ROOT = Path(r"D:\Temp")
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


def record(path: str, size: int, digest: str = "a" * 64) -> dict[str, object]:
    return {
        "relative_path": path,
        "size": size,
        "mtime_ns": 1,
        "sha256": digest,
    }


class PlanningTests(unittest.TestCase):
    def test_rejects_incoherent_transfer_thresholds(self):
        with self.assertRaises(transfer.TransferError) as raised:
            transfer.validate_thresholds(
                tiny_max_bytes=64,
                large_min_bytes=32,
                bundle_max_bytes=16,
            )

        self.assertEqual(raised.exception.kind, "invalid_thresholds")

    def test_classifies_only_tiny_files_as_pack_candidates(self):
        tiny = transfer.classify_size(64 * 1024 * 1024)
        medium = transfer.classify_size(64 * 1024 * 1024 + 1)
        large = transfer.classify_size(1024**3)

        self.assertEqual(tiny, ("packed", "tiny_file"))
        self.assertEqual(medium, ("direct", "medium_file_direct"))
        self.assertEqual(large, ("direct", "large_file_direct"))

    def test_single_tiny_file_transfers_directly_without_archive(self):
        files, bundles = transfer.assign_bundles([record("one.txt", 10)])

        self.assertEqual(files[0]["transfer_mode"], "direct")
        self.assertEqual(files[0]["classification_reason"], "single_tiny_file_direct")
        self.assertNotIn("bundle", files[0])
        self.assertEqual(bundles, [])

    def test_bundle_assignment_is_sorted_and_bounded(self):
        files, bundles = transfer.assign_bundles(
            [
                record("z.txt", 6),
                record("a.txt", 6),
                record("middle.bin", 100),
            ],
            tiny_max_bytes=10,
            bundle_max_bytes=10,
        )

        packed = [item for item in files if item["transfer_mode"] == "packed"]
        self.assertEqual([item["relative_path"] for item in packed], ["a.txt", "z.txt"])
        self.assertEqual([item["bundle"] for item in packed], ["bundle-0001.tar", "bundle-0002.tar"])
        self.assertEqual([item["relative_path"] for item in files if item["transfer_mode"] == "direct"], ["middle.bin"])
        self.assertEqual([bundle["payload_bytes"] for bundle in bundles], [6, 6])
        self.assertTrue(all(bundle["archive_format"] == "tar" for bundle in bundles))
        self.assertTrue(all(bundle["compression"] == "none" for bundle in bundles))

    def test_duplicate_casefold_relative_paths_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "case-insensitive relative path collision"):
            transfer.validate_unique_relative_paths(
                [record("Folder/File.txt", 1), record("folder/file.TXT", 1)]
            )

    def test_source_snapshot_hash_is_deterministic(self):
        first = [record("b.txt", 2, "b" * 64), record("a.txt", 1, "a" * 64)]
        second = list(reversed(first))

        self.assertEqual(
            transfer.source_snapshot_hash(first),
            transfer.source_snapshot_hash(second),
        )

    def test_scan_source_hashes_files_and_uses_relative_paths(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temp_dir:
            root = Path(temp_dir)
            (root / "nested").mkdir()
            (root / "nested" / "one.txt").write_text("alpha", encoding="utf-8")
            (root / "two.bin").write_bytes(b"beta")

            files = transfer.scan_source(root)

        self.assertEqual([item["relative_path"] for item in files], ["nested/one.txt", "two.bin"])
        self.assertEqual([item["size"] for item in files], [5, 4])
        self.assertTrue(all(len(str(item["sha256"])) == 64 for item in files))

    def test_scan_source_rejects_symlink_or_reparse_source(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temp_dir:
            source = Path(temp_dir) / "one.txt"
            source.write_text("alpha", encoding="utf-8")
            with patch.object(Path, "is_symlink", return_value=True):
                with self.assertRaisesRegex(ValueError, "symbolic links"):
                    transfer.scan_source(source)

    def test_manifest_canonicalization_excludes_storage_path(self):
        manifest = {
            "schema_version": 1,
            "transfer_id": "abc",
            "manifest_path": r"D:\Temp\one.json",
            "files": [record("one.txt", 1)],
        }

        canonical = transfer.canonical_manifest_json(manifest)

        self.assertNotIn("manifest_path", json.loads(canonical))
        self.assertEqual(canonical, transfer.canonical_manifest_json(dict(reversed(list(manifest.items())))))


class EndpointTests(unittest.TestCase):
    DEVICE_OUTPUT = """List of devices attached
device-001 device product:sample_product model:Test_Device device:sample_device transport_id:34
emulator-5554 offline transport_id:35
192.168.1.20:5555 unauthorized transport_id:36
"""

    def test_parses_adb_devices_with_endpoint_metadata(self):
        devices = transfer.parse_adb_devices(self.DEVICE_OUTPUT)

        self.assertEqual(devices[0]["serial"], "device-001")
        self.assertEqual(devices[0]["state"], "device")
        self.assertEqual(devices[0]["model"], "Test_Device")
        self.assertEqual(devices[0]["transport_id"], "34")
        self.assertEqual(devices[1]["state"], "offline")
        self.assertEqual(devices[2]["state"], "unauthorized")

    def test_selects_only_ready_device_automatically(self):
        selected = transfer.select_device(transfer.parse_adb_devices(self.DEVICE_OUTPUT))
        self.assertEqual(selected["serial"], "device-001")

    def test_multiple_ready_devices_require_explicit_serial(self):
        devices = transfer.parse_adb_devices(
            "List of devices attached\nfirst device transport_id:1\nsecond device transport_id:2\n"
        )

        with self.assertRaises(transfer.TransferError) as raised:
            transfer.select_device(devices)

        self.assertEqual(raised.exception.kind, "ambiguous_device")
        self.assertEqual([item["serial"] for item in raised.exception.details["candidates"]], ["first", "second"])

    def test_explicit_serial_must_be_ready(self):
        devices = transfer.parse_adb_devices(self.DEVICE_OUTPUT)

        with self.assertRaises(transfer.TransferError) as raised:
            transfer.select_device(devices, serial="emulator-5554")

        self.assertEqual(raised.exception.kind, "device_not_ready")

    def test_stable_identity_hash_ignores_transport_id(self):
        first = {
            "serial": "device-001",
            "android_serial": "ABC123",
            "model": "Test Device",
            "product": "kalama",
            "device": "kalama",
            "build_fingerprint": "vendor/build/fingerprint",
            "transport_id": "34",
        }
        second = {**first, "transport_id": "99"}

        self.assertEqual(transfer.stable_identity_hash(first), transfer.stable_identity_hash(second))

    def test_every_adb_command_binds_explicit_serial(self):
        command = transfer.adb_command("C:/sdk/adb.exe", "device-001", "shell", "df", "-Pk", "/storage")
        self.assertEqual(command[:4], ["C:/sdk/adb.exe", "-s", "device-001", "shell"])

    def test_remote_shell_script_is_quoted_as_one_adb_shell_argument(self):
        command = transfer.remote_shell_command(
            "C:/sdk/adb.exe",
            "device-001",
            "test -d /data/local/tmp && test -w /data/local/tmp",
        )

        self.assertEqual(command[-3:-1], ["sh", "-c"])
        self.assertEqual(
            command[-1],
            "'test -d /data/local/tmp && test -w /data/local/tmp'",
        )

    def test_detects_required_toybox_capabilities(self):
        capabilities = transfer.parse_toybox_capabilities("cp gzip mv rm sha256sum tar")
        self.assertTrue(capabilities["tar"])
        self.assertTrue(capabilities["sha256sum"])
        self.assertTrue(capabilities["gzip"])
        self.assertTrue(capabilities["transfer_ready"])

    def test_protected_or_relative_destinations_are_rejected(self):
        for destination in ("relative/path", "/", "/storage", "/sdcard", "/data"):
            with self.subTest(destination=destination):
                with self.assertRaises(transfer.TransferError) as raised:
                    transfer.validate_remote_destination(destination)
                self.assertEqual(raised.exception.kind, "unsafe_destination")

        normalized, parent = transfer.validate_remote_destination("/storage/ABCD-1234/Roms/nds")
        self.assertEqual(normalized, "/storage/ABCD-1234/Roms/nds")
        self.assertEqual(parent, "/storage/ABCD-1234/Roms")

    def test_parses_available_bytes_from_posix_df(self):
        output = """Filesystem 1024-blocks Used Available Capacity Mounted on
/dev/block/vold 1000000 100000 900000 10% /storage/ABCD-1234
"""
        self.assertEqual(transfer.parse_df_available_bytes(output), 900000 * 1024)

    def test_getprop_parser_enriches_endpoint_identity(self):
        output = """[ro.serialno]: [ABC123]
[ro.product.model]: [Test Device]
[ro.product.name]: [kalama]
[ro.product.device]: [kalama]
[ro.build.fingerprint]: [vendor/build/fingerprint]
"""
        endpoint = transfer.enrich_endpoint_identity(
            {"serial": "device-001", "state": "device", "transport_id": "34"},
            output,
        )
        self.assertEqual(endpoint["android_serial"], "ABC123")
        self.assertEqual(endpoint["model"], "Test Device")
        self.assertEqual(endpoint["identity_hash"], transfer.stable_identity_hash(endpoint))


class RecordingRunner:
    def __init__(self, seven_zip_path: Path):
        self.commands: list[tuple[list[str], str | None]] = []
        self.seven_zip_path = seven_zip_path
        self.tar_bytes = b"uncompressed-tar-fixture"

    def __call__(self, command: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
        self.commands.append((list(command), cwd))
        if command[0] == str(self.seven_zip_path):
            archive = Path(command[4])
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(self.tar_bytes)
            return subprocess.CompletedProcess(command, 0, "Everything is Ok\n", "")
        if command[1:] == ["devices", "-l"]:
            return subprocess.CompletedProcess(
                command,
                0,
                "List of devices attached\ndevice-001 device product:sample_product model:Test_Device device:sample_device transport_id:34\n",
                "",
            )
        joined = " ".join(command)
        if "shell getprop" in joined:
            return subprocess.CompletedProcess(
                command,
                0,
                "[ro.serialno]: [ABC123]\n"
                "[ro.product.model]: [Test Device]\n"
                "[ro.product.name]: [kalama]\n"
                "[ro.product.device]: [kalama]\n"
                "[ro.build.fingerprint]: [vendor/build/fingerprint]\n",
                "",
            )
        if joined.endswith("shell toybox"):
            return subprocess.CompletedProcess(command, 0, "cp gzip mkdir mv rm sha256sum tar", "")
        if "df -Pk" in joined:
            return subprocess.CompletedProcess(
                command,
                0,
                "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                "/dev/block/vold 20000000 100000 19900000 1% /storage/ABCD-1234\n",
                "",
            )
        if "toybox sha256sum" in joined and "sha256sum -c" not in joined:
            digest = hashlib.sha256(self.tar_bytes).hexdigest()
            return subprocess.CompletedProcess(command, 0, f"{digest}  bundle.tar\n", "")
        if "toybox sha256sum -c" in joined:
            return subprocess.CompletedProcess(command, 0, "all files: OK\n", "")
        return subprocess.CompletedProcess(command, 0, "", "")


class TransactionTests(unittest.TestCase):
    def make_fixture(self):
        temp = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        root = Path(temp.name)
        source = root / "source"
        source.mkdir()
        (source / "tiny-a.txt").write_bytes(b"a")
        (source / "tiny-b.txt").write_bytes(b"b")
        (source / "medium.bin").write_bytes(b"0123456789")
        adb_path = root / "adb.exe"
        adb_path.write_bytes(b"fake-adb")
        seven_zip_path = root / "7z.exe"
        seven_zip_path.write_bytes(b"fake-7z")
        manifest_path = root / "manifest.json"
        runner = RecordingRunner(seven_zip_path)
        return temp, root, source, adb_path, seven_zip_path, manifest_path, runner

    def create_plan(self):
        fixture = self.make_fixture()
        temp, root, source, adb_path, seven_zip_path, manifest_path, runner = fixture
        result = transfer.plan_transfer(
            source=source,
            destination="/storage/ABCD-1234/Roms/demo",
            serial="device-001",
            manifest_path=manifest_path,
            temp_root=root / "staging",
            adb_path=str(adb_path),
            seven_zip_path=str(seven_zip_path),
            tiny_max_bytes=4,
            bundle_max_bytes=100,
            runner=runner,
        )
        return fixture, result

    def test_cli_parses_plan_apply_and_cleanup_confirmation_flags(self):
        plan = cli.build_parser().parse_args(
            ["plan", "--source", "D:/source", "--destination", "/sdcard/demo", "--serial", "one"]
        )
        apply = cli.build_parser().parse_args(
            ["apply", "--manifest", "D:/manifest.json", "--confirm-transfer"]
        )
        cleanup = cli.build_parser().parse_args(
            ["cleanup", "--manifest", "D:/manifest.json", "--confirm-cleanup"]
        )
        self.assertEqual(plan.operation, "plan")
        self.assertTrue(apply.confirm_transfer)
        self.assertTrue(cleanup.confirm_cleanup)

    def test_plan_reports_invalid_source_as_structured_transfer_error(self):
        fixture = self.make_fixture()
        temp, root, _source, adb_path, seven_zip_path, manifest_path, runner = fixture
        try:
            with self.assertRaises(transfer.TransferError) as raised:
                transfer.plan_transfer(
                    source=root / "missing",
                    destination="/storage/ABCD-1234/Roms/demo",
                    manifest_path=manifest_path,
                    adb_path=str(adb_path),
                    seven_zip_path=str(seven_zip_path),
                    runner=runner,
                )
        finally:
            temp.cleanup()

        self.assertEqual(raised.exception.kind, "source_invalid")
        self.assertEqual(runner.commands, [])

    def test_plan_writes_endpoint_bound_manifest_and_transfer_partition(self):
        fixture, result = self.create_plan()
        temp, _root, _source, _adb, _seven_zip, manifest_path, _runner = fixture
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        finally:
            temp.cleanup()

        self.assertTrue(result["ok"])
        self.assertEqual(manifest["device"]["serial"], "device-001")
        self.assertEqual(manifest["destination"], "/storage/ABCD-1234/Roms/demo")
        modes = {item["relative_path"]: item["transfer_mode"] for item in manifest["files"]}
        self.assertEqual(modes["tiny-a.txt"], "packed")
        self.assertEqual(modes["tiny-b.txt"], "packed")
        self.assertEqual(modes["medium.bin"], "direct")
        self.assertEqual(manifest["bundles"][0]["compression"], "none")
        self.assertEqual(manifest["manifest_sha256"], transfer.manifest_hash(manifest))

    def test_apply_requires_explicit_confirmation_before_any_command(self):
        fixture, _result = self.create_plan()
        temp, _root, _source, _adb, _seven_zip, manifest_path, runner = fixture
        runner.commands.clear()
        try:
            with self.assertRaises(transfer.TransferError) as raised:
                transfer.apply_transfer(manifest_path, confirm_transfer=False, runner=runner)
        finally:
            temp.cleanup()
        self.assertEqual(raised.exception.kind, "confirmation_required")
        self.assertEqual(runner.commands, [])

    def test_source_drift_fails_before_remote_mutation(self):
        fixture, _result = self.create_plan()
        temp, _root, source, _adb, _seven_zip, manifest_path, runner = fixture
        (source / "tiny-a.txt").write_bytes(b"changed")
        runner.commands.clear()
        try:
            with self.assertRaises(transfer.TransferError) as raised:
                transfer.apply_transfer(manifest_path, confirm_transfer=True, runner=runner)
        finally:
            temp.cleanup()
        self.assertEqual(raised.exception.kind, "source_changed")
        self.assertFalse(any(" push " in f" {' '.join(command)} " for command, _cwd in runner.commands))
        self.assertFalse(any(" mkdir " in f" {' '.join(command)} " for command, _cwd in runner.commands))

    def test_unlisted_new_source_file_is_ignored_by_ticket(self):
        fixture, _result = self.create_plan()
        temp, _root, source, _adb, _seven_zip, manifest_path, runner = fixture
        (source / "created-after-plan.txt").write_text("ignore me", encoding="utf-8")
        runner.commands.clear()
        try:
            result = transfer.apply_transfer(
                manifest_path,
                confirm_transfer=True,
                keep_manifest=True,
                runner=runner,
            )
        finally:
            temp.cleanup()
        self.assertTrue(result["ok"])
        pushed = "\n".join(" ".join(command) for command, _cwd in runner.commands if "push" in command)
        self.assertNotIn("created-after-plan.txt", pushed)

    def test_apply_uses_uncompressed_tar_direct_push_and_verified_placement_order(self):
        fixture, _result = self.create_plan()
        temp, _root, _source, _adb, seven_zip_path, manifest_path, runner = fixture
        runner.commands.clear()
        try:
            result = transfer.apply_transfer(
                manifest_path,
                confirm_transfer=True,
                keep_manifest=True,
                runner=runner,
            )
        finally:
            temp.cleanup()

        rendered = [" ".join(command) for command, _cwd in runner.commands]
        seven_zip_commands = [command for command, _cwd in runner.commands if command[0] == str(seven_zip_path)]
        self.assertEqual(len(seven_zip_commands), 1)
        self.assertIn("-ttar", seven_zip_commands[0])
        self.assertFalse(any(argument.startswith("-mx") for argument in seven_zip_commands[0]))
        direct_push = next(line for line in rendered if " push " in f" {line} " and "medium.bin" in line)
        self.assertNotIn("bundle", direct_push)
        extract_index = next(index for index, line in enumerate(rendered) if "tar --restrict -xf" in line)
        verify_index = next(index for index, line in enumerate(rendered) if "sha256sum -c" in line)
        placement_index = next(index for index, line in enumerate(rendered) if "mv --" in line and "/Roms/demo" in line)
        self.assertLess(extract_index, verify_index)
        self.assertLess(verify_index, placement_index)
        self.assertEqual(result["destination"], "/storage/ABCD-1234/Roms/demo")

    def test_every_device_specific_adb_command_uses_manifest_serial(self):
        fixture, _result = self.create_plan()
        temp, _root, _source, adb_path, _seven_zip, manifest_path, runner = fixture
        runner.commands.clear()
        try:
            transfer.apply_transfer(
                manifest_path,
                confirm_transfer=True,
                keep_manifest=True,
                runner=runner,
            )
        finally:
            temp.cleanup()

        adb_commands = [command for command, _cwd in runner.commands if command[0] == str(adb_path)]
        for command in adb_commands:
            if command[1:] == ["devices", "-l"]:
                continue
            self.assertEqual(command[1:3], ["-s", "device-001"])

    def test_cleanup_refuses_unconfirmed_and_targets_only_manifest_stage(self):
        fixture, _result = self.create_plan()
        temp, _root, _source, _adb, _seven_zip, manifest_path, runner = fixture
        try:
            with self.assertRaises(transfer.TransferError) as raised:
                transfer.cleanup_transfer(manifest_path, confirm_cleanup=False, runner=runner)
            self.assertEqual(raised.exception.kind, "confirmation_required")

            runner.commands.clear()
            result = transfer.cleanup_transfer(manifest_path, confirm_cleanup=True, runner=runner)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        finally:
            temp.cleanup()

        cleanup_commands = [
            " ".join(command)
            for command, _cwd in runner.commands
            if "toybox rm" in " ".join(command)
        ]
        self.assertEqual(len(cleanup_commands), 1)
        self.assertIn(manifest["remote_stage"], cleanup_commands[0])
        self.assertNotIn(f"rm -rf -- {manifest['destination']}", cleanup_commands[0])
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
