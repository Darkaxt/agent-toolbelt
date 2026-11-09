"""Read-only Git ownership proof and narrow linked-worktree finalization."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess

from . import filesystem as fs
from . import retirement


class WorktreeError(ValueError):
    def __init__(self, kind, message):
        self.kind = kind
        super().__init__(message)


def git(root, *arguments, common=False):
    environment = {key: value for key, value in os.environ.items() if key not in {
        'GIT_DIR', 'GIT_COMMON_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE',
        'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'}}
    command = ['git', '-c', 'core.fsmonitor=false', '-c', 'gc.auto=0', '-c', 'maintenance.auto=false']
    command += ['--git-dir', str(root)] if common else ['-C', str(root)]
    result = subprocess.run([*command, *arguments], env={**environment, 'GIT_OPTIONAL_LOCKS': '0'},
        capture_output=True, text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise WorktreeError('worktree_git_error', f'Git verification failed: {arguments[0]} ({result.returncode})')
    return result.stdout


def identity(path, expected=None):
    fs.check_chain(path)
    info = fs.identity(path)
    if not info['directory'] or info['reparse'] or info['filesystem'] not in {'NTFS', 'ReFS'}:
        raise WorktreeError('worktree_identity_required', 'A normal NTFS/ReFS directory is required')
    if expected is not None and info['identity'] != expected:
        raise WorktreeError('worktree_replaced', 'The reviewed worktree or Git metadata directory was replaced')
    return info['identity']


def retained(common, head):
    refs = git(common, 'for-each-ref', '--contains', head, '--format=%(refname)', common=True).splitlines()
    if not any(ref.startswith(('refs/heads/', 'refs/tags/', 'refs/remotes/')) for ref in refs):
        raise WorktreeError('worktree_unretained_head', 'Commit the result to a retained common ref before retiring this worktree')


def validate(root, temp_roots, expected=None, require_git=True, restored=None):
    root = fs.canonical(root)
    if not any(root != fs.canonical(temp) and fs.within(root, fs.canonical(temp)) for temp in temp_roots):
        raise WorktreeError('worktree_location', 'Use the exact task-owned temporary worktree root')
    if expected and not require_git:
        identity(Path(expected['common']), expected['common_identity'])
        retained(Path(expected['common']), expected['head'])
        if os.path.lexists(root):
            identity(root, expected['root_identity'])
            marker = root/'.git'
            if marker.exists():
                current = fs.identity(marker)
                allowed = restored['identity'] if restored else expected['marker_identity']
                if current['identity'] != allowed or marker.read_bytes().decode('utf-8') != expected['marker_text']:
                    raise WorktreeError('worktree_review_required', 'Git marker was restored or replaced; create a fresh review')
        metadata = Path(expected['metadata'])
        if os.path.lexists(metadata):
            identity(metadata, expected['metadata_identity'])
            if (metadata/'locked').exists() or any(metadata.glob('*.lock')):
                raise WorktreeError('worktree_locked', 'An active Git lock is present')
        if retirement.active_processes(root) or retirement.active_processes(metadata):
            raise WorktreeError('worktree_active_consumers', 'A live process references the worktree')
        return expected
    root_identity = identity(root, expected['root_identity'] if expected else None)
    marker = root/'.git'
    fs.check_chain(marker)
    if not marker.is_file():
        raise WorktreeError('worktree_marker_required', 'A real linked-worktree .git file is required')
    marker_info = fs.identity(marker)
    if marker_info['links'] != 1 or marker_info['reparse']:
        raise WorktreeError('worktree_marker_required', 'The Git marker must be an ordinary unshared file')
    marker_text = marker.read_bytes().decode('utf-8')
    if not marker_text.startswith('gitdir:') or len(marker_text.splitlines()) != 1:
        raise WorktreeError('worktree_marker_invalid', 'Invalid Git worktree marker')
    metadata = fs.canonical(root/marker_text.removeprefix('gitdir:').strip())
    metadata_identity = identity(metadata)
    fs.check_chain(metadata/'commondir')
    common = fs.canonical(metadata/(metadata/'commondir').read_text(encoding='utf-8').strip())
    if metadata.parent != common/'worktrees' or not metadata.name:
        raise WorktreeError('worktree_metadata_invalid', 'Only this worktree private administrative directory is eligible')
    common_identity = identity(common)
    fs.check_chain(metadata/'gitdir')
    if fs.canonical((metadata/'gitdir').read_text(encoding='utf-8').strip()) != marker:
        raise WorktreeError('worktree_metadata_invalid', 'Git metadata does not point back to this exact marker')
    if (metadata/'locked').exists() or any(metadata.glob('*.lock')):
        raise WorktreeError('worktree_locked', 'A retained worktree or an active Git lock is present')
    if fs.canonical(git(root, 'rev-parse', '--show-toplevel').strip()) != root:
        raise WorktreeError('worktree_root_mismatch', 'Git reports a different working root')
    if fs.canonical(git(root, 'rev-parse', '--absolute-git-dir').strip()) != metadata:
        raise WorktreeError('worktree_metadata_invalid', 'Git reports a different private directory')
    if git(root, 'status', '--porcelain=v1', '--untracked-files=all').strip():
        raise WorktreeError('worktree_dirty', 'Preserve uncommitted or untracked work; this worktree is not finished')
    if any(line.startswith('160000 ') for line in git(root, 'ls-files', '--stage').splitlines()):
        raise WorktreeError('worktree_submodules', 'Submodule working data needs its own ownership review')
    head = git(root, 'rev-parse', 'HEAD').strip()
    retained(common, head)
    if retirement.active_processes(root) or retirement.active_processes(metadata):
        raise WorktreeError('worktree_active_consumers', 'A live process references this worktree or its private metadata')
    proof = {'root': str(root), 'root_identity': root_identity, 'metadata': str(metadata),
        'metadata_identity': metadata_identity, 'common': str(common), 'common_identity': common_identity,
        'head': head, 'marker_identity': marker_info['identity'], 'marker_text': marker_text}
    if expected and proof != expected:
        raise WorktreeError('worktree_changed', 'The linked-worktree ownership proof changed; review afresh')
    return proof


def before_member(item, proof):
    root = Path(proof['root'])
    path = Path(item['path'])
    if item.get('worktree_phase') == 2:
        return 'not_empty' if os.path.lexists(root) else None
    if path == root/'.git' and root.exists():
        if any(child.name != '.git' for child in root.iterdir()):
            return 'not_empty'
    return None


def restore_marker_if_needed(proof):
    root = Path(proof['root'])
    if not os.path.lexists(root):
        return
    identity(root, proof['root_identity'])
    marker = root/'.git'
    if not os.path.lexists(marker):
        # A new arrival prevented empty-directory removal after unlinking the
        # marker. Restore only the original binding, never overwrite new data.
        with marker.open('x', encoding='utf-8', newline='') as output:
            output.write(proof['marker_text'])
            output.flush()
            os.fsync(output.fileno())
        return {'identity': fs.identity(marker)['identity'],
                'sha256': hashlib.sha256(marker.read_bytes()).hexdigest()}
