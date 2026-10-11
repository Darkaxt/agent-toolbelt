"""Best-effort silent desktop information, never build synchronization."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import threading
from xml.sax.saxutils import escape


def clean_text(value, limit):
    return ' '.join(''.join(c for c in str(value) if ord(c) >= 32).split())[:limit]


def owner_label(explicit):
    if explicit and explicit.strip():
        return clean_text(explicit, 200)
    for key, prefix in (('CODEX_THREAD_ID', 'Codex task'), ('CLAUDE_SESSION_ID', 'Claude session')):
        if os.environ.get(key):
            return clean_text(f'{prefix} {os.environ[key]}', 200)
    return f'Task unknown (supervisor PID {os.getpid()})'


def thread_label(explicit):
    return clean_text(explicit or '', 200) or 'Unknown'


def payload(project, ticket_id, owner, *, thread_name=None):
    lines = ['Gradle gate in use', f'Task: {owner}', f'Thread Name: {thread_label(thread_name)}',
             'Gate owner; preflight may still be waiting for an existing build.',
             'Admitted: ' + datetime.now(timezone.utc).isoformat(timespec='seconds')]
    xml = ('<toast><visual><binding template="ToastGeneric">' +
           ''.join('<text>' + escape(line) + '</text>' for line in lines) +
           '</binding></visual><audio silent="true"/></toast>')
    # Windows limits each identifier; use both UUID halves, not a shared group
    # plus a truncated ticket that could alias another owner.
    return {'xml': xml, 'tag': ticket_id[:16], 'group': ticket_id[-16:]}


def transport(action, message):
    if os.name != 'nt':
        return {'state': 'unavailable', 'failure_kind': 'windows_required'}
    powershell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = Path(__file__).parent / 'assets/desktop-notification.ps1'
    try:
        process = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-File', str(script)],
                                 input=json.dumps({'action': action, **message}), text=True, encoding='utf-8',
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
        if process.returncode:
            return {'state': 'unavailable', 'failure_kind': 'notification_transport_error'}
        result = json.loads(process.stdout)
        if not isinstance(result, dict) or result.get('state') not in {
                'submitted', 'removed', 'registered', 'disabled_by_windows', 'unavailable'}:
            raise ValueError('Invalid notification response')
        return result
    except subprocess.TimeoutExpired:
        # Only this optional notification subprocess is bounded, never Gradle.
        return {'state': 'unavailable', 'failure_kind': 'notification_transport_timeout'}
    except (OSError, ValueError):
        return {'state': 'unavailable', 'failure_kind': 'notification_transport_error'}


class BuildNotification:
    def __init__(self, project, owner_task=None, *, thread_name=None, enabled=True):
        self.project = project
        self.owner = owner_label(owner_task)
        self.thread_name = thread_label(thread_name)
        self.enabled = enabled
        self.closed = threading.Event()
        self.worker = None
        self.result = {'state': 'not_started' if enabled else 'disabled', 'silent': True,
                       'owner_task': self.owner, 'thread_name': self.thread_name, 'project': str(project),
                       'visibility_verified': False, 'identity': 'Gradle Build Gate'}

    def __enter__(self):
        return self

    def start(self, ticket):
        if not self.enabled or self.worker is not None:
            return
        try:
            message = payload(self.project, ticket['id'], self.owner, thread_name=self.thread_name)
            self.worker = threading.Thread(target=self._run, args=(message,), name='gradle-desktop-notification')
            self.worker.start()
        except Exception as error:
            self.result.update(state='unavailable', failure_kind=type(error).__name__)
            self.worker = None

    def _run(self, message):
        try:
            self.result.update(transport('show', message))
        except Exception as error:
            self.result.update(state='unavailable', failure_kind=type(error).__name__)
        self.closed.wait()
        # An uncertain transport result can still have reached Windows before
        # its response failed; remove only our own identity in that case too.
        if self.result['state'] in {'submitted', 'unavailable'}:
            try:
                self.result['removal'] = transport('remove', message)
            except Exception as error:
                self.result['removal'] = {'state': 'unavailable', 'failure_kind': type(error).__name__}

    def finish(self):
        self.closed.set()
        if self.worker is not None:
            self.worker.join()

    def __exit__(self, *args):
        self.finish()
