"""Prove that a CMake download is reproducible rather than maintained local work."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from . import filesystem as fs
from . import retirement


def reject(kind, message):
    raise retirement.RetirementError('dependency_' + kind, message)


def github_source_commit(parts, oid):
    endpoint = f'repos/{parts[0]}/{parts[1]}/git/commits/{oid}'
    gh = shutil.which('gh')
    if gh:
        result = subprocess.run([gh, 'api', '--hostname', 'github.com', endpoint, '--jq', '.sha'],
                                capture_output=True, text=True,
                                env=dict(os.environ, GH_PROMPT_DISABLED='1'))
        if result.returncode:
            reject('source_pin_unavailable', 'Existing GitHub CLI cannot verify the exact source commit')
        actual = result.stdout.strip()
    else:
        request = Request('https://api.github.com/' + endpoint,
                          headers={'User-Agent': 'transactional-cleanup', 'Accept': 'application/vnd.github+json'})
        try:
            with urlopen(request) as response:
                actual = json.load(response).get('sha')
        except (OSError, ValueError):
            reject('source_pin_unavailable', 'Cannot verify the exact public source commit')
    if actual != oid:
        reject('source_pin_unavailable', 'Public source commit identity does not match')


def fingerprint(path, project, root):
    path = fs.canonical(path)
    fs.check_chain(path)
    if not fs.within(path, project) or fs.within(path, root) or not path.is_file():
        reject('producer_invalid', 'Producer and patches must remain outside the clone in the maintained project')
    retirement.git(path.parent, 'ls-files', '--error-unmatch', '--', str(path))
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def patch_tree(root, head, patches, validation):
    """Git writes only the caller-owned Temp index/object directory, never the clone."""
    validation = fs.canonical(validation)
    fs.check_chain(validation)
    temp_roots = [Path('D:/Temp'), Path('E:/Temp'), Path(tempfile.gettempdir())]
    if (not validation.is_dir() or not any(validation != p and fs.within(validation, p) for p in temp_roots)
            or fs.within(validation, root)):
        reject('validation_root_invalid', 'Use an existing task-owned Temp scratch directory; clean it through the helper')
    scratch = Path(tempfile.mkdtemp(prefix='dependency-proof-', dir=validation))
    objects = scratch / 'objects'; objects.mkdir()
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0',
                       GIT_INDEX_FILE=str(scratch / 'index'), GIT_OBJECT_DIRECTORY=str(objects),
                       GIT_ALTERNATE_OBJECT_DIRECTORIES=str(root / '.git/objects'))

    def isolated(*args):
        result = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-c', 'gc.auto=0',
                                 '-c', 'maintenance.auto=false', '-C', str(root), *args],
                                capture_output=True, text=True, env=environment)
        if result.returncode:
            reject('patch_mismatch', 'Maintained patches do not reproduce the complete dependency worktree')
        return result.stdout
    isolated('read-tree', head)
    for patch in patches:
        isolated('apply', '--cached', '--ignore-whitespace', '--', patch['path'])
    tree = isolated('write-tree').strip()
    isolated('diff', '--no-ext-diff', '--no-textconv', '--exit-code', tree, '--')
    return tree


def source_proof(root, declared_origin, declared_pin, patches, validation_root, outer=None):
    marker = root / '.git'
    if fs.reparse(marker) or (not marker.is_dir() if outer is None else not marker.is_file()):
        reject('repository_invalid', 'Linked/external Git metadata is unsupported')
    top = fs.canonical(retirement.git(root, 'rev-parse', '--show-toplevel').strip())
    common = fs.canonical(retirement.git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir').strip())
    fs.check_chain(common)
    contained = common == marker if outer is None else fs.within(common, outer / 'modules')
    if top != root or not contained or (common / 'objects/info/alternates').exists():
        reject('repository_invalid', 'Require an independent exact standalone clone')
    hooks = common / 'hooks'
    if hooks.is_dir() and any(p.is_file() and not p.name.endswith('.sample') for p in hooks.iterdir()):
        reject('local_changes', 'Custom local Git hooks must be preserved')
    config = retirement.git(root, 'config', '--local', '--list').splitlines()
    if any(re.match(r'(alias\.|credential\.|user\.|include\.|includeif\.|filter\.|core\.hookspath=)', line, re.I) for line in config):
        reject('local_changes', 'Custom local Git configuration must be preserved')
    if retirement.git(root, 'worktree', 'list', '--porcelain').count('worktree ') != 1:
        reject('worktrees', 'Additional worktrees still use this clone')
    origin = retirement.git(root, 'remote', 'get-url', 'origin').strip()
    if origin.replace('\\', '/') != declared_origin.replace('\\', '/'):
        reject('origin_mismatch', 'Clone origin does not match maintained provenance')
    parsed_origin = urlsplit(origin)
    if parsed_origin.scheme == 'https' and parsed_origin.hostname and not parsed_origin.username and not parsed_origin.password:
        pass
    elif Path(origin).is_absolute():
        source = fs.canonical(origin)
        fs.check_chain(source)
        if fs.within(source, root) or retirement.git(source, 'rev-parse', '--is-bare-repository').strip() != 'true':
            reject('origin_invalid', 'Local regeneration requires an independent bare source')
    else:
        reject('origin_invalid', 'Use a credential-free HTTPS origin or independent local bare source')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', declared_pin):
        reject('pin_invalid', 'Use a literal commit hash or tag/ref name')
    if retirement.git(root, 'remote').splitlines() != ['origin']:
        reject('local_history', 'Additional remotes require preservation review')
    head = retirement.git(root, 'rev-parse', '--verify', 'HEAD').strip()
    pin = retirement.git(root, 'rev-parse', '--verify', declared_pin + '^{commit}').strip()
    if head != pin:
        reject('pin_mismatch', 'Clone HEAD differs from the maintained dependency pin')
    refs = retirement.git(root, 'for-each-ref', '--format=%(refname) %(objectname)').splitlines()
    ref_map = dict(line.split(' ', 1) for line in refs)
    # Query the declared source directly: a stale local remote-tracking tag is
    # insufficient proof that a named local tag is reproducible.
    remote = subprocess.run(['git', '-c', 'protocol.ext.allow=never', 'ls-remote', '--', origin],
                            capture_output=True, text=True,
                            env=dict(os.environ, GIT_TERMINAL_PROMPT='0'))
    if remote.returncode:
        reject('source_unavailable', 'Cannot verify the regeneration source; preserve the clone')
    remote_refs = {ref: oid for oid, ref in (line.split() for line in remote.stdout.splitlines())}
    verified_commits = set(remote_refs.values())
    def verify_source_commit(oid):
        if oid in verified_commits:
            return
        if Path(origin).is_absolute():
            retirement.git(fs.canonical(origin), 'cat-file', '-e', oid + '^{commit}')
            return
        # Exact GitHub commit reads prove hash pins that are ancestors of current
        # remote tips. Other hosts remain fail-closed unless advertising the pin.
        parts = parsed_origin.path.removesuffix('.git').strip('/').split('/')
        if parsed_origin.hostname != 'github.com' or len(parts) != 2:
            reject('source_pin_unavailable', 'The remote does not advertise the exact source commit')
        github_source_commit(parts, oid)
        verified_commits.add(oid)
    verify_source_commit(head)
    for name, oid in ref_map.items():
        if name.startswith('refs/heads/'):
            if ref_map.get('refs/remotes/origin/' + name[len('refs/heads/'):]) != oid:
                reject('local_history', 'Local branch has no matching origin branch')
        elif name.startswith('refs/tags/'):
            if remote_refs.get(name) != oid:
                reject('local_history', 'Local-only or changed tags must be preserved')
        elif name.startswith('refs/remotes/origin/'):
            verify_source_commit(oid)
        else:
            reject('local_history', 'Unknown local refs must be preserved')
    if retirement.git(root, 'rev-list', '--all', '--reflog', '--not', '--remotes=origin', '--tags').strip():
        reject('local_history', 'Local-only/ref/reflog commits must be preserved')
    status = retirement.git(root, 'status', '--porcelain=v1', '--untracked-files=all', '--ignored')
    if any(line[:2] in {'??', '!!'} for line in status.splitlines()):
        reject('local_changes', 'Untracked or ignored local files remain')
    if any(line[0] != ' ' for line in status.splitlines()):
        reject('local_changes', 'Staged/index changes must be preserved')
    if patches:
        tree = patch_tree(root, head, patches, validation_root)
    else:
        if status.strip():
            reject('local_changes', 'Unknown tracked changes remain')
        tree = retirement.git(root, 'rev-parse', 'HEAD^{tree}').strip()
    children = []
    links = [line.split('\t', 1) for line in retirement.git(root, 'ls-files', '--stage').splitlines()
             if line.startswith('160000 ')]
    for fields, relative in links:
        child = fs.canonical(root / relative)
        if not fs.within(child, root) or child == root:
            reject('submodule_invalid', 'Submodule path escapes its generated parent')
        child_pin = fields.split()[1]
        if not child.exists() or not any(child.iterdir()):
            children.append({'path': relative, 'pin': child_pin, 'initialized': False})
            continue
        mappings = retirement.git(root, 'config', '--blob', 'HEAD:.gitmodules', '--get-regexp', r'^submodule\..*\.path$')
        keys = [line.split(' ', 1)[0] for line in mappings.splitlines() if line.split(' ', 1)[1] == relative]
        if len(keys) != 1:
            reject('submodule_invalid', 'Require one tracked submodule origin declaration')
        child_origin = retirement.git(root, 'config', '--blob', 'HEAD:.gitmodules', '--get', keys[0][:-4] + 'url').strip()
        child_proof = source_proof(child, child_origin, child_pin, [], validation_root, outer or common)
        children.append({'path': relative, 'pin': child_pin, 'initialized': True, 'proof': child_proof})
    return {'head': head, 'tree': tree, 'root_identity': retirement.standalone(root),
            'git_identity': retirement.standalone(common), 'children': children,
            'refs_sha256': hashlib.sha256('\n'.join(refs).encode()).hexdigest()}


def validate(root, evidence, expected=None, require_git=True):
    identity = retirement.standalone(root, expected.get('root_identity') if expected else None)
    project = fs.canonical(evidence['project'])
    project_identity = retirement.standalone(project)
    relative = root.relative_to(project) if fs.within(root, project) and root != project else Path('.')
    if ('.cxx' not in relative.parts or root.parent.name != '_deps'
            or root.name.casefold() != evidence['dependency'].casefold() + '-src'):
        reject('location_invalid', 'Only exact .cxx/.../_deps/<dependency>-src generated clones are supported')
    if fs.canonical(retirement.git(project, 'rev-parse', '--show-toplevel').strip()) != project:
        reject('project_invalid', 'The maintained project must be an exact Git working-tree root')
    retirement.check_consumers(project, evidence)
    producer = fingerprint(evidence['producer'], project, root)
    patches = [fingerprint(p, project, root) for p in evidence.get('patches', [])]
    text = Path(producer['path']).read_text(encoding='utf-8-sig')
    if any(Path(p['path']).name not in text for p in patches):
        reject('producer_mismatch', 'Maintained patch paths must be referenced by the producer')
    text = re.sub(r'(?m)#.*$', '', text)
    declarations = re.findall(r'FetchContent_Declare\(\s*([^\s()]+)([^)]*)\)', text, re.I)
    matches = [body for name, body in declarations if name.casefold() == evidence['dependency'].casefold()
               and re.search(r'GIT_REPOSITORY\s+"?' + re.escape(evidence['origin']) + r'"?(?=\s|$)', body)
               and re.search(r'GIT_TAG\s+"?' + re.escape(evidence['pin']) + r'"?(?=\s|$)', body)]
    if len(matches) != 1 or bool(re.search(r'\bPATCH_COMMAND\b', matches[0])) != bool(patches):
        reject('producer_mismatch', 'Require one literal matching FetchContent origin/pin and explicit maintained patches')
    static = {'producer': producer, 'patches': patches, 'project_identity': project_identity}
    if expected and static != expected['dependency']:
        reject('producer_changed', 'Maintained producer or patches changed after review')
    if not require_git:
        return expected
    git_state = source_proof(root, evidence['origin'], evidence['pin'], patches, evidence['validation_root'])
    proof = {'evidence': evidence, 'root_identity': identity, 'dependency': static,
             'git': git_state}
    if expected and proof != expected:
        reject('changed_after_review', 'Dependency state changed; obtain a fresh review')
    return proof
