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
                                         cwd=root, env=env, capture_output=True, text=True, check=True)
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
