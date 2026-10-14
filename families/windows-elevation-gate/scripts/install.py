"""Deploy immutable runtime and identical agent-neutral personal skill folders."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

FAMILY = Path(__file__).resolve().parents[1]


sys.dont_write_bytecode = True


def protected_broker(executable, thread_name):
    sys.path.insert(0, str(FAMILY / 'src'))
    from agent_toolbelt_windows_elevation_gate import broker, engine
    executable = Path(executable).resolve(strict=True)
    digest = engine.sha256(executable)
    try:
        _, current = broker.installation()
        if engine.sha256(current) == digest:
            return {'ok': True, 'already_installed': True, 'broker': str(current)}
    except broker.BrokerUnavailable:
        pass
    powershell = Path(os.environ['WINDIR']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = FAMILY / 'assets/install-broker.ps1'
    request = engine.prepare([str(powershell), '-NoProfile', '-NonInteractive', '-File', str(script),
                              '-SourceExe', str(executable), '-ExpectedSha256', digest], cwd=str(FAMILY),
        task='Install protected administrator approval broker', thread_name=thread_name,
        reason='Replace repeated per-command UAC with a broker that owns each Accept/Cancel decision',
        changes='Install content-addressed broker under Program Files with administrator ownership and read-only user access; no service, startup, UAC policy or application settings change',
        targets=[str(broker.root_path())], bind_files=[str(executable)])
    result = engine.run(request)
    if not result.get('ok'):
        raise RuntimeError('Protected broker installation did not succeed; previous client activation preserved: ' + json.dumps(result))
    _, installed = broker.installation()
    if engine.sha256(installed) != digest:
        raise RuntimeError('Protected broker verification failed; previous client activation preserved')
    return {'ok': True, 'broker': str(installed), 'sha256': digest}


def install(runtime_root, skill_roots, broker_exe=None, thread_name=None):
    protected = protected_broker(broker_exe, thread_name) if broker_exe else None
    source = FAMILY / "src/agent_toolbelt_windows_elevation_gate"
    files = sorted(p for p in source.rglob("*.py") if "__pycache__" not in p.parts)
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(source).as_posix().encode())
        digest.update(path.read_bytes())
    release = digest.hexdigest()[:16]
    destination = runtime_root / "releases" / release / source.name
    for path in files:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != path.read_bytes():
            raise RuntimeError("Existing immutable runtime differs; refusing overwrite")
        if not target.exists():
            shutil.copy2(path, target)
        if target.read_bytes() != path.read_bytes():
            raise RuntimeError("Runtime copy verification failed")
    pending = runtime_root / (uuid.uuid4().hex + ".pending.json")
    try:
        pending.write_text(json.dumps({"schema": 1, "release": release, "version": "0.2.0"}), encoding="utf-8")
        os.replace(pending, runtime_root / "active.json")
    finally:
        pending.unlink(missing_ok=True)
    skill = FAMILY / "codex/skills/windows-elevation-gate"
    for root in skill_roots:
        for path in skill.rglob("*"):
            if path.is_file() and path.suffix in (".py", ".md", ".yaml"):
                target = root / skill.name / path.relative_to(skill)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                if target.read_bytes() != path.read_bytes():
                    raise RuntimeError("Installed skill copy verification failed")
    return {"ok": True, "release": release, "runtime": str(destination), "protected_broker": protected,
            "skills": [str(root / skill.name) for root in skill_roots]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path,
                        default=Path(os.environ["LOCALAPPDATA"]) / "Tools/windows-elevation-gate")
    parser.add_argument("--skills-root", type=Path, action="append")
    parser.add_argument("--broker-exe", type=Path, help="Install/verify protected broker through the existing explained native-UAC flow before client activation")
    parser.add_argument("--thread-name", help="Actual conversation title for protected installation")
    args = parser.parse_args()
    if args.broker_exe and not args.thread_name:
        parser.error('--thread-name is required with --broker-exe')
    roots = args.skills_root or [Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills",
                                Path.home() / ".agents/skills", Path.home() / ".claude/skills"]
    print(json.dumps(install(args.runtime_root, roots, args.broker_exe, args.thread_name), indent=2))
