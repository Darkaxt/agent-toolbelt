from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

FAMILY = Path(__file__).resolve().parents[1]


class InstalledWorkflowTests(unittest.TestCase):
    def test_upgrade_retains_previous_runtime_for_active_legacy_state(self):
        with tempfile.TemporaryDirectory(dir='D:/Temp') as directory:
            root = Path(directory)
            home, local = root / 'home', root / 'local'
            command = [sys.executable, '-B', str(FAMILY / 'scripts/install.py'),
                       '--home', str(home), '--local-appdata', str(local)]
            first = json.loads(subprocess.run(command, capture_output=True, text=True, check=True).stdout)
            state = local / 'Tools/transactional-cleanup/state'
            state.mkdir(parents=True)
            (state / ('a' * 32 + '.json')).write_text(
                '{"payload":{"state":"open"},"mac":"legacy"}', encoding='utf-8')
            second = json.loads(subprocess.run(command, capture_output=True, text=True, check=True).stdout)
            self.assertEqual(second['legacy_active_state_count'], 1)
            self.assertEqual(second['legacy_runtime_retained'], first['active_runtime'])
            self.assertTrue(Path(first['active_runtime']).is_dir())
            active = json.loads((local / 'Tools/transactional-cleanup/active.json').read_text())
            self.assertEqual(active['legacy_source'], first['active_runtime'])
            third = json.loads(subprocess.run(command, capture_output=True, text=True, check=True).stdout)
            active = json.loads((local / 'Tools/transactional-cleanup/active.json').read_text())
            self.assertEqual(active['legacy_source'], first['active_runtime'])
            self.assertEqual(third['legacy_runtime_retained'], first['active_runtime'])
            self.assertTrue(Path(first['active_runtime']).is_dir())
            self.assertFalse(Path(second['active_runtime']).exists())
            releases = local / 'Tools/transactional-cleanup/releases'
            self.assertEqual(len([path for path in releases.iterdir() if path.is_dir()]), 2)

    @unittest.skipUnless(os.name == 'nt', 'Windows junction guard')
    def test_redirected_skill_destination_rejected_before_deployment(self):
        with tempfile.TemporaryDirectory(dir='D:/Temp') as directory:
            root = Path(directory)
            home, local, outside = root / 'home', root / 'local', root / 'outside'
            skill = home / '.codex/skills/transactional-cleanup'
            skill.parent.mkdir(parents=True)
            outside.mkdir()
            subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
                            f"New-Item -ItemType Junction -Path '{skill}' -Target '{outside}' | Out-Null"],
                           capture_output=True, check=True)
            try:
                result = subprocess.run([sys.executable, '-B', str(FAMILY / 'scripts/install.py'),
                                         '--home', str(home), '--local-appdata', str(local)],
                                        capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Reparse point protected', result.stderr)
                self.assertFalse(local.exists())
                self.assertEqual(list(outside.iterdir()), [])
            finally:
                skill.rmdir()

    def test_installed_wrapper_transaction_and_reinstall(self):
        with tempfile.TemporaryDirectory(dir='D:/Temp') as directory:
            root = Path(directory)
            home, local = root / 'home', root / 'local'
            work = root / 'workspace'
            work.mkdir()
            def install():
                process = subprocess.run([sys.executable, '-B', str(FAMILY / 'scripts/install.py'),
                                          '--home', str(home), '--local-appdata', str(local)],
                                         capture_output=True, text=True, check=True)
                return json.loads(process.stdout)
            first = install()
            env = dict(os.environ, LOCALAPPDATA=str(local), PYTHONDONTWRITEBYTECODE='1')
            env.pop('AGENT_TOOLBELT_HOME', None)
            wrapper = home / '.codex/skills/transactional-cleanup/scripts/invoke_transactional_cleanup.py'
            def run(*args):
                process = subprocess.run([sys.executable, '-B', str(wrapper), *args],
                                         cwd=root, env=env, capture_output=True, text=True)
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
                return json.loads(process.stdout)
            start = run('begin', '--workspace', str(work), '--scan-root', str(work))
            transaction = start['transaction_id']
            out = work / 'build'
            run('register', '--transaction', transaction, '--path', str(out),
                '--kind', 'compiler-output', '--evidence', 'installed integration fixture')
            out.mkdir()
            (out / 'output.bin').write_bytes(b'12345')
            review = run('review', '--transaction', transaction)
            ticket = run('ticket', '--transaction', transaction, '--manifest-sha256', review['manifest_sha256'])['ticket_id']
            dry = run('apply', '--ticket', ticket, '--dry-run')
            self.assertEqual(dry['deleted_bytes'], 0)
            self.assertTrue((out / 'output.bin').exists())
            result = run('apply', '--ticket', ticket)
            self.assertEqual(result['deleted_bytes'], 5)
            self.assertFalse(out.exists())

            # Exercise the activated runtime, not the repository's imported Engine.
            probe = '''
import sys
from pathlib import Path
from unittest.mock import patch
from agent_toolbelt_transactional_cleanup import cli, filesystem as fs
from agent_toolbelt_transactional_cleanup.engine import Engine
root = Path(sys.argv[1]); root.mkdir()
work = root / 'work'; work.mkdir()
engine = Engine(root / 'state')
transaction = engine.begin(work)['transaction_id']
output = work / 'build'
engine.register(transaction, output, 'compiler-output', 'installed concurrency fixture')
output.mkdir()
for index in range(8):
    (output / f'{index}.bin').write_bytes(b'x')
review = engine.review(transaction)
ticket = engine.ticket(transaction, review['manifest_sha256'])['ticket_id']
other = root / 'other'; other.mkdir()
independent = engine.begin(work, [other])['transaction_id']
delete_exact = fs.delete_exact
calls = 0
def delete_with_writer(item, dry_run=False):
    global calls
    calls += 1
    if calls == 3:
        writer = engine.connect()
        try:
            writer.execute('UPDATE transactions SET progress_processed=1 WHERE transaction_id=?', (independent,))
            writer.commit()
        finally:
            writer.close()
    return delete_exact(item, dry_run=dry_run)
with patch('agent_toolbelt_transactional_cleanup.engine.BATCH_SIZE', 2), patch.object(fs, 'delete_exact', side_effect=delete_with_writer):
    result = cli.main(['--state-root', str(root / 'state'), 'apply', '--ticket', ticket])
assert not output.exists()
assert engine.txn(independent)['state'] == 'open'
raise SystemExit(result)
'''
            process = subprocess.run([sys.executable, '-B', '-c', probe, str(root / 'concurrent')],
                                     cwd=root, env=dict(env, PYTHONPATH=first['active_runtime']),
                                     capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            concurrent_result = json.loads(process.stdout)
            self.assertEqual(concurrent_result['ticket_state'], 'applied')
            self.assertEqual(concurrent_result['deleted_bytes'], 8)

            disposable = root / 'installed-validation-clone'
            disposable.mkdir()
            subprocess.run(['git', 'init', str(disposable)], check=True, capture_output=True)
            (disposable / 'fixture.txt').write_text('tracked validation data', encoding='utf-8')
            subprocess.run(['git', '-C', str(disposable), 'add', '.'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(disposable), '-c', 'user.name=Cleanup Tests',
                            '-c', 'user.email=cleanup@example.invalid', 'commit', '-m', 'fixture'],
                           check=True, capture_output=True)
            repository_start = run('begin', '--workspace', str(work),
                                   '--scan-root', str(disposable))
            repository_transaction = repository_start['transaction_id']
            run('register', '--transaction', repository_transaction, '--path', str(disposable),
                '--kind', 'disposable-repository', '--evidence', 'installed validation clone',
                '--regenerated', '--allow-disposable-repository')
            repository_review = run('review', '--transaction', repository_transaction)
            repository_ticket = run(
                'ticket', '--transaction', repository_transaction,
                '--manifest-sha256', repository_review['manifest_sha256'])['ticket_id']
            repository_result = run('apply', '--ticket', repository_ticket)
            self.assertEqual(repository_result['ticket_state'], 'applied', repository_result)
            self.assertFalse(disposable.exists())

            second = install()
            self.assertFalse(Path(first['active_runtime']).exists())
            self.assertTrue(Path(second['active_runtime']).exists())
            self.assertEqual(second['deployment_residuals'], [])
            for folder in ('.codex', '.agents', '.claude'):
                installed = home / folder / 'skills/transactional-cleanup'
                self.assertEqual((installed / 'SKILL.md').read_bytes(),
                                 (FAMILY / 'codex/skills/transactional-cleanup/SKILL.md').read_bytes())
            self.assertFalse(run('status', '--transaction', transaction)['detailed_state_retained'])

    def test_bundles_match(self):
        codex = FAMILY / 'codex/skills/transactional-cleanup'
        claude = FAMILY / 'claude/marketplaces/agent-toolbelt-local/plugins/transactional-cleanup/skills/transactional-cleanup'
        for name in ('SKILL.md', 'scripts/invoke_transactional_cleanup.py'):
            self.assertEqual((codex / name).read_bytes(), (claude / name).read_bytes())


if __name__ == '__main__':
    unittest.main()
