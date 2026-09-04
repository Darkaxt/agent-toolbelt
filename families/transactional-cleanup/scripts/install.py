from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
FAMILY = Path(__file__).resolve().parents[1]
PACKAGE = 'agent_toolbelt_transactional_cleanup'
sys.path.insert(0, str(FAMILY / 'src'))
from agent_toolbelt_transactional_cleanup import filesystem as fs


def copy_sources(source, destination):
    fs.check_chain(source)
    fs.check_chain(destination)
    for path in source.rglob('*'):
        fs.check_chain(path)
        fs.check_chain(destination / path.relative_to(source))
    shutil.copytree(source, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))


def install(home=None, local=None):
    home = fs.canonical(home or Path.home())
    local = fs.canonical(local or os.environ.get('LOCALAPPDATA', home / '.local/share'))
    root = local / 'Tools/transactional-cleanup'
    release = root / 'releases' / secrets.token_hex(16)
    source = release / 'src'
    destinations = [home / folder / 'skills/transactional-cleanup' for folder in ('.codex', '.agents', '.claude')]
    for path in [root / 'active.json', root / 'active.pending', *destinations]:
        fs.check_chain(path)
        if path.is_dir():
            for child in path.rglob('*'):
                fs.check_chain(child)
    copy_sources(FAMILY / 'src', source)
    environment = dict(os.environ, PYTHONPATH=str(source), PYTHONDONTWRITEBYTECODE='1')
    # A failed smoke test never activates the release.
    try:
        subprocess.run([sys.executable, '-B', '-m', PACKAGE + '.cli', '--help'],
                       env=environment, check=True, capture_output=True)
    except Exception:
        for path in source.rglob('*.py'):
            path.unlink()
        for path in sorted(source.rglob('*'), key=lambda p: len(p.parts), reverse=True):
            if path.is_dir():
                path.rmdir()
        source.rmdir()
        release.rmdir()
        raise
    hashes = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source.rglob('*.py')}
    active_path = root / 'active.json'
    previous = json.loads(active_path.read_text()) if active_path.exists() else None
    metadata = {'source': str(source), 'hashes': hashes}
    (release / 'release.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    skill_source = FAMILY / 'codex/skills/transactional-cleanup'
    for destination in destinations:
        copy_sources(skill_source, destination)
    temporary = root / 'active.pending'
    temporary.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    os.replace(temporary, active_path)
    # Retire only unchanged files explicitly listed by the preceding deployment.
    residuals = []
    if previous:
        old = Path(previous['source'])
        if old.parent.parent == root / 'releases' and old != source and not old.is_symlink():
            fs.check_chain(old)
            for relative, expected in previous.get('hashes', {}).items():
                path = old / relative
                fs.check_chain(path)
                if path.resolve().is_relative_to(old.resolve()) and path.is_file():
                    if hashlib.sha256(path.read_bytes()).hexdigest() == expected:
                        path.unlink()
                    else:
                        residuals.append(str(path))
            for path in sorted(old.rglob('*'), key=lambda p: len(p.parts), reverse=True):
                if path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
            if not any(old.iterdir()):
                old.rmdir()
                (old.parent / 'release.json').unlink(missing_ok=True)
                old.parent.rmdir()
    return {'ok': True, 'active_runtime': str(source), 'skills': [str(p) for p in destinations],
            'deployment_residuals': residuals}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--home')
    parser.add_argument('--local-appdata')
    args = parser.parse_args()
    print(json.dumps(install(args.home, args.local_appdata), indent=2))
