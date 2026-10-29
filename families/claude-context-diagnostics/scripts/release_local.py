"""Release the verified two-file skill bundle and install an identical Claude copy."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

VERSION = '0.1.0'
NAME = 'claude-context-diagnostics'
FILES = ('SKILL.md','scripts/context_diagnostics.py')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def install_tree(target, payload):
    if target.is_symlink() or any(p.is_symlink() for p in target.rglob('*')):
        raise RuntimeError('Linked destination preserved; installation refused.')
    if target.exists():
        actual = {p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}
        if actual != set(payload) or any((target/name).read_bytes() != data for name,data in payload.items()):
            raise RuntimeError('Existing destination differs; preserved without replacement.')
        return
    target.mkdir(parents=True,exist_ok=False)
    for name,data in payload.items():
        dest = target/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open('xb') as stream:
            stream.write(data)
    if any((target/name).read_bytes() != data for name,data in payload.items()):
        raise RuntimeError('Installed content verification failed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit',required=True)
    parser.add_argument('--release-root',type=Path,required=True)
    parser.add_argument('--claude-root',type=Path,required=True)
    args = parser.parse_args()
    if not re.fullmatch('[a-f0-9]{40}',args.source_commit):
        parser.error('Supply the exact verified source commit SHA.')
    repo = Path(__file__).resolve().parents[3]
    bundle = Path(__file__).resolve().parents[1]/'codex/skills'/NAME
    payload = {}
    for name in FILES:
        src = bundle/name
        data = src.read_bytes()
        committed = subprocess.check_output(['git','-C',str(repo),'show',f'{args.source_commit}:{src.relative_to(repo).as_posix()}'])
        if data != committed:
            raise RuntimeError('Source differs from the specified commit; release refused.')
        payload[name] = data
    manifest = {'name':NAME,'version':VERSION,'source_commit':args.source_commit,
                'files':{name:digest(data) for name,data in payload.items()}}
    manifest_bytes = (json.dumps(manifest,indent=2)+'\n').encode()
    released = {**payload,'release.json':manifest_bytes}
    release = args.release_root.resolve()/'releases'/VERSION
    installed = args.claude_root.resolve()/'skills'/NAME
    install_tree(release,released)
    install_tree(installed,released)
    receipt = {**manifest,'release_directory':str(release),'installed_directory':str(installed),'hashes_verified':True,
               'limits':'Installation and bytes verified; no running Claude session was messaged or restarted.'}
    receipt_path = args.release_root.resolve()/f'installation-{VERSION}.json'
    if receipt_path.exists() and json.loads(receipt_path.read_text()) != receipt:
        raise RuntimeError('A different installation receipt exists; preserved.')
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,indent=2))


if __name__ == '__main__':
    main()
