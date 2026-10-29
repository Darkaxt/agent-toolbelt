"""Release the verified two-file skill bundle and install an identical Claude copy."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

VERSION = '0.1.1'
NAME = 'claude-context-diagnostics'
FILES = ('SKILL.md','scripts/context_diagnostics.py')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_locked(stream, data):
    stream.seek(0);stream.write(data);stream.truncate();stream.flush();os.fsync(stream.fileno())


def upgrade_tree(target, payload, previous):
    """Pin all existing files against readers/writers until the bundle settles."""
    if os.name != 'nt':
        raise RuntimeError('Verified existing-bundle upgrades require Windows; destination preserved.')
    import ctypes
    from ctypes import wintypes as w
    import msvcrt
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,ctypes.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
    kernel.CreateFileW.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE]
    kernel.GetFileInformationByHandleEx.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
    def opened(path,access,share,directory=False):
        handle=kernel.CreateFileW(str(path),access,share,None,3,0x200000|(0x2000000 if directory else 0),None)
        if handle==w.HANDLE(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        attributes=(w.DWORD*2)()
        if not kernel.GetFileInformationByHandleEx(handle,9,ctypes.byref(attributes),ctypes.sizeof(attributes)):
            error=ctypes.WinError(ctypes.get_last_error());kernel.CloseHandle(handle);raise error
        if attributes[0]&0x400 or bool(attributes[0]&0x10)!=directory:
            kernel.CloseHandle(handle);raise RuntimeError('Redirected or unexpected upgrade target preserved.')
        return handle
    if set(previous)!=set(payload):raise RuntimeError('Upgrade file sets differ; destination preserved.')
    with ExitStack() as stack:
        directory=opened(target,0x80000000,3,True)
        stack.callback(kernel.CloseHandle,directory)
        for parent in sorted({(target/name).parent for name in payload}-{target}):
            directory=opened(parent,0x80000000,3,True)
            stack.callback(kernel.CloseHandle,directory)
        if {p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}!=set(payload):
            raise RuntimeError('Unknown installed files preserved; upgrade refused.')
        streams={}
        for name in payload:
            handle=opened(target/name,0xc0000000,0)
            try:fd=msvcrt.open_osfhandle(handle,os.O_RDWR|os.O_BINARY)
            except BaseException:kernel.CloseHandle(handle);raise
            stream=stack.enter_context(os.fdopen(fd,'r+b'))
            if os.fstat(stream.fileno()).st_nlink!=1 or stream.read()!=previous[name]:
                raise RuntimeError('Installed edits or unexpected links preserved; upgrade refused.')
            streams[name]=stream
        # All members are exclusively pinned before any mutation. Readers never
        # consume a partial bundle; pre-existing/concurrent writers fail admission.
        try:
            for name,data in payload.items():write_locked(streams[name],data)
            for name,data in payload.items():
                streams[name].seek(0)
                if streams[name].read()!=data:raise RuntimeError('Upgraded bytes failed verification.')
        except BaseException:
            for name,data in previous.items():write_locked(streams[name],data)
            raise


def install_tree(target, payload, previous=None):
    if target.is_symlink() or any(p.is_symlink() for p in target.rglob('*')):
        raise RuntimeError('Linked destination preserved; installation refused.')
    if target.exists():
        actual = {p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}
        if actual != set(payload):
            raise RuntimeError('Existing destination differs; preserved without replacement.')
        if any((target/name).read_bytes()!=data for name,data in payload.items()):
            if previous is None:
                raise RuntimeError('Existing destination differs; preserved without replacement.')
            upgrade_tree(target,payload,previous)
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
    parser.add_argument('--upgrade-from',help='Exact retained release version used to verify the installed previous bundle')
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
    previous=None
    if args.upgrade_from:
        if not re.fullmatch(r'\d+\.\d+\.\d+',args.upgrade_from):parser.error('Invalid prior release version.')
        prior=args.release_root.resolve()/'releases'/args.upgrade_from
        raw_manifest=(prior/'release.json').read_bytes();old=json.loads(raw_manifest)
        if old.get('name')!=NAME or old.get('version')!=args.upgrade_from or set(old.get('files',{}))!=set(FILES):
            raise RuntimeError('Prior release manifest does not identify this exact bundle.')
        previous={name:(prior/name).read_bytes() for name in FILES}
        if any(digest(data)!=old['files'][name] for name,data in previous.items()):
            raise RuntimeError('Prior release content differs; upgrade refused.')
        previous['release.json']=raw_manifest
    install_tree(release,released)
    install_tree(installed,released,previous)
    install_tree(installed,released)  # Independent read-back after exclusive handles close.
    receipt = {**manifest,'release_directory':str(release),'installed_directory':str(installed),'hashes_verified':True,
               'limits':'Installation and bytes verified; no running Claude session was messaged or restarted.'}
    receipt_path = args.release_root.resolve()/f'installation-{VERSION}.json'
    if receipt_path.exists() and json.loads(receipt_path.read_text()) != receipt:
        raise RuntimeError('A different installation receipt exists; preserved.')
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,indent=2))


if __name__ == '__main__':
    main()
