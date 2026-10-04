import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
PACKAGE = 'agent_toolbelt_c_drive_maintenance'


def source_root():
    override = os.environ.get('AGENT_TOOLBELT_HOME')
    if override:
        source = Path(override) / 'families/c-drive-maintenance/src'
        if not (source / PACKAGE / 'cli.py').is_file():
            raise RuntimeError('AGENT_TOOLBELT_HOME lacks c-drive-maintenance')
        return source
    root = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share'))
    pointer = root / 'Tools/c-drive-maintenance/active.json'
    if pointer.is_file():
        source = Path(json.loads(pointer.read_text(encoding='utf-8'))['source'])
        if (source / PACKAGE / 'cli.py').is_file():
            return source
        raise RuntimeError('Installed maintenance runtime is incomplete; rerun installer')
    for parent in Path(__file__).resolve().parents:
        source = parent / 'families/c-drive-maintenance/src'
        if (source / PACKAGE / 'cli.py').is_file():
            return source
    raise RuntimeError('Install the c-drive-maintenance runtime first')


if __name__ == '__main__':
    try:
        sys.path.insert(0, str(source_root()))
        from agent_toolbelt_c_drive_maintenance.cli import main
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({'ok': False, 'failure_kind': 'runtime_unavailable', 'errors': [str(error)]}))
        raise SystemExit(1)
