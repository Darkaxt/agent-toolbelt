import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "everything" / "src"
for path in (CORE_SRC, FAMILY_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_toolbelt_everything import everything


class EverythingTests(unittest.TestCase):
    def test_resolve_es_executable_prefers_explicit_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_es = Path(temp_dir) / "es.exe"
            fake_es.write_text("placeholder", encoding="utf-8")

            resolved = everything.resolve_es_executable(explicit_path=str(fake_es))

        self.assertEqual(Path(resolved), fake_es)

    def test_global_mode_uses_everything_backend(self):
        original_resolver = everything.resolve_es_executable
        original_everything = everything.search_with_everything
        everything.resolve_es_executable = lambda explicit_path=None: "C:/Tools/es.exe"
        everything.search_with_everything = lambda **kwargs: {
            "ok": True,
            "backend": "everything",
            "query": kwargs["query"],
            "results": ["C:\\Program Files\\Everything\\Everything.exe"],
            "stderr": "",
            "exit_code": 0,
        }
        try:
            result = everything.lookup(query="Everything.exe", mode="global", max_results=5)
        finally:
            everything.resolve_es_executable = original_resolver
            everything.search_with_everything = original_everything

        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "everything")
        self.assertIn("Everything.exe", result["results"][0])

    def test_path_resolve_uses_where_backend(self):
        original_where = everything.search_with_where
        everything.search_with_where = lambda **kwargs: {
            "ok": True,
            "backend": "fallback-where",
            "query": kwargs["query"],
            "results": ["C:\\Tools\\claude.exe"],
            "stderr": "",
            "exit_code": 0,
        }
        try:
            result = everything.lookup(query="claude", mode="path-resolve")
        finally:
            everything.search_with_where = original_where

        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "fallback-where")
        self.assertIn("claude.exe", result["results"][0])

    def test_repo_local_uses_rg_backend(self):
        original_rg = everything.search_with_rg
        everything.search_with_rg = lambda **kwargs: {
            "ok": True,
            "backend": "fallback-rg",
            "query": kwargs["query"],
            "results": ["D:\\repo\\README.md"],
            "stderr": "",
            "exit_code": 0,
        }
        try:
            result = everything.lookup(query="README.md", mode="repo-local", root="D:\\repo")
        finally:
            everything.search_with_rg = original_rg

        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "fallback-rg")

    def test_missing_es_falls_back_cleanly(self):
        original_resolver = everything.resolve_es_executable
        original_ps = everything.search_with_powershell
        everything.resolve_es_executable = lambda explicit_path=None: None
        everything.search_with_powershell = lambda **kwargs: {
            "ok": True,
            "backend": "fallback-powershell",
            "query": kwargs["query"],
            "results": [],
            "stderr": "Everything CLI not available; searched only within the provided root.",
            "exit_code": 0,
        }
        try:
            result = everything.lookup(
                query="*.md",
                mode="global",
                root="D:\\repo",
                max_results=10,
            )
        finally:
            everything.resolve_es_executable = original_resolver
            everything.search_with_powershell = original_ps

        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "fallback-powershell")
        self.assertIn("Everything CLI not available", result["stderr"])

    def test_non_zero_es_exit_falls_back_cleanly(self):
        original_resolver = everything.resolve_es_executable
        original_everything = everything.search_with_everything
        original_ps = everything.search_with_powershell
        everything.resolve_es_executable = lambda explicit_path=None: "C:/Tools/es.exe"
        everything.search_with_everything = lambda **kwargs: {
            "ok": False,
            "backend": "everything",
            "query": kwargs["query"],
            "results": [],
            "stderr": "Everything CLI failed.",
            "exit_code": 2,
        }
        everything.search_with_powershell = lambda **kwargs: {
            "ok": True,
            "backend": "fallback-powershell",
            "query": kwargs["query"],
            "results": ["D:\\repo\\notes.md"],
            "stderr": "Everything CLI failed. Fell back to scoped PowerShell search.",
            "exit_code": 0,
        }
        try:
            result = everything.lookup(
                query="notes.md",
                mode="global",
                root="D:\\repo",
                max_results=5,
            )
        finally:
            everything.resolve_es_executable = original_resolver
            everything.search_with_everything = original_everything
            everything.search_with_powershell = original_ps

        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "fallback-powershell")
        self.assertIn("notes.md", result["results"][0])


if __name__ == "__main__":
    unittest.main()
