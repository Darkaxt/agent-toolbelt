from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


FAMILY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = FAMILY_ROOT / "codex" / "skills" / "context-transfer" / "scripts"


def load_script(name: str):
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(f"context_transfer_test_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def make_repo(root: Path) -> Path:
    family = root / "families" / "context-transfer"
    package = family / "src" / "agent_toolbelt_context_transfer"
    package.mkdir(parents=True)
    (root / "pyproject.toml").write_text("[tool.uv.workspace]\nmembers=[]\n", encoding="utf-8")
    (family / "pyproject.toml").write_text("[project]\nname='agent-toolbelt-context-transfer'\n", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text("def main(args=None): return 0\n", encoding="utf-8")
    cache = package / "__pycache__"
    cache.mkdir()
    (cache / "cli.pyc").write_bytes(b"generated")
    return root


class ContextTransferRuntimeTests(unittest.TestCase):
    def test_bootstrap_resolves_active_staged_runtime(self):
        module = load_script("runtime_bootstrap.py")
        with tempfile.TemporaryDirectory(dir=r"D:\Temp") as temp_dir:
            root = Path(temp_dir)
            codex_home = root / "codex-home"
            release = codex_home / "tools" / "context-transfer" / "releases" / "r1"
            python = release / ".venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"")
            (release / "src" / "agent_toolbelt_context_transfer").mkdir(parents=True)
            active = codex_home / "tools" / "context-transfer" / "active.json"
            active.parent.mkdir(parents=True, exist_ok=True)
            active.write_text(json.dumps({"release_root": str(release)}), encoding="utf-8")
            script = root / "installed" / "scripts" / "invoke_context_transfer.py"
            script.parent.mkdir(parents=True)
            script.write_text("", encoding="utf-8")

            target = module.resolve_execution_target(
                script_path=script,
                env={"CODEX_HOME": str(codex_home)},
            )

        self.assertEqual(target["mode"], "runtime")
        self.assertEqual(Path(target["runtime_python"]), python.resolve())
        self.assertEqual(Path(target["release_root"]), release.resolve())

    def test_bootstrap_prefers_explicit_repo_for_development(self):
        module = load_script("runtime_bootstrap.py")
        with tempfile.TemporaryDirectory(dir=r"D:\Temp") as temp_dir:
            root = Path(temp_dir)
            repo = make_repo(root / "repo")
            script = root / "installed" / "invoke.py"
            script.parent.mkdir(parents=True)
            script.write_text("", encoding="utf-8")

            target = module.resolve_execution_target(
                script_path=script,
                env={"AGENT_TOOLBELT_HOME": str(repo), "CODEX_HOME": str(root / "home")},
            )

        self.assertEqual(target["mode"], "repo")
        self.assertEqual(Path(target["repo_root"]), repo.resolve())

    def test_installer_activates_only_after_validation(self):
        installer = load_script("install_context_transfer_runtime.py")
        with tempfile.TemporaryDirectory(dir=r"D:\Temp") as temp_dir:
            root = Path(temp_dir)
            repo = make_repo(root / "repo")
            codex_home = root / "codex-home"
            observations = []

            def runner(command, env=None):
                observations.append(list(command))
                release = codex_home / "tools" / "context-transfer" / "releases" / "r1"
                python = release / ".venv" / "Scripts" / "python.exe"
                python.parent.mkdir(parents=True, exist_ok=True)
                python.write_bytes(b"")

            def validator(*, release_root, runner):
                self.assertFalse((codex_home / "tools" / "context-transfer" / "active.json").exists())
                self.assertTrue((release_root / "src" / "agent_toolbelt_context_transfer" / "cli.py").is_file())
                self.assertFalse((release_root / "src" / "agent_toolbelt_context_transfer" / "__pycache__").exists())

            active = installer.install_runtime(
                repo_root=repo,
                codex_home=codex_home,
                python_executable=Path("C:/Python/python.exe"),
                runner=runner,
                validator=validator,
                release_stamp="r1",
            )

            payload = json.loads(active.read_text(encoding="utf-8"))

        self.assertEqual(len(observations), 1)
        self.assertIn("-m", observations[0])
        self.assertIn("venv", observations[0])
        self.assertEqual(Path(payload["release_root"]), codex_home / "tools" / "context-transfer" / "releases" / "r1")

    def test_installer_uses_atomic_active_manifest(self):
        installer = load_script("install_context_transfer_runtime.py")
        source = (SCRIPTS / "install_context_transfer_runtime.py").read_text(encoding="utf-8")
        bootstrap = (SCRIPTS / "runtime_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn("os.replace", source)
        self.assertNotIn("timeout=", source)
        self.assertIn("PYTHONDONTWRITEBYTECODE", source)
        self.assertIn("PYTHONDONTWRITEBYTECODE", bootstrap)
        self.assertTrue(callable(installer.write_active_manifest))


if __name__ == "__main__":
    unittest.main()
