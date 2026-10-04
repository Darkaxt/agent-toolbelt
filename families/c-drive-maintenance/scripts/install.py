"""Deploy immutable helper code and identical personal skills; no user state."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
FAMILY = Path(__file__).resolve().parents[1]
PACKAGE = 'agent_toolbelt_c_drive_maintenance'


def check_chain(path):
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if part.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Refusing linked deployment path: ' + str(part))


def install(home=None, local_appdata=None):
    home = Path(home or Path.home()).absolute()
    local = Path(local_appdata or os.environ.get('LOCALAPPDATA', home / '.local/share')).absolute()
    source = FAMILY / 'src'
    files = sorted((source / PACKAGE).glob('*.py'))
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    root = local / 'Tools/c-drive-maintenance'
    runtime = root / 'releases' / digest.hexdigest()[:16] / 'src'
    skill_source = FAMILY / 'codex/skills/c-drive-maintenance'
    destinations = [home / agent / 'skills/c-drive-maintenance' for agent in ('.codex', '.agents', '.claude')]
    check_chain(root)
    for destination in destinations:
        for path in skill_source.rglob('*'):
            if path.is_file():
                check_chain(destination / path.relative_to(skill_source))
    for path in files:
        target = runtime / PACKAGE / path.name
        check_chain(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != path.read_bytes():
            raise ValueError('Immutable installed runtime does not match source')
        if not target.exists():
            shutil.copy2(path, target)
    subprocess.run([sys.executable, '-B', '-m', PACKAGE + '.cli', '--help'],
                   env={**os.environ, 'PYTHONPATH': str(runtime)}, capture_output=True, check=True)
    for destination in destinations:
        for path in skill_source.rglob('*'):
            if path.is_file() and path.suffix in {'.py', '.md', '.yaml'}:
                target = destination / path.relative_to(skill_source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
    pointer = root / 'active.json'
    check_chain(pointer)
    pending = root / (uuid.uuid4().hex + '.pending')
    pending.write_text(json.dumps({'version': '0.1.1', 'source': str(runtime)}), encoding='utf-8')
    os.replace(pending, pointer)
    return {'ok': True, 'runtime': str(runtime), 'skills': [str(p) for p in destinations]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--home')
    parser.add_argument('--local-appdata')
    args = parser.parse_args()
    print(json.dumps(install(args.home, args.local_appdata), indent=2))
