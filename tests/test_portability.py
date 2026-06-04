import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


FORBIDDEN_TOKENS = (
    "C:" + "\\Users\\" + "darka",
    "." + "codex",
    "." + "claude",
    "darka" + "-local",
)


class PortabilityTests(unittest.TestCase):
    def test_repo_contains_no_personal_machine_tokens(self):
        checked_extensions = {
            ".md",
            ".py",
            ".ps1",
            ".bat",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
        }

        offenders = []
        for path in REPO_ROOT.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in checked_extensions:
                continue
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_TOKENS:
                if token in text:
                    offenders.append(f"{path.relative_to(REPO_ROOT)} -> {token}")

        self.assertEqual(offenders, [])

    def test_bundled_assets_exclude_runtime_artifacts(self):
        forbidden_parts = {
            ".venv",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "browser-profiles",
            "sessions",
        }
        forbidden_names = {
            "Cookies",
            "Local State",
            "uv.lock",
            "todo.md",
            "derived_todo.md",
        }
        forbidden_suffixes = {
            ".db",
            ".sqlite",
            ".sqlite3",
            ".ldb",
            ".log",
            ".pyc",
            ".pyo",
        }
        asset_roots = [
            REPO_ROOT
            / "families"
            / "amazon-cli"
            / "src"
            / "agent_toolbelt_amazon_cli"
            / "assets"
            / "amazon-intent-cli",
            REPO_ROOT
            / "families"
            / "skroutz-cli"
            / "src"
            / "agent_toolbelt_skroutz_cli"
            / "assets"
            / "skroutz-intent-cli",
            REPO_ROOT
            / "families"
            / "aliexpress-cli"
            / "src"
            / "agent_toolbelt_aliexpress_cli"
            / "assets"
            / "aliexpress-intent-cli",
        ]

        offenders = []
        for asset_root in asset_roots:
            if not asset_root.exists():
                continue
            for path in asset_root.rglob("*"):
                relative = path.relative_to(REPO_ROOT)
                if any(part in forbidden_parts for part in relative.parts):
                    offenders.append(str(relative))
                if path.name in forbidden_names:
                    offenders.append(str(relative))
                if path.is_file() and path.suffix.lower() in forbidden_suffixes:
                    offenders.append(str(relative))

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
