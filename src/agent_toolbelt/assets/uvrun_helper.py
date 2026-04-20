#!/usr/bin/env python3
"""
Helper script for uvrun: detect file-local dependencies and add inline metadata.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path


PACKAGE_MAPPINGS = {
    "PIL": "Pillow",
    "OpenSSL": "pyOpenSSL",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
}

STDLIB_MODULES = {
    "__future__",
    "__main__",
    "abc",
    "aifc",
    "argparse",
    "array",
    "ast",
    "asynchat",
    "asyncio",
    "asyncore",
    "atexit",
    "audioop",
    "base64",
    "bdb",
    "binascii",
    "bisect",
    "builtins",
    "bz2",
    "calendar",
    "cgi",
    "cgitb",
    "chunk",
    "cmath",
    "cmd",
    "code",
    "codecs",
    "codeop",
    "collections",
    "colorsys",
    "compileall",
    "concurrent",
    "configparser",
    "contextlib",
    "contextvars",
    "copy",
    "copyreg",
    "crypt",
    "csv",
    "ctypes",
    "curses",
    "dataclasses",
    "datetime",
    "dbm",
    "decimal",
    "difflib",
    "dis",
    "distutils",
    "doctest",
    "email",
    "encodings",
    "enum",
    "errno",
    "faulthandler",
    "fcntl",
    "filecmp",
    "fileinput",
    "fnmatch",
    "fractions",
    "ftplib",
    "functools",
    "gc",
    "getopt",
    "getpass",
    "gettext",
    "glob",
    "graphlib",
    "grp",
    "gzip",
    "hashlib",
    "heapq",
    "hmac",
    "html",
    "http",
    "imaplib",
    "imghdr",
    "imp",
    "importlib",
    "inspect",
    "io",
    "ipaddress",
    "itertools",
    "json",
    "keyword",
    "lib2to3",
    "linecache",
    "locale",
    "logging",
    "lzma",
    "mailbox",
    "mailcap",
    "marshal",
    "math",
    "mimetypes",
    "mmap",
    "modulefinder",
    "msilib",
    "msvcrt",
    "multiprocessing",
    "netrc",
    "nis",
    "nntplib",
    "numbers",
    "operator",
    "optparse",
    "os",
    "ossaudiodev",
    "pathlib",
    "pdb",
    "pickle",
    "pickletools",
    "pipes",
    "pkgutil",
    "platform",
    "plistlib",
    "poplib",
    "posix",
    "posixpath",
    "pprint",
    "profile",
    "pstats",
    "pty",
    "pwd",
    "py_compile",
    "pyclbr",
    "pydoc",
    "queue",
    "quopri",
    "random",
    "re",
    "readline",
    "reprlib",
    "resource",
    "rlcompleter",
    "runpy",
    "sched",
    "secrets",
    "select",
    "selectors",
    "shelve",
    "shlex",
    "shutil",
    "signal",
    "site",
    "smtpd",
    "smtplib",
    "sndhdr",
    "socket",
    "socketserver",
    "spwd",
    "sqlite3",
    "ssl",
    "stat",
    "statistics",
    "string",
    "stringprep",
    "struct",
    "subprocess",
    "sunau",
    "symtable",
    "sys",
    "sysconfig",
    "syslog",
    "tabnanny",
    "tarfile",
    "telnetlib",
    "tempfile",
    "termios",
    "test",
    "textwrap",
    "threading",
    "time",
    "timeit",
    "tkinter",
    "token",
    "tokenize",
    "trace",
    "traceback",
    "tracemalloc",
    "tty",
    "turtle",
    "turtledemo",
    "types",
    "typing",
    "unicodedata",
    "unittest",
    "urllib",
    "uu",
    "uuid",
    "venv",
    "warnings",
    "wave",
    "weakref",
    "webbrowser",
    "winreg",
    "winsound",
    "wsgiref",
    "xdrlib",
    "xml",
    "xmlrpc",
    "zipapp",
    "zipfile",
    "zipimport",
    "zlib",
    "zoneinfo",
}

if hasattr(sys, "stdlib_module_names"):
    STDLIB_MODULES = STDLIB_MODULES | set(sys.stdlib_module_names)

ENCODING_COOKIE_RE = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)")


def has_inline_metadata(filepath: Path | str) -> bool:
    try:
        content = Path(filepath).read_text(encoding="utf-8")
    except OSError:
        return False
    return "# /// script" in content


def is_encoding_cookie(line: str) -> bool:
    return bool(ENCODING_COOKIE_RE.match(line))


def detect_dependencies(filepath: Path | str) -> list[str]:
    path = Path(filepath)
    try:
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except Exception as exc:
        print(f"Warning: Could not parse {path}: {exc}", file=sys.stderr)
        return []

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if node.module:
                imports.add(node.module.split(".")[0])

    third_party = imports - STDLIB_MODULES
    mapped = {PACKAGE_MAPPINGS.get(module_name, module_name) for module_name in third_party}
    return sorted(mapped)


def compute_requires_python() -> str:
    return f">={sys.version_info.major}.{sys.version_info.minor}"


def build_metadata_block(
    dependencies: list[str],
    requires_python: str | None = None,
) -> str:
    requires = requires_python or compute_requires_python()
    metadata_lines = [
        "# /// script",
        f'# requires-python = "{requires}"',
    ]
    if dependencies:
        metadata_lines.append("# dependencies = [")
        for dependency in sorted(set(dependencies)):
            metadata_lines.append(f'#   "{dependency}",')
        metadata_lines.append("# ]")
    else:
        metadata_lines.append("# dependencies = []")
    metadata_lines.append("# ///")
    return "\n".join(metadata_lines) + "\n\n"


def split_leading_prefix(content: str) -> tuple[str, str]:
    lines = content.splitlines(keepends=True)
    prefix: list[str] = []
    index = 0

    if lines and lines[0].startswith("#!"):
        prefix.append(lines[0])
        index = 1
        if len(lines) > 1 and is_encoding_cookie(lines[1]):
            prefix.append(lines[1])
            index = 2
    elif lines and is_encoding_cookie(lines[0]):
        prefix.append(lines[0])
        index = 1

    prefix_text = "".join(prefix)
    if prefix_text and not prefix_text.endswith(("\n", "\r")):
        prefix_text += "\n"
    remainder = "".join(lines[index:])
    return prefix_text, remainder


def add_inline_metadata(
    filepath: Path | str,
    dependencies: list[str],
    requires_python: str | None = None,
) -> bool:
    path = Path(filepath)
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error reading {path}: {exc}", file=sys.stderr)
        return False

    prefix_text, remainder = split_leading_prefix(content)
    new_content = prefix_text + build_metadata_block(dependencies, requires_python) + remainder

    try:
        path.write_text(new_content, encoding="utf-8")
        return True
    except OSError as exc:
        print(f"Error writing {path}: {exc}", file=sys.stderr)
        return False


def ensure_inline_metadata(filepath: Path | str) -> tuple[bool, list[str]]:
    path = Path(filepath)
    if has_inline_metadata(path):
        return False, []

    dependencies = detect_dependencies(path)
    changed = add_inline_metadata(path, dependencies, compute_requires_python())
    return changed, dependencies


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: uvrun_helper.py <script.py>", file=sys.stderr)
        raise SystemExit(1)

    script_path = Path(sys.argv[1])
    if not script_path.exists():
        print(f"Error: {script_path} not found", file=sys.stderr)
        raise SystemExit(1)

    if has_inline_metadata(script_path):
        print(f"[OK] {script_path.name} already has inline metadata")
        raise SystemExit(0)

    print(f"Analyzing imports in {script_path.name}...")
    dependencies = detect_dependencies(script_path)
    if dependencies:
        print(f"Found dependencies: {', '.join(dependencies)}")
    else:
        print("No third-party dependencies detected")

    print("Adding inline metadata...")
    if add_inline_metadata(script_path, dependencies, compute_requires_python()):
        print(f"Updated {script_path.name}")
        raise SystemExit(0)

    raise SystemExit(1)


if __name__ == "__main__":
    main()
