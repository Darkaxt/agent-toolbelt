import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "uvrun" / "src"
for path in (CORE_SRC, FAMILY_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_toolbelt_uvrun import uvrun


class UVRunTests(unittest.TestCase):
    def test_resolve_uvrun_executable_prefers_packaged_powershell_launcher(self):
        resolved = uvrun.resolve_uvrun_executable()
        self.assertEqual(resolved.suffix.lower(), ".ps1")
        self.assertTrue(resolved.exists())
        self.assertIn("uvrun.ps1", str(resolved))

    def test_eligible_script_uses_uvrun_ps1_backend(self):
        original_uv = uvrun.resolve_uv_executable
        original_ps = uvrun.resolve_powershell_executable
        uvrun.resolve_uv_executable = lambda: "C:/Tools/uv.exe"
        uvrun.resolve_powershell_executable = lambda: "powershell.exe"
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                script = Path(temp_dir) / "scratch.py"
                script.write_text("print('ok')\n", encoding="utf-8")
                result = uvrun.plan_execution(script=str(script))
        finally:
            uvrun.resolve_uv_executable = original_uv
            uvrun.resolve_powershell_executable = original_ps

        self.assertTrue(result["eligible"])
        self.assertEqual(result["backend"], "uvrun")
        self.assertEqual(result["command"][0].lower(), "powershell.exe")
        self.assertIn("-File", result["command"])
        self.assertIn("uvrun.ps1", " ".join(result["command"]))
        self.assertIn("uvrun.ps1", result["reason"])

    def test_preserves_query_string_argument_as_single_arg(self):
        original_uv = uvrun.resolve_uv_executable
        original_ps = uvrun.resolve_powershell_executable
        uvrun.resolve_uv_executable = lambda: "C:/Tools/uv.exe"
        uvrun.resolve_powershell_executable = lambda: "powershell.exe"
        try:
            url = "https://www.youtube.com/watch?v=KFisvc-AMII"
            with tempfile.TemporaryDirectory() as temp_dir:
                script = Path(temp_dir) / "scratch.py"
                script.write_text("print('ok')\n", encoding="utf-8")
                result = uvrun.plan_execution(script=str(script), script_args=[url])
        finally:
            uvrun.resolve_uv_executable = original_uv
            uvrun.resolve_powershell_executable = original_ps

        self.assertEqual(result["command"][-1], url)

    def test_falls_back_to_deprecated_batch_launcher_when_ps1_unavailable(self):
        original_uv = uvrun.resolve_uv_executable
        original_ps = uvrun.resolve_powershell_executable
        uvrun.resolve_uv_executable = lambda: "C:/Tools/uv.exe"
        uvrun.resolve_powershell_executable = lambda: None
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                script = Path(temp_dir) / "scratch.py"
                script.write_text("print('ok')\n", encoding="utf-8")
                result = uvrun.plan_execution(script=str(script))
        finally:
            uvrun.resolve_uv_executable = original_uv
            uvrun.resolve_powershell_executable = original_ps

        self.assertTrue(result["eligible"])
        self.assertEqual(result["backend"], "uvrun-batch-compat")
        self.assertEqual(result["command"][0].lower(), "cmd.exe")
        self.assertIn("deprecated", result["reason"])

    def test_project_managed_script_uses_direct_python_backend(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
            script = root / "tool.py"
            script.write_text("print('ok')\n", encoding="utf-8")

            result = uvrun.plan_execution(script=str(script))

        self.assertFalse(result["eligible"])
        self.assertEqual(result["backend"], "direct-python")
        self.assertIn("project-managed", result["reason"])

    def test_missing_uv_or_uvrun_falls_back_cleanly(self):
        original_uv = uvrun.resolve_uv_executable
        original_ps = uvrun.resolve_powershell_executable
        uvrun.resolve_uv_executable = lambda: None
        uvrun.resolve_powershell_executable = lambda: None
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                script = Path(temp_dir) / "scratch.py"
                script.write_text("print('ok')\n", encoding="utf-8")
                result = uvrun.plan_execution(script=str(script))
        finally:
            uvrun.resolve_uv_executable = original_uv
            uvrun.resolve_powershell_executable = original_ps

        self.assertTrue(result["eligible"])
        self.assertEqual(result["backend"], "direct-python")
        self.assertIn("uv path was unavailable", result["reason"])

    def test_nearby_git_directory_counts_as_project_managed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()
            script = root / "tool.py"
            script.write_text("print('ok')\n", encoding="utf-8")

            result = uvrun.plan_execution(script=str(script))

        self.assertFalse(result["eligible"])
        self.assertEqual(result["backend"], "direct-python")
        self.assertIn(".git", result["reason"])

    def test_cli_parses_wrapper_flags_after_script(self):
        args = uvrun.parse_args(["demo.py", "--check", "--json"])

        self.assertEqual(args.script, "demo.py")
        self.assertTrue(args.check)
        self.assertTrue(args.json)
        self.assertEqual(args.script_args, [])


if __name__ == "__main__":
    unittest.main()
