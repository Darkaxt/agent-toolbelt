"""Prove installed startup survives closing only an isolated launcher job."""
import argparse
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

RUNTIME = Path(os.environ['LOCALAPPDATA']) / 'Tools/windows-elevation-gate'
active = json.loads((RUNTIME / 'active.json').read_text())
sys.path.insert(0, str(RUNTIME / 'releases' / active['release']))
from agent_toolbelt_windows_elevation_gate import broker
from agent_toolbelt_windows_elevation_gate.native import Native


class StartupInfo(ctypes.Structure):
    _fields_ = [('cb', w.DWORD), ('reserved', w.LPWSTR), ('desktop', w.LPWSTR), ('title', w.LPWSTR),
                ('x', w.DWORD), ('y', w.DWORD), ('width', w.DWORD), ('height', w.DWORD),
                ('xchars', w.DWORD), ('ychars', w.DWORD), ('fill', w.DWORD), ('flags', w.DWORD),
                ('show', w.WORD), ('reserved_count', w.WORD), ('reserved_bytes', ctypes.c_void_p),
                ('stdin', w.HANDLE), ('stdout', w.HANDLE), ('stderr', w.HANDLE)]


class ProcessInfo(ctypes.Structure):
    _fields_ = [('process', w.HANDLE), ('thread', w.HANDLE), ('pid', w.DWORD), ('tid', w.DWORD)]


class BasicLimits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64), ('flags', w.DWORD),
                ('min_working_set', ctypes.c_size_t), ('max_working_set', ctypes.c_size_t),
                ('active_processes', w.DWORD), ('affinity', ctypes.c_size_t),
                ('priority', w.DWORD), ('scheduling', w.DWORD)]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('basic', BasicLimits), ('io_counters', ctypes.c_uint64 * 6),
                ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]


def native():
    n = Native()
    n.k.CreateJobObjectW.argtypes, n.k.CreateJobObjectW.restype = [ctypes.c_void_p, w.LPCWSTR], w.HANDLE
    n.k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    n.k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    n.k.IsProcessInJob.argtypes = [w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)]
    n.k.GetCurrentProcess.restype = w.HANDLE
    n.k.ResumeThread.argtypes, n.k.ResumeThread.restype = [w.HANDLE], w.DWORD
    n.k.CreateProcessW.argtypes = [w.LPCWSTR, w.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                  w.BOOL, w.DWORD, ctypes.c_void_p, w.LPCWSTR,
                                  ctypes.POINTER(StartupInfo), ctypes.POINTER(ProcessInfo)]
    return n


def member(n, process, job=None):
    value = w.BOOL()
    if not n.k.IsProcessInJob(process, job, ctypes.byref(value)):
        raise ctypes.WinError(ctypes.get_last_error())
    return bool(value.value)


def worker(root, signal, release):
    n = native()
    ready, finish = n.event(signal), n.event(release)
    try:
        result = broker.start()
        result['fixture_in_job'] = member(n, n.k.GetCurrentProcess())
        (root / 'startup.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        n.signal(ready)
        n.wait(finish)
    finally:
        n.close(ready)
        n.close(finish)


def verify(root):
    if broker.status().get('running'):
        raise RuntimeError('Stop the existing broker through its normal interface before the startup fixture')
    root.mkdir(parents=True, exist_ok=False)
    n = native()
    nonce = uuid.uuid4().hex
    signal, release = ('Local\\Darka.Elevation.Lifecycle.' + nonce + suffix for suffix in ('.ready', '.release'))
    ready, finish = n.event(signal), n.event(release)
    job = n.k.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE, only for this test's launcher.
    info = ProcessInfo()
    may_close_kill_job = False
    try:
        if not n.k.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline([
            sys.executable, '-B', str(Path(__file__).resolve()), '--fixture-worker', str(root),
            '--signal', signal, '--release', release]))
        startup = StartupInfo(cb=ctypes.sizeof(StartupInfo))
        if not n.k.CreateProcessW(sys.executable, command, None, None, False, 0x08000004,
                                  None, str(root), ctypes.byref(startup), ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not n.k.AssignProcessToJobObject(job, info.process):
            n.k.ResumeThread(info.thread)
            raise ctypes.WinError(ctypes.get_last_error())
        if n.k.ResumeThread(info.thread) == 0xffffffff:
            raise ctypes.WinError(ctypes.get_last_error())
        if n.wait(ready, info.process) != 0:
            raise RuntimeError('Fixture exited before startup result; no broker survival claimed')
        result = json.loads((root / 'startup.json').read_text())
        if not result.get('ok'):
            raise RuntimeError('Fixture startup failed: ' + json.dumps(result))
        current = broker.status()
        handle, _ = n.process(current['broker_pid'])
        try:
            if not handle or member(n, handle) or member(n, handle, job):
                raise RuntimeError('Broker belongs to a job; refusing fixture teardown that might kill it')
        finally:
            n.close(handle)
        if not result.get('fixture_in_job'):
            raise RuntimeError('Fixture did not exercise a job-attached launcher')
        may_close_kill_job = True
        n.close(job)
        job = None
        n.wait(info.process)
        after = broker.status()
        if not after.get('running') or not after.get('accepting') or after.get('in_job') is not False or after['broker_pid'] != current['broker_pid']:
            raise RuntimeError('Broker did not survive the isolated launcher job closing')
        evidence = {'ok': True, 'fixture_launcher_pid': info.pid, 'launcher_job_closed': True,
                    'broker_pid': after['broker_pid'], 'broker_outside_all_jobs': True,
                    'same_broker_survived': True, 'actual_codex_untouched': True}
        (root / 'verification.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        print(json.dumps(evidence, indent=2))
    finally:
        if job and not may_close_kill_job:
            # Never kill an unclassified broker or pending UAC request on failure.
            limits.basic.flags = 0
            if not n.k.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise RuntimeError('Could not disarm fixture job; preserve its handle for diagnosis')
        n.signal(finish)
        n.close(job)
        n.close(info.thread)
        n.close(info.process)
        n.close(ready)
        n.close(finish)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--fixture-worker', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--signal', help=argparse.SUPPRESS)
    parser.add_argument('--release', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.fixture_worker:
        worker(args.fixture_worker, args.signal, args.release)
    elif args.output_dir:
        verify(args.output_dir.resolve())
    else:
        parser.error('--output-dir is required')
