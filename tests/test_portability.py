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


if __name__ == "__main__":
    unittest.main()
