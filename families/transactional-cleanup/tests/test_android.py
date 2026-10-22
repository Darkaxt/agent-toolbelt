from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_toolbelt_transactional_cleanup import android, cli
from agent_toolbelt_transactional_cleanup.engine import CleanupError


class FakeDevice:
    def __init__(self):
        self.identity = {'serial': 'test-serial', 'android_serial': 'hardware',
                         'fingerprint': 'build', 'model': 'fixture'}
        self.files = {'/storage/emulated/0/S12-fixture/a.bin': b'alpha'}
        self.directories = {'/storage/emulated/0/S12-fixture': 'dir'}
        self.calls = []
        self.installed = False
        self.install_stamp = 'first-install'
        self.uninstall_failure = False

    def endpoint(self):
        return dict(self.identity)

    def inventory(self, root):
        return [{'path': root, 'directory': True, 'identity': 'dir'}, *[
            self.snapshot(path) for path in sorted(self.files) if path.startswith(root + '/')]]

    def snapshot(self, path):
        if path in self.directories:
            return {'path': path, 'directory': True, 'identity': self.directories[path]}
        if path not in self.files:
            return None
        value = self.files[path]
        return {'path': path, 'directory': False, 'identity': 'file',
                'size': len(value), 'sha256': hashlib.sha256(value).hexdigest()}

    def remove(self, item, dry_run):
        self.calls.append(('remove', item['path'], dry_run))
        if item['directory']:
            if any(path.startswith(item['path'] + '/') for path in self.files):
                return 'not_empty'
            if not dry_run:
                self.directories.pop(item['path'], None)
            return 'would_delete' if dry_run else 'deleted'
        path = item['path']
        if path not in self.files:
            return 'missing'
        if self.snapshot(path) != item:
            return 'changed_after_review'
        if not dry_run:
            del self.files[path]
        return 'would_delete' if dry_run else 'deleted'

    def package(self, package):
        return None if not self.installed else {'package': package, 'apk_hashes': [{'sha256': 'a' * 64}],
                                              'install_identity': self.install_stamp}

    def uninstall(self, package):
        self.calls.append(('uninstall', package))
        if self.uninstall_failure:
            raise CleanupError('adb_failed', 'package manager refused test removal')
        self.installed = False


class AndroidTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='D:/Temp' if os.name == 'nt' else None)
        self.device = FakeDevice()
        self.engine = android.AndroidCleanup(Path(self.temp.name) / 'state', device=self.device)
        self.root = '/storage/emulated/0/S12-fixture'

    def tearDown(self):
        self.temp.cleanup()

    def review(self):
        return self.engine.review(self.root, 'S12 testing', 'test-generated reference files')

    def ticket(self, review, **kwargs):
        return self.engine.ticket(review['transaction_id'], review['manifest_sha256'], **kwargs)['ticket_id']

    def test_review_inspect_dry_run_apply_and_compaction(self):
        review = self.review()
        self.assertFalse(self.device.calls)
        page = self.engine.inspect(review['transaction_id'], 0, 1)
        self.assertEqual(len(page['items']), 1)
        ticket = self.ticket(review)
        self.assertTrue(self.engine.apply(ticket, True)['ok'])
        self.assertTrue(self.device.files)
        result = self.engine.apply(ticket)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['deleted_bytes'], 5)
        self.assertFalse(self.device.files)
        self.assertFalse(self.engine.status(review['transaction_id'])['detailed_state_retained'])
        self.assertTrue(self.engine.apply(ticket)['ok'])

    def test_new_and_changed_members_survive_and_retry_is_exact(self):
        review = self.review()
        ticket = self.ticket(review)
        self.device.files[self.root + '/new.bin'] = b'new'
        self.device.files[self.root + '/a.bin'] = b'changed'
        result = self.engine.apply(ticket)
        self.assertFalse(result['ok'])
        self.assertEqual(result['counts']['changed_after_review'], 1)
        self.assertEqual(len(self.device.files), 2)
        self.device.files[self.root + '/a.bin'] = b'alpha'
        result = self.engine.apply(ticket)
        self.assertEqual(result['deleted_bytes'], 5)
        self.assertEqual(list(self.device.files), [self.root + '/new.bin'])

    def test_device_change_and_bad_manifest_hash_fail_before_mutation(self):
        review = self.review()
        with self.assertRaises(CleanupError):
            self.engine.ticket(review['transaction_id'], '0' * 64)
        ticket = self.ticket(review)
        self.device.identity['android_serial'] = 'another-device'
        with self.assertRaises(CleanupError) as failure:
            self.engine.apply(ticket)
        self.assertEqual(failure.exception.kind, 'device_identity_changed')
        self.assertFalse(self.device.calls)

    def test_signed_state_tampering_rejected(self):
        review = self.review()
        path = self.engine.record_path(review['transaction_id'])
        value = json.loads(path.read_text())
        value['payload']['manifest']['root'] = '/storage/emulated/0/DCIM'
        path.write_text(json.dumps(value))
        with self.assertRaises(CleanupError):
            self.engine.inspect(review['transaction_id'])

    def test_revoke_compacts_and_prevents_application(self):
        review = self.review()
        ticket = self.ticket(review)
        self.engine.revoke(ticket)
        with self.assertRaises(CleanupError):
            self.engine.apply(ticket)
        self.assertFalse(self.device.calls)

    def test_protected_paths_and_traversal(self):
        for path in ('/', '/sdcard', '/data/local/tmp', '/storage/emulated/0',
                     '/storage/emulated/0/Android/data/app', '/storage/emulated/0/DCIM',
                     '/storage/emulated/0/ROMs', self.root + '/../DCIM', self.root + '//x'):
            with self.subTest(path=path), self.assertRaises(CleanupError):
                self.engine.review(path, 'task', 'evidence')

    def download_fixture(self):
        self.root = '/storage/emulated/0/Download/20MTD-Revamped-1.0.0-deployer'
        self.shared_parent = '/storage/emulated/0/Download'
        self.device.directories = {self.root: 'dir', self.shared_parent: 'download-dir'}
        self.device.files = {self.root + '/installer.ps1': b'installer',
                             self.shared_parent + '/personal.pdf': b'preserve sibling'}

    def test_download_task_ticket_removes_only_reviewed_files_and_empty_task_root(self):
        self.download_fixture()
        review = self.review()
        page = self.engine.inspect(review['transaction_id'])
        self.assertEqual(page['root_ancestors'],
                         [{'path': self.shared_parent, 'directory': True, 'identity': 'download-dir'}])
        self.assertEqual({item['path'] for item in page['items']},
                         {self.root, self.root + '/installer.ps1'})
        ticket = self.ticket(review)
        self.assertTrue(self.engine.apply(ticket, True)['ok'])
        self.assertIn(self.root + '/installer.ps1', self.device.files)
        self.assertTrue(self.engine.apply(ticket)['ok'])
        self.assertEqual(self.device.files,
                         {self.shared_parent + '/personal.pdf': b'preserve sibling'})
        self.assertEqual(self.device.directories, {self.shared_parent: 'download-dir'})
        self.assertNotIn(('remove', self.shared_parent, False), self.device.calls)

    def test_download_new_and_changed_task_files_survive_exact_retry(self):
        self.download_fixture()
        ticket = self.ticket(self.review())
        self.device.files[self.root + '/installer.ps1'] = b'changed installer'
        self.device.files[self.root + '/new.txt'] = b'new user content'
        result = self.engine.apply(ticket)
        self.assertFalse(result['ok'])
        self.assertEqual(result['counts']['changed_after_review'], 1)
        self.assertEqual(self.device.files[self.root + '/new.txt'], b'new user content')
        self.device.files[self.root + '/installer.ps1'] = b'installer'
        result = self.engine.apply(ticket)
        self.assertFalse(result['ok'])
        self.assertEqual(result['deleted_bytes'], 9)
        self.assertEqual(self.device.files, {self.root + '/new.txt': b'new user content',
                                           self.shared_parent + '/personal.pdf': b'preserve sibling'})

    def test_download_shared_parent_replacement_blocks_apply(self):
        self.download_fixture()
        ticket = self.ticket(self.review())
        self.device.directories[self.shared_parent] = 'replacement-parent'
        with self.assertRaises(CleanupError) as failure:
            self.engine.apply(ticket)
        self.assertEqual(failure.exception.kind, 'android_ancestor_changed')
        self.assertFalse(self.device.calls)

    def test_download_shared_parent_replacement_during_inventory_rejects_review(self):
        self.download_fixture()
        inventory = self.device.inventory
        def replaced(root):
            items = inventory(root)
            self.device.directories[self.shared_parent] = 'replacement-parent'
            return items
        self.device.inventory = replaced
        with self.assertRaises(CleanupError) as failure:
            self.review()
        self.assertEqual(failure.exception.kind, 'android_ancestor_changed')
        self.assertFalse(self.device.calls)

    def test_download_shared_parent_change_between_members_preserves_remaining_files(self):
        self.download_fixture()
        self.device.files[self.root + '/second.ps1'] = b'second installer'
        ticket = self.ticket(self.review())
        remove = self.device.remove
        def replace_after_first(item, dry_run):
            result = remove(item, dry_run)
            if not dry_run and result == 'deleted':
                self.device.directories[self.shared_parent] = 'replacement-parent'
            return result
        self.device.remove = replace_after_first
        with self.assertRaises(CleanupError) as failure:
            self.engine.apply(ticket)
        self.assertEqual(failure.exception.kind, 'android_ancestor_changed')
        self.assertEqual(sum(path.startswith(self.root + '/') for path in self.device.files), 1)
        self.assertIn(self.shared_parent + '/personal.pdf', self.device.files)

    def test_download_broad_roots_protected_names_and_aliases_fail_before_transport(self):
        for path in ('/storage/emulated/0/Download', '/storage/emulated/0/Download/',
                     '/storage/emulated/0/Downloads/task', '/storage/emulated/0/Documents/task',
                     '/storage/emulated/0/Download/Android', '/storage/emulated/0/Download/Saves',
                     '/storage/emulated/0/Download/task/nested', '/sdcard/Download/task',
                     '/storage/emulated/0/Download/task/../other'):
            with self.subTest(path=path), self.assertRaises(CleanupError) as failure:
                self.engine.review(path, 'task', 'evidence')
            self.assertEqual(failure.exception.kind, 'protected_android_path')
        self.assertFalse(self.device.calls)

    def test_package_absence_baseline_and_data_acknowledgement_required(self):
        baseline = self.engine.package_baseline('org.example.test', 'S12', 'temporary test APK', ['a' * 64])
        self.device.installed = True
        review = self.engine.package_review(baseline['transaction_id'])
        with self.assertRaises(CleanupError):
            self.ticket(review)
        ticket = self.ticket(review, confirm_test_app_data=True)
        self.assertTrue(self.engine.apply(ticket, True)['ok'])
        self.assertTrue(self.device.installed)
        self.assertTrue(self.engine.apply(ticket)['ok'])
        self.assertFalse(self.device.installed)

    def test_preexisting_and_replaced_packages_are_preserved(self):
        self.device.installed = True
        with self.assertRaises(CleanupError):
            self.engine.package_baseline('org.example.test', 'S12', 'test', ['a' * 64])
        self.device.installed = False
        baseline = self.engine.package_baseline('org.example.test', 'S12', 'test', ['a' * 64])
        self.device.installed = True
        review = self.engine.package_review(baseline['transaction_id'])
        ticket = self.ticket(review, confirm_test_app_data=True)
        self.device.install_stamp = 'reinstalled'
        result = self.engine.apply(ticket)
        self.assertFalse(result['ok'])
        self.assertTrue(self.device.installed)
        self.assertFalse(self.device.calls)

    def test_failed_uninstall_is_retryable_not_success(self):
        baseline = self.engine.package_baseline('org.example.test', 'S12', 'test', ['a' * 64])
        self.device.installed = True
        ticket = self.ticket(self.engine.package_review(baseline['transaction_id']), confirm_test_app_data=True)
        self.device.uninstall_failure = True
        self.assertFalse(self.engine.apply(ticket)['ok'])
        self.device.uninstall_failure = False
        self.assertTrue(self.engine.apply(ticket)['ok'])

    def test_unexpected_apk_cannot_be_registered_as_task_installation(self):
        baseline = self.engine.package_baseline('org.example.test', 'S12', 'test', ['b' * 64])
        self.device.installed = True
        with self.assertRaises(CleanupError) as failure:
            self.engine.package_review(baseline['transaction_id'])
        self.assertEqual(failure.exception.kind, 'test_package_mismatch')
        self.assertFalse(self.device.calls)

    def test_state_inventory_and_missing_root_retry(self):
        review = self.review()
        ticket = self.ticket(review)
        self.assertEqual(self.engine.state_inventory()['unfinished_count'], 1)
        self.device.files.clear()
        self.device.snapshot = lambda path: None
        self.assertTrue(self.engine.apply(ticket)['ok'])
        self.assertEqual(self.engine.state_inventory()['unfinished_count'], 0)

    def test_changed_ancestor_preserves_descendant(self):
        original_inventory = self.device.inventory
        child = self.root + '/nested'
        self.device.files = {child + '/a.bin': b'alpha'}
        def inventory(root):
            return original_inventory(root) + [{'path': child, 'directory': True, 'identity': 'old-directory'}]
        self.device.inventory = inventory
        review = self.review()
        ticket = self.ticket(review)
        original = self.device.snapshot
        self.device.snapshot = lambda path: ({'path': child, 'directory': True, 'identity': 'new-directory'}
                                             if path == child else original(path))
        result = self.engine.apply(ticket)
        self.assertFalse(result['ok'])
        self.assertIn(child + '/a.bin', self.device.files)
        self.assertEqual(result['counts']['changed_ancestor'], 1)

    def test_cli_routes_android_without_host_windows_scan(self):
        args = cli.parser().parse_args(['adb-review', '--serial', 'test-serial',
                                      '--root', self.root, '--owner-task', 'S12', '--evidence', 'fixture'])
        self.assertEqual(args.command, 'adb-review')
        with patch.object(android, 'AndroidCleanup', return_value=self.engine):
            import io
            from contextlib import redirect_stdout
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(cli.main(['--state-root', str(self.engine.host.root), 'adb-review',
                                          '--serial', 'test-serial', '--root', self.root,
                                          '--owner-task', 'S12', '--evidence', 'fixture']), 0)
            self.assertTrue(json.loads(output.getvalue())['ok'])

    def test_overlapping_device_targets_are_locked_but_independent_roots_are_not(self):
        review = self.review()
        manifest = self.engine.load(review['transaction_id'])['manifest']
        with self.engine.host.locked(self.engine.locks(manifest), operation='fixture'):
            with self.assertRaises(CleanupError) as failure:
                self.review()
            self.assertEqual(failure.exception.kind, 'target_busy')
            self.engine.review('/storage/emulated/0/Other-fixture', 'test', 'independent task output')

    def test_discard_does_not_delete_files_or_allow_issued_ticket(self):
        review = self.review()
        self.engine.discard(review['transaction_id'], 'unused test review')
        self.assertTrue(self.device.files)
        self.assertFalse(self.engine.status(review['transaction_id'])['detailed_state_retained'])
        review = self.review()
        self.ticket(review)
        with self.assertRaises(CleanupError):
            self.engine.discard(review['transaction_id'], 'cannot discard ticket')

    def test_root_replacement_prevents_deletion(self):
        review = self.review()
        ticket = self.ticket(review)
        original = self.device.snapshot
        def replacement(path):
            value = original(path)
            if value and value['directory']:
                value['identity'] = 'replacement-root'
            return value
        self.device.snapshot = replacement
        with self.assertRaises(CleanupError):
            self.engine.apply(ticket)
        self.assertFalse(self.device.calls)


class AdbTransportTests(unittest.TestCase):
    def device(self, runner):
        return android.AdbDevice('fixture-serial', adb_path=sys.executable, runner=runner)

    def test_endpoint_accepts_adb_crlf_output(self):
        def runner(command, **kwargs):
            output = (b'device\r\n' if command[-1] == 'get-state' else
                      b'[ro.serialno]: [hardware]\r\n[ro.build.fingerprint]: [build]\r\n[ro.product.model]: [model]\r\n')
            return subprocess.CompletedProcess(command, 0, output, b'')
        self.assertEqual(self.device(runner).endpoint()['android_serial'], 'hardware')

    def test_exact_serial_identity_and_offline_rejection(self):
        calls = []
        def runner(command, **kwargs):
            calls.append(command)
            output = (b'device\n' if command[-1] == 'get-state' else
                      b'[ro.serialno]: [hardware]\n[ro.build.fingerprint]: [build]\n[ro.product.model]: [model]\n')
            return subprocess.CompletedProcess(command, 0, output, b'')
        self.assertEqual(self.device(runner).endpoint()['android_serial'], 'hardware')
        self.assertTrue(all(command[1:3] == ['-s', 'fixture-serial'] for command in calls))
        with self.assertRaises(CleanupError):
            self.device(lambda command, **kw: subprocess.CompletedProcess(command, 1, b'', b'device unauthorized')).endpoint()
        with self.assertRaises(CleanupError):
            android.AdbDevice('', adb_path=sys.executable)

    def test_package_users_system_protection_and_install_identity(self):
        def runner(command, **kwargs):
            script = kwargs.get('input', b'').decode()
            if script == 'pm list users\n':
                output = b'Users:\n UserInfo{0:Owner:13} running\n'
            elif script.startswith('pm list packages'):
                output = b'package:org.example.test\n'
            elif script.startswith('dumpsys'):
                output = b' codePath=/data/app/test\n versionCode=1 minSdk=23\n firstInstallTime=2026-10-14\n lastUpdateTime=2026-10-14\n userId=12345\n pkgFlags=[ HAS_CODE ]\n'
            elif script.startswith('pm path'):
                output = b'package:/data/app/test/base.apk\n'
            else:
                output = b'1:2:81a4:5:1:1\nfile\n' + b'a' * 64 + b'\n'
            return subprocess.CompletedProcess(command, 0, output, b'')
        device = self.device(runner)
        result = device.package('org.example.test')
        self.assertEqual(result['apk_hashes'][0]['sha256'], 'a' * 64)
        def system(command, **kwargs):
            value = runner(command, **kwargs)
            if kwargs.get('input', b'').startswith(b'dumpsys'):
                value.stdout = value.stdout.replace(b'HAS_CODE', b'SYSTEM HAS_CODE')
            return value
        with self.assertRaises(CleanupError):
            self.device(system).package('org.example.test')
        def diagnostic(command, **kwargs):
            value = runner(command, **kwargs)
            if kwargs.get('input', b'').startswith(b'pm list packages'):
                value.stdout, value.stderr = b'', b'SecurityException'
            return value
        with self.assertRaises(CleanupError):
            self.device(diagnostic).package('org.example.test')

    def test_real_shell_hash_checks_quoting_and_exact_unlink(self):
        bash = r'C:\Program Files\Git\bin\bash.exe' if os.name == 'nt' else shutil.which('sh')
        if not bash or not Path(bash).is_file():
            self.skipTest('POSIX shell unavailable for script integration')
        with tempfile.TemporaryDirectory(dir='D:/Temp' if os.name == 'nt' else None) as directory:
            folder = Path(directory)
            victim = folder / "one ' $(touch escaped).bin"
            victim.write_bytes(b'alpha')
            new = folder / 'new.bin'
            new.write_bytes(b'preserve')
            def posix(path):
                value = path.as_posix()
                return '/' + value[0].lower() + value[2:] if os.name == 'nt' else value
            def runner(command, **kwargs):
                return subprocess.run([bash, '-s'], input=kwargs.get('input'), capture_output=True,
                                      env=dict(os.environ, MSYS_NO_PATHCONV='1'))
            device = self.device(runner)
            item = device.snapshot(posix(victim))
            self.assertEqual(item['sha256'], hashlib.sha256(b'alpha').hexdigest())
            self.assertEqual(device.remove(item, True), 'would_delete')
            self.assertTrue(victim.exists())
            victim.write_bytes(b'changed')
            self.assertEqual(device.remove(item, False), 'changed_after_review')
            self.assertTrue(victim.exists())
            item = device.snapshot(posix(victim))
            self.assertEqual(device.remove(item, False), 'deleted')
            self.assertEqual(device.remove(item, False), 'missing')
            self.assertTrue(new.exists())
            self.assertFalse((folder / 'escaped').exists())
            directory_item = device.snapshot(posix(folder))
            self.assertEqual(device.remove(directory_item, False), 'not_empty')

    def test_symlink_and_ancestor_symlink_never_unlinked(self):
        if os.name == 'nt':
            self.skipTest('POSIX symlink test; Windows junctions covered by host suite')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'target'
            target.mkdir()
            (target / 'data').write_bytes(b'preserve')
            link = root / 'link'
            link.symlink_to(target, target_is_directory=True)
            def runner(command, **kwargs):
                return subprocess.run(['sh'], input=kwargs.get('input'), capture_output=True)
            with self.assertRaises(CleanupError):
                self.device(runner).snapshot(str(link / 'data'))
            self.assertTrue((target / 'data').exists())


if __name__ == '__main__':
    unittest.main()
