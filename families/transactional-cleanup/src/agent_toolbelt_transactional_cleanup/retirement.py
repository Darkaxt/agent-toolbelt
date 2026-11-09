"""Read-only evidence checks for explicitly authorized checkout retirement."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

from . import filesystem as fs


class RetirementError(ValueError):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def git(root, *args, input=None):
    result = subprocess.run(
        ['git', '-c', 'core.fsmonitor=false', '-c', 'gc.auto=0',
         '-c', 'maintenance.auto=false', '-C', str(root), *args],
        input=input, capture_output=True, text=True,
        env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'))
    if result.returncode:
        raise RetirementError('retirement_git_error',
                              f'Git verification failed ({args[0]}, exit {result.returncode})')
    return result.stdout


def active_processes(root):
    # Command-line visibility is evidence, not proof that services/tasks have no
    # dormant dependencies. The separate owner review covers those consumers.
    command = ('Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,'
               'CreationDate,CommandLine | ConvertTo-Json -Compress')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, text=True)
    if result.returncode:
        raise RetirementError('retirement_process_inspection_failed',
                              'Cannot inspect visible process identities; no retirement authorized')
    try:
        rows = json.loads(result.stdout)
        rows = rows if isinstance(rows, list) else [rows]
        parents = {row['ProcessId']: row['ParentProcessId'] for row in rows}
    except (ValueError, TypeError, KeyError) as exc:
        raise RetirementError('retirement_process_inspection_failed', 'Invalid process snapshot') from exc
    supervisors, current = set(), os.getpid()
    while current and current not in supervisors:
        supervisors.add(current)
        current = parents.get(current)
    pattern = re.compile(re.escape(str(root).replace('\\', '/')) + r'''(?=$|[/\s"':,;])''', re.I)
    return [{'pid': row['ProcessId'], 'started_at': row['CreationDate']}
            for row in rows if row['ProcessId'] not in supervisors
            and pattern.search((row.get('CommandLine') or '').replace('\\', '/'))]


def check_consumers(root, evidence):
    review = evidence.get('consumer_review', {})
    required = ('checked_at', 'ownership', 'schedulers_services', 'dependencies')
    if not isinstance(review, dict) or any(not isinstance(review.get(key), str)
                                          or not review[key].strip() for key in required):
        raise RetirementError('retirement_consumer_evidence_required',
                              'Record ownership, schedulers/services, dependencies and check timestamp')
    if review.get('active_consumers') != []:
        raise RetirementError('retirement_active_consumers', 'Owner review has unresolved consumers')
    processes = active_processes(root)
    if processes:
        raise RetirementError('retirement_active_consumers',
                              'Visible processes reference the checkout: ' + json.dumps(processes))


def load_evidence(path, root):
    path = fs.canonical(path)
    fs.check_chain(path)
    if fs.within(path, root):
        raise RetirementError('retirement_evidence_invalid', 'Keep retirement evidence outside the checkout')
    if path.stat().st_size > 1024 * 1024:
        raise RetirementError('retirement_evidence_invalid', 'Retirement evidence must be a compact JSON document')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict) or value.get('version') != 1:
        raise RetirementError('retirement_evidence_invalid', 'Expected retirement evidence version 1')
    if fs.canonical(value.get('repository', '')) != root:
        raise RetirementError('retirement_evidence_invalid', 'Evidence repository does not match the exact root')
    fields = (('authorization', 'project', 'producer', 'dependency', 'origin', 'pin', 'validation_root')
              if value.get('mode') == 'cmake-fetchcontent' else
              ('authorization', 'recovery_instructions', 'recovery_repository'))
    for field in fields:
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise RetirementError('retirement_evidence_invalid', f'Missing {field}')
    return value


def standalone(root, identity=None):
    fs.check_chain(root)
    info = fs.identity(root)
    if not info['directory'] or info['reparse'] or info['filesystem'] not in {'NTFS', 'ReFS'}:
        raise RetirementError('retirement_repository_invalid', 'Normal NTFS/ReFS checkout required')
    if identity is not None and info['identity'] != identity:
        raise RetirementError('retirement_repository_replaced', 'Retired repository root was replaced')
    return info['identity']


def verify_recovery(root, proof):
    recovery = fs.canonical(proof['evidence']['recovery_repository'])
    if fs.within(recovery, root) or fs.within(root, recovery):
        raise RetirementError('retirement_recovery_invalid', 'Recovery repository must be independent of the retired root')
    identity = standalone(recovery, proof.get('recovery_identity'))
    if git(recovery, 'rev-parse', '--is-bare-repository').strip() != 'true':
        raise RetirementError('retirement_recovery_invalid', 'Use an existing independent bare recovery repository')
    objects = fs.canonical(git(recovery, 'rev-parse', '--path-format=absolute', '--git-path', 'objects').strip())
    if objects != recovery / 'objects' or (objects / 'info/alternates').exists() or (recovery / 'shallow').exists():
        raise RetirementError('retirement_recovery_invalid', 'Shared, alternate or shallow recovery storage is unsupported')
    for folder, dirs, files in os.walk(objects, followlinks=False):
        for name in (*dirs, *files):
            if fs.reparse(Path(folder) / name):
                raise RetirementError('retirement_recovery_invalid', 'Recovery object storage cannot contain redirected paths')
    required = proof['git']['required_objects']
    for offset in range(0, len(required), 256):
        batch = required[offset:offset + 256]
        lines = git(recovery, 'cat-file', '--batch-check', input='\n'.join(batch) + '\n').splitlines()
        if len(lines) != len(batch) or any(line.endswith(' missing') for line in lines):
            raise RetirementError('retirement_recovery_incomplete',
                                  'Recovery lacks local/ref/reflog history; preserve it before retirement')
    recovery_refs = set(git(recovery, 'for-each-ref', '--format=%(refname) %(objectname)').splitlines())
    reachable = set(git(recovery, 'rev-list', '--all').splitlines())
    reachable.update(line.split(' ', 1)[1] for line in recovery_refs)
    if not set(proof['git']['refs']).issubset(recovery_refs) or not set(required).issubset(reachable):
        raise RetirementError('retirement_recovery_incomplete',
                              'Recovery must retain original named refs and anchor reflog history against Git pruning')
    git(recovery, 'fsck', '--full', '--no-reflogs')
    return identity


def validate(root, evidence, expected=None, require_git=True):
    if evidence.get('mode') == 'cmake-fetchcontent':
        from . import generated_dependencies
        return generated_dependencies.validate(root, evidence, expected, require_git)
    identity = standalone(root, expected.get('root_identity') if expected else None)
    check_consumers(root, evidence)
    if not require_git:
        verify_recovery(root, expected)
        return expected
    marker = root / '.git'
    if not marker.is_dir() or fs.reparse(marker):
        raise RetirementError('retirement_repository_invalid', 'Linked worktrees and external Git metadata are unsupported')
    top = fs.canonical(git(root, 'rev-parse', '--show-toplevel').strip())
    common = fs.canonical(git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir').strip())
    if top != root or common != marker or (marker / 'shallow').exists():
        raise RetirementError('retirement_repository_invalid', 'Exact standalone non-shallow checkout required')
    if git(root, 'worktree', 'list', '--porcelain').count('worktree ') != 1:
        raise RetirementError('retirement_worktrees', 'Additional worktrees still depend on this repository')
    if git(root, 'status', '--porcelain=v1', '--untracked-files=all', '--ignored').strip():
        raise RetirementError('retirement_local_changes',
                              'Tracked edits, untracked or ignored files remain; preserve work or clean eligible output first')
    if any(line.startswith('160000 ') for line in git(root, 'ls-files', '--stage').splitlines()):
        raise RetirementError('retirement_repository_invalid', 'Submodule retirement requires separate ownership review')
    head = git(root, 'rev-parse', '--verify', 'HEAD').strip()
    refs = git(root, 'for-each-ref', '--format=%(refname) %(objectname)').splitlines()
    required = set(git(root, 'rev-list', '--all', '--reflog').splitlines())
    required.update(line.split(' ', 1)[1] for line in refs)
    required.add(head)
    proof = {'evidence': evidence, 'root_identity': identity,
             'git': {'head': head, 'refs': refs, 'required_objects': sorted(required)}}
    proof['recovery_identity'] = verify_recovery(root, proof)
    if expected and proof != expected:
        raise RetirementError('retirement_changed_after_review',
                              'Git state, recovery identity or owner evidence changed; obtain a new review')
    return proof
