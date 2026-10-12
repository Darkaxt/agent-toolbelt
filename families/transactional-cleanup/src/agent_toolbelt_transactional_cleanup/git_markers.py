"""Exact generated workflow pointers, never general Git metadata deletion."""
from pathlib import Path
import re
import subprocess

from . import filesystem as fs


def validate(path, expected=None):
    path = fs.canonical(path)
    fs.check_chain(path)
    if path.parent.name != '.git' or not re.fullmatch(
            r'[A-Za-z0-9][A-Za-z0-9._-]*-workflow-tree', path.name):
        raise ValueError('Only a namespaced workflow-tree file directly inside .git is supported')
    metadata, repository = path.parent, path.parent.parent
    proof = {'path': str(path), 'repository_root': str(repository),
             'repository_identity': fs.identity(repository)['identity'],
             'git_directory': str(metadata), 'git_identity': fs.identity(metadata)['identity']}
    if expected:
        if proof != expected:
            raise ValueError('Generated Git marker ancestors changed')
        return proof
    result = subprocess.run(['git', '-C', str(repository), 'rev-parse', '--absolute-git-dir'],
                            check=True, capture_output=True, text=True)
    if fs.canonical(result.stdout.strip()) != metadata:
        raise ValueError('Marker must belong to the standalone internal Git directory')
    result = subprocess.run(['git', '-C', str(repository), 'rev-parse', '--show-toplevel'],
                            check=True, capture_output=True, text=True)
    if fs.canonical(result.stdout.strip()) != repository:
        raise ValueError('Marker must belong to the exact standalone checkout')
    info = fs.identity(path)
    if info['directory'] or info['reparse'] or info['links'] != 1 or info['size'] > 256:
        raise ValueError('Marker must be a small regular single-link file')
    tree = path.read_text(encoding='ascii').strip()
    if not re.fullmatch(r'[0-9a-fA-F]{40}|[0-9a-fA-F]{64}', tree):
        raise ValueError('Workflow marker must contain only a Git tree object ID')
    result = subprocess.run(['git', '-C', str(repository), 'cat-file', '-t', tree],
                            check=True, capture_output=True, text=True)
    if result.stdout.strip() != 'tree':
        raise ValueError('Workflow marker does not reference an existing tree')
    return proof
