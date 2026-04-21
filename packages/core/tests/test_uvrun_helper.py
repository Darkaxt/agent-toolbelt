import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from agent_toolbelt_core.assets import uvrun_helper


class UVRunHelperTests(unittest.TestCase):
    def write_script(self, directory: str, name: str, content: str) -> Path:
        path = Path(directory) / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_existing_inline_metadata_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            script = self.write_script(
                temp_dir,
                "already_tagged.py",
                "# /// script\n# requires-python = \">=3.11\"\n# dependencies = []\n# ///\n\nprint('ok')\n",
            )
            before = script.read_text(encoding="utf-8")

            changed, dependencies = uvrun_helper.ensure_inline_metadata(script)

            self.assertFalse(changed)
            self.assertEqual(dependencies, [])
            self.assertEqual(script.read_text(encoding="utf-8"), before)

    def test_shebang_is_preserved_before_inserted_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            script = self.write_script(
                temp_dir,
                "shebang_script.py",
                "#!/usr/bin/env python3\nprint('ok')\n",
            )

            changed, _ = uvrun_helper.ensure_inline_metadata(script)
            lines = script.read_text(encoding="utf-8").splitlines()

            self.assertTrue(changed)
            self.assertEqual(lines[0], "#!/usr/bin/env python3")
            self.assertEqual(lines[1], "# /// script")

    def test_encoding_cookie_stays_in_valid_position(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            script = self.write_script(
                temp_dir,
                "encoding_script.py",
                "# -*- coding: utf-8 -*-\nprint('ok')\n",
            )

            changed, _ = uvrun_helper.ensure_inline_metadata(script)
            lines = script.read_text(encoding="utf-8").splitlines()

            self.assertTrue(changed)
            self.assertEqual(lines[0], "# -*- coding: utf-8 -*-")
            self.assertEqual(lines[1], "# /// script")

    def test_requires_python_header_is_added_from_running_interpreter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            script = self.write_script(
                temp_dir,
                "requests_script.py",
                "import requests\nprint('ok')\n",
            )

            changed, _ = uvrun_helper.ensure_inline_metadata(script)
            content = script.read_text(encoding="utf-8")

            self.assertTrue(changed)
            self.assertIn(
                f'# requires-python = ">={sys.version_info.major}.{sys.version_info.minor}"',
                content,
            )

    def test_dependencies_are_sorted_deduplicated_and_mapped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            script = self.write_script(
                temp_dir,
                "deps_script.py",
                (
                    "import requests\n"
                    "import yaml\n"
                    "from bs4 import BeautifulSoup\n"
                    "import requests\n"
                ),
            )

            dependencies = uvrun_helper.detect_dependencies(script)

            self.assertEqual(dependencies, ["PyYAML", "beautifulsoup4", "requests"])

    def test_dependency_detection_does_not_bleed_from_neighboring_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            script = self.write_script(
                temp_dir,
                "target.py",
                "import requests\nprint('ok')\n",
            )
            self.write_script(
                temp_dir,
                "neighbor.py",
                "import pandas\nprint('neighbor')\n",
            )

            dependencies = uvrun_helper.detect_dependencies(script)

            self.assertEqual(dependencies, ["requests"])


if __name__ == "__main__":
    unittest.main()
