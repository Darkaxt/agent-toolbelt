from __future__ import annotations

import ctypes
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_toolbelt_transactional_cleanup import filesystem as fs
from agent_toolbelt_transactional_cleanup.engine import Engine


@unittest.skipUnless(os.name == 'nt', 'Windows handle identity')
class ExfatIdentityTests(unittest.TestCase):
    def legacy_info(self, opened, output):
        info = output._obj
        info.volume, info.index_low, info.links = 42, 17, 1
        info.created.dwLowDateTime = 123
        return True

    def test_only_confirmed_exfat_uses_legacy_identity(self):
        with patch.object(fs.kernel, 'GetFileInformationByHandle', side_effect=self.legacy_info), \
             patch.object(fs.kernel, 'GetFileInformationByHandleEx', return_value=False), \
             patch.object(ctypes, 'get_last_error', return_value=87), \
             patch.object(fs, 'filesystem_from_handle', return_value='exFAT', create=True):
            info = fs.from_handle(1)
        self.assertEqual(info['identity_kind'], 'exfat_file_index_64')
        self.assertEqual(info['identity'], 'exfat:42:17:0:123')
        self.assertEqual(info['filesystem'], 'exFAT')

    def test_refs_does_not_downgrade_its_128_bit_identity(self):
        with patch.object(fs.kernel, 'GetFileInformationByHandle', side_effect=self.legacy_info), \
             patch.object(fs.kernel, 'GetFileInformationByHandleEx', return_value=False), \
             patch.object(ctypes, 'get_last_error', return_value=87), \
             patch.object(fs, 'filesystem_from_handle', return_value='ReFS', create=True):
            with self.assertRaises(OSError) as error:
                fs.from_handle(1)
        self.assertEqual(error.exception.winerror, 87)

    def test_access_failure_is_not_an_exfat_compatibility_fallback(self):
        with patch.object(fs.kernel, 'GetFileInformationByHandle', side_effect=self.legacy_info), \
             patch.object(fs.kernel, 'GetFileInformationByHandleEx', return_value=False), \
             patch.object(ctypes, 'get_last_error', return_value=5), \
             patch.object(fs, 'filesystem_from_handle', return_value='exFAT', create=True) as detect:
            with self.assertRaises(OSError) as error:
                fs.from_handle(1)
        self.assertEqual(error.exception.winerror, 5)
        detect.assert_not_called()

    def test_existing_128_bit_identity_format_is_unchanged(self):
        def extended(opened, kind, output, size):
            output._obj.volume = 99
            output._obj.identifier[0] = 5
            return True
        with patch.object(fs.kernel, 'GetFileInformationByHandle', side_effect=self.legacy_info), \
             patch.object(fs.kernel, 'GetFileInformationByHandleEx', side_effect=extended):
            info = fs.from_handle(1)
        self.assertEqual(info['identity'], '99:05' + '00' * 15 + ':0:123')
        self.assertEqual(info['identity_kind'], 'windows_file_id_128')

    def test_unusable_exfat_regular_file_index_is_rejected(self):
        def no_index(opened, output):
            self.legacy_info(opened, output)
            output._obj.index_low = 0
            return True
        with patch.object(fs.kernel, 'GetFileInformationByHandle', side_effect=no_index), \
             patch.object(fs.kernel, 'GetFileInformationByHandleEx', return_value=False), \
             patch.object(ctypes, 'get_last_error', return_value=87), \
             patch.object(fs, 'filesystem_from_handle', return_value='exFAT'):
            with self.assertRaises(ValueError):
                fs.from_handle(1)


@unittest.skipUnless(os.name == 'nt' and Path('E:/Temp').is_dir(), 'Live E: exFAT fixture')
class ExfatCleanupTests(unittest.TestCase):
    def setUp(self):
        if fs.filesystem_type('E:\\') != 'exFAT':
            self.skipTest('E: is not exFAT')
        self.scratch = tempfile.TemporaryDirectory(prefix='cleanup-exfat-test-', dir='E:/Temp')
        self.state = tempfile.TemporaryDirectory(prefix='cleanup-exfat-state-', dir='D:/Temp')
        self.root = Path(self.scratch.name)
        self.work = self.root / 'workspace'
        self.work.mkdir()
        self.out = self.root / 'build'
        self.out.mkdir()
        self.file = self.out / 'compiler.bin'
        self.file.write_bytes(b'compiled output')
        self.engine = Engine(Path(self.state.name))
        self.transaction = self.engine.begin(self.work, [str(self.out)])['transaction_id']
        self.engine.register(self.transaction, self.out, 'compiler-output',
                             'disposable exFAT regression fixture', regenerated=True)

    def tearDown(self):
        self.state.cleanup()
        self.scratch.cleanup()

    def ticket(self):
        review = self.engine.review(self.transaction)
        self.assertEqual(review['candidate_count'], 2)
        items = self.engine.inspect(self.transaction)['page_items']
        file = next(item for item in items if item['path'] == str(self.file))
        self.assertEqual(len(file['content_sha256']), 64)
        self.assertEqual(file['identity_kind'], 'exfat_file_index_64')
        return self.engine.ticket(self.transaction, review['manifest_sha256'])['ticket_id']

    def test_live_review_dry_run_and_delete(self):
        ticket = self.ticket()
        self.engine.apply(ticket, dry_run=True)
        self.assertTrue(self.file.exists())
        result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'applied')
        self.assertEqual(result['deleted_bytes'], len(b'compiled output'))
        self.assertFalse(self.out.exists())

    def test_same_identity_edit_is_preserved_even_with_restored_timestamp(self):
        ticket = self.ticket()
        stamp = self.file.stat()
        before = fs.identity(self.file)
        self.file.write_bytes(b'changed! output')
        os.utime(self.file, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        after = fs.identity(self.file)
        self.assertEqual((before['identity'], before['size'], before['mtime']),
                         (after['identity'], after['size'], after['mtime']))
        result = self.engine.apply(ticket)
        self.assertEqual(result['result_counts'].get('modified_after_review'), 1)
        self.assertTrue(self.file.exists())
        self.engine.revoke(ticket)

    def test_new_concurrent_file_survives(self):
        ticket = self.ticket()
        new = self.out / 'new.bin'
        new.write_bytes(b'not in ticket')
        result = self.engine.apply(ticket)
        self.assertFalse(self.file.exists())
        self.assertEqual(new.read_bytes(), b'not in ticket')
        self.assertEqual(result['ticket_state'], 'partially_applied')
        self.engine.revoke(ticket)

    def test_missing_content_proof_never_deletes(self):
        entry = {'path': str(self.file), **fs.identity(self.file)}
        outcome, _ = fs.delete_exact(entry)
        self.assertEqual(outcome, 'protected')
        self.assertTrue(self.file.exists())

    def test_replacement_survives(self):
        ticket = self.ticket()
        replacement = self.out / 'replacement.bin'
        replacement.write_bytes(b'new replacement')
        os.replace(replacement, self.file)
        result = self.engine.apply(ticket)
        self.assertTrue(self.file.exists())
        self.assertEqual(result['ticket_state'], 'partially_applied')
        self.engine.revoke(ticket)

    def test_locked_file_is_retryable(self):
        ticket = self.ticket()
        with fs.handle(self.file, delete=True):
            result = self.engine.apply(ticket)
        self.assertEqual(result['result_counts'].get('locked'), 1)
        self.assertTrue(self.file.exists())
        self.assertEqual(self.engine.apply(ticket)['ticket_state'], 'applied')

    def test_unreadable_content_does_not_block_other_files(self):
        other = self.out / 'other.bin'
        other.write_bytes(b'other generated bytes')
        original = fs.content_snapshot
        def snapshot(entry):
            if entry['path'] == str(self.file):
                raise PermissionError('fixture content lock')
            return original(entry)
        with patch.object(fs, 'content_snapshot', side_effect=snapshot):
            review = self.engine.review(self.transaction)
        excluded = self.engine.inspect(self.transaction, decision='excluded')['page_items']
        self.assertEqual(excluded[0]['reason'], 'content_snapshot_unavailable')
        ticket = self.engine.ticket(self.transaction, review['manifest_sha256'])['ticket_id']
        self.engine.apply(ticket)
        self.assertTrue(self.file.exists())
        self.assertFalse(other.exists())
        self.engine.revoke(ticket)

    def test_read_only_generated_file_is_deleted_by_verified_handle(self):
        os.chmod(self.file, 0o444)
        ticket = self.ticket()
        self.assertEqual(self.engine.apply(ticket)['ticket_state'], 'applied')
        self.assertFalse(self.file.exists())


if __name__ == '__main__':
    unittest.main()
