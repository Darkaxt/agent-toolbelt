"""Optional observational telemetry and tray lifecycle; never launch clearance."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from .gate import NamedMutex, NO_WINDOW
from .notifications import owner_label, thread_label
from .queue import NativeWait, default_root
from .support import save

_OBSERVERS = {}

def names(root):
    key = hashlib.sha256(os.path.normcase(str(Path(root).resolve())).encode()).hexdigest()[:24]
    return r'Local\Darka.GradleTray.' + key


def identity(ticket):
    try:
        native = NativeWait()
        handle, _ = native.process(ticket['pid'], ticket['created_ticks'])
        if handle:
            native.k.CloseHandle(handle)
            return 'live'
        return 'exited'
    except (OSError, KeyError, TypeError):
        return 'unknown'


class TelemetryStore:
    def __init__(self, root=None, *, lock=None, identity=identity):
        self.root = Path(root) if root is not None else default_root()
        self.lock = lock or (lambda: NamedMutex(names(self.root) + '.Metadata'))
        self.identity = identity

    def read(self):
        path = self.root / 'telemetry.json'
        if not path.exists():
            return {'schema': 1, 'since': time.time(), 'live': {}, 'recent': [],
                    'stats': dict(builds=0, failures=0, aborted=0, abandoned=0,
                                  gate_seconds=0, build_seconds=0, queue_seconds=0, admissions=0)}
        data = json.loads(path.read_text(encoding='utf-8'))
        if (data.get('schema') != 1 or not isinstance(data.get('live'), dict) or
                not isinstance(data.get('stats'), dict) or not isinstance(data.get('recent'), list)):
            raise ValueError('Invalid observational telemetry; not reset automatically')
        return data

    def update(self, row, phase, *, now=None, **fields):
        now = time.time() if now is None else now
        with self.lock():
            data = self.read()
            for key, previous in list(data['live'].items()):
                if self.identity(previous) == 'exited':
                    del data['live'][key]
                    data['stats']['abandoned'] += 1
                    data['recent'].insert(0, {**previous, 'phase': 'supervisor_exited', 'finished_at': now})
            if phase == 'finished':
                previous = data['live'].pop(row['id'], None)
                if previous is not None:
                    completed = {**previous, **fields, 'phase': phase, 'finished_at': now}
                    stats = data['stats']
                    if fields.get('exit_code') is None:
                        stats['aborted'] += 1
                    else:
                        stats['builds'] += 1
                        stats['failures'] += int(fields['exit_code'] != 0)
                        stats['build_seconds'] += fields.get('build_seconds', 0)
                    if 'acquired_at' in previous:
                        stats['admissions'] += 1
                        stats['queue_seconds'] += fields.get('queue_seconds', 0)
                        stats['gate_seconds'] += fields.get('gate_seconds', 0)
                    data['recent'].insert(0, completed)
            else:
                data['live'][row['id']] = {**data['live'].get(row['id'], {}), **row, **fields,
                                          'phase': phase, 'updated_at': now}
            data['recent'] = data['recent'][:100]
            save(self.root / 'telemetry.json', data)


def running(root=None):
    root = Path(root) if root is not None else default_root()
    mutex = NamedMutex(names(root))
    try:
        result = mutex.kernel.WaitForSingleObject(mutex.handle, 0)
        if result in (0, 0x80):
            mutex.kernel.ReleaseMutex(mutex.handle)
            return False
        if result == 258:
            return True
        raise ctypes_error()
    finally:
        mutex.kernel.CloseHandle(mutex.handle)


def ctypes_error():
    import ctypes
    return ctypes.WinError(ctypes.get_last_error())


def command(root, *arguments):
    powershell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    return [str(powershell), '-NoProfile', '-NonInteractive', '-STA', '-WindowStyle', 'Hidden',
            '-File', str(Path(__file__).parent / 'assets/tray.ps1'), '-Root', str(root),
            '-MutexName', names(root), *arguments]


def start(root=None, *, wait_ready=True):
    root = Path(root) if root is not None else default_root()
    if running(root):
        return {'state': 'already_running'}
    native = NativeWait()
    ready = native.event(names(root) + '.Ready')
    try:
        native.k.ResetEvent(ready)
        child = subprocess.Popen(command(root), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        _OBSERVERS[names(root)] = child
        if not wait_ready:
            return {'state': 'launch_requested', 'pid': child.pid}
        # Optional UI readiness diagnostic only; never a build/queue deadline.
        result = native.k.WaitForSingleObject(ready, 15000)
        return {'state': 'started' if result == 0 else 'readiness_unconfirmed', 'pid': child.pid}
    finally:
        native.k.CloseHandle(ready)


def stop(root=None):
    root = Path(root) if root is not None else default_root()
    if not running(root):
        return {'state': 'not_running'}
    native = NativeWait()
    event = native.event(names(root) + '.Stop')
    try:
        native.signal(event)
    finally:
        native.k.CloseHandle(event)
    child = _OBSERVERS.get(names(root))
    if child is not None:
        try:
            child.wait(timeout=15)  # Observer exit diagnostic only; never kill.
            del _OBSERVERS[names(root)]
            return {'state': 'stopped', 'builds_affected': False}
        except subprocess.TimeoutExpired:
            pass
    return {'state': 'stop_requested', 'builds_affected': False}


def status(root=None):
    root = Path(root) if root is not None else default_root()
    try:
        child = subprocess.run(command(root, '-Probe'), capture_output=True, text=True, encoding='utf-8',
                               creationflags=NO_WINDOW, timeout=15)
        if child.returncode:
            raise ValueError('Observer snapshot failed')
        return {**json.loads(child.stdout), 'observer_running': running(root), 'read_only': True}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'state': 'unavailable', 'failure_kind': 'tray_snapshot_error', 'read_only': True}


class BuildTelemetry:
    def __init__(self, project, owner_task=None, *, thread_name=None, enabled=True, store=None, autostart=True):
        self.enabled, self.autostart, self.store = enabled, autostart, store
        self.row = {'owner_task': owner_label(owner_task), 'thread_name': thread_label(thread_name),
                    'project': str(project), 'queued_at': time.time()}
        self.queued = time.monotonic()
        self.acquired = self.build_started = self.build_finished = None
        self.finished_at = None
        self.gate_released = None
        self.exit_code = None
        self.events = queue.SimpleQueue()
        self.worker = None
        self.result = {'state': 'not_started' if enabled else 'disabled'}

    def __enter__(self):
        if self.enabled:
            try:
                self.worker = threading.Thread(target=self._run, name='gradle-tray-telemetry', daemon=True)
                self.worker.start()
            except Exception as error:
                self.worker = None
                self.result.update(state='unavailable', failure_kind=type(error).__name__)
        return self

    def registered(self, ticket):
        if self.worker is not None:
            self.row.update(ticket)
            self.events.put(('queued', dict(self.row), {}))

    def phase(self, ticket, phase):
        if self.worker is None:
            return
        if 'id' not in self.row:
            self.registered(ticket)
        fields = {}
        if phase == 'preflight':
            self.acquired = time.monotonic()
            fields['acquired_at'] = time.time()
        elif phase == 'running':
            self.build_started = time.monotonic()
            fields['build_started_at'] = time.time()
        if self.finished_at is not None:
            fields['build_finished_at'] = self.finished_at
        self.events.put((phase, dict(self.row), fields))

    def completed(self, exit_code):
        self.exit_code = exit_code
        self.build_finished = time.monotonic()
        self.finished_at = time.time()

    def released(self):
        self.gate_released = time.monotonic()
        if self.worker is not None and 'id' in self.row:
            self.events.put(('released', dict(self.row), {'released_at': time.time()}))

    def _run(self):
        launched = False
        while True:
            event = self.events.get()
            if event is None:
                return
            phase, row, fields = event
            try:
                if self.store is None:
                    self.store = TelemetryStore()
                self.store.update(row, phase, **fields)
                self.result['state'] = 'recorded' if self.result['state'] != 'unavailable' else 'unavailable'
                if self.autostart and not launched:
                    launched = True
                    self.result['observer'] = start(self.store.root, wait_ready=False)
            except Exception as error:
                self.result.update(state='unavailable', failure_kind=type(error).__name__)

    def __exit__(self, *args):
        if self.worker is None:
            return
        if 'id' in self.row:
            now = time.monotonic()
            self.events.put(('finished', dict(self.row), {
                'exit_code': self.exit_code,
                'queue_seconds': max(0, self.acquired - self.queued) if self.acquired is not None else 0,
                'gate_seconds': max(0, (self.gate_released or now) - self.acquired)
                                if self.acquired is not None else 0,
                'build_seconds': max(0, (self.build_finished or now) - self.build_started)
                                 if self.build_started is not None else 0}))
        self.events.put(None)
        # Collect diagnostics after mutex/ticket release. A stuck observational
        # worker may lose its final write; it never delays release or cancels work.
        self.worker.join(timeout=15)
        if self.worker.is_alive():
            self.result.update(state='unavailable', failure_kind='telemetry_collection_incomplete')
