"""Rebuild assets/saf-client.dex from assets/SafClient.java.

Usage: python -B scripts/build_client_dex.py [--sdk <Android SDK>] [--scratch <dir>]

Requires a JDK (javac) and the Android SDK platform android-35 plus build-tools
with d8. Records the source SHA-256 in assets/saf-client.json so tests can detect
a stale dex. Run it whenever SafClient.java changes and commit both files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "src" / "agent_toolbelt_adb_saf" / "assets"
PLATFORM = "android-35"
MIN_API = "29"


def newest_build_tools(sdk: Path) -> Path:
    versions = sorted((p for p in (sdk / "build-tools").iterdir() if (p / "d8.bat").is_file() or (p / "d8").is_file()),
                      key=lambda p: [int(x) if x.isdigit() else 0 for x in p.name.split(".")])
    if not versions:
        raise SystemExit("No Android build-tools with d8 found")
    return versions[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk", default=os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
                        or str(Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk"))
    parser.add_argument("--scratch")
    args = parser.parse_args()
    sdk = Path(args.sdk)
    android_jar = sdk / "platforms" / PLATFORM / "android.jar"
    if not android_jar.is_file():
        raise SystemExit(f"Missing {android_jar}")
    tools = newest_build_tools(sdk)
    d8 = tools / ("d8.bat" if os.name == "nt" else "d8")
    javac = shutil.which("javac")
    if not javac:
        raise SystemExit("javac not found on PATH")
    source = ASSETS / "SafClient.java"
    with tempfile.TemporaryDirectory(dir=args.scratch) as work:
        classes = Path(work) / "classes"
        out = Path(work) / "dex"
        classes.mkdir()
        out.mkdir()
        subprocess.run([javac, "--release", "8", "-Xlint:-options", "-encoding", "UTF-8",
                        "-classpath", str(android_jar), "-d", str(classes), str(source)], check=True)
        class_files = [str(p) for p in sorted(classes.rglob("*.class"))]
        subprocess.run([str(d8), "--release", "--min-api", MIN_API, "--lib", str(android_jar),
                        "--output", str(out), *class_files], check=True)
        dex = (out / "classes.dex").read_bytes()
    (ASSETS / "saf-client.dex").write_bytes(dex)
    record = {
        "schema": 1,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "dex_sha256": hashlib.sha256(dex).hexdigest(),
        "platform": PLATFORM,
        "min_api": int(MIN_API),
        "build_tools": tools.name,
    }
    (ASSETS / "saf-client.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
