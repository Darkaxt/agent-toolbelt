import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

CHECKED_SUFFIXES = {".md", ".py", ".json", ".toml", ".yaml", ".yml"}
FAMILY_NAMES = (
    "gemini",
    "everything",
    "media",
    "outlook-classic-mail",
    "amazon-cli",
    "linkedin-cv",
    "codex-thread-recall",
    "whatsapp-wacli",
    "skills-sh-scout",
)


class FamilyIsolationTests(unittest.TestCase):
    def test_family_files_do_not_reference_unrelated_family_folders(self):
        offenders: list[str] = []

        for family_name in FAMILY_NAMES:
            family_root = REPO_ROOT / "families" / family_name
            other_family_tokens = {
                f"families/{other_name}"
                for other_name in FAMILY_NAMES
                if other_name != family_name
            }

            for path in family_root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in CHECKED_SUFFIXES:
                    continue
                text = path.read_text(encoding="utf-8")
                for token in other_family_tokens:
                    if token in text.replace("\\", "/"):
                        offenders.append(f"{path.relative_to(REPO_ROOT)} -> {token}")

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
