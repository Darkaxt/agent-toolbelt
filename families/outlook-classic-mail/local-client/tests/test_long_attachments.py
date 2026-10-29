import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from outlook_classic_mail_client import client


class Attachment:
    def __init__(self, path):
        self.FileName = Path(path).name
        self.content = Path(path).read_bytes()

    def SaveAsFile(self, path):
        Path(path).write_bytes(self.content)


class Attachments(list):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.fail_add = False

    @property
    def Count(self):
        return len(self)

    def Add(self, path):
        self.calls.append(path)
        item = Attachment(path)
        self.append(item)
        if self.fail_add:
            raise RuntimeError('Native failure after insertion')
        return item

    def Item(self, index):
        return self[index - 1]


class Draft:
    def __init__(self):
        self.Attachments = Attachments()

    def Save(self):
        assert all(Path(path).exists() for path in self.Attachments.calls)


class LongAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.staging = self.root / 'stage'
        self.staging.mkdir()
        self.real_staging_root = client.attachment_staging_root
        self.patch = patch.object(client, 'attachment_staging_root', return_value=self.staging)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        directory = self.root / ('nested-' * 28)
        directory.mkdir()
        self.source = directory / ('résumé-' + 'x' * 150 + '.txt')
        self.payload = b'Long path\x00\xff' * 100
        self.source.write_bytes(self.payload)

    def test_long_path_preserves_unicode_filename_bytes_and_consumer_lifetime(self):
        details = client.prepare_draft_attachments([str(self.source)])
        draft = Draft()
        with client.attach_draft_files(draft, details):
            self.assertFalse(details['items'][0]['attached'])
            self.assertNotEqual(draft.Attachments.calls[0], str(self.source))
            self.assertLess(len(draft.Attachments.calls[0]), 260)
            draft.Save()
        self.assertEqual(draft.Attachments[0].FileName, self.source.name)
        self.assertEqual(draft.Attachments[0].content, self.payload)
        self.assertEqual(self.source.read_bytes(), self.payload)
        item = details['items'][0]
        self.assertTrue(item['content_verified'] and item['filename_verified'] and item['attached'])
        self.assertEqual(item['content_sha256'], hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(list(self.staging.iterdir()), [])

    def test_native_error_after_insertion_is_never_retried_and_stage_is_removed(self):
        draft = Draft()
        draft.Attachments.fail_add = True
        details = client.prepare_draft_attachments([str(self.source)])
        with self.assertRaisesRegex(RuntimeError, 'Native failure'):
            with client.attach_draft_files(draft, details):
                self.fail('Add must fail')
        self.assertEqual(len(draft.Attachments.calls), 1)
        self.assertFalse(details['items'][0]['attached'])
        self.assertEqual(list(self.staging.iterdir()), [])

    def test_save_failure_cleans_stage_without_claiming_attached(self):
        details = client.prepare_draft_attachments([str(self.source)])
        with self.assertRaisesRegex(RuntimeError, 'save failed'):
            with client.attach_draft_files(Draft(), details):
                raise RuntimeError('save failed')
        self.assertFalse(details['items'][0]['attached'])
        self.assertEqual(list(self.staging.iterdir()), [])

    def test_corrupt_saved_content_or_name_fails_verification(self):
        for corruption in ('content', 'FileName'):
            with self.subTest(corruption=corruption):
                draft = Draft()
                details = client.prepare_draft_attachments([str(self.source)])
                with self.assertRaisesRegex(ValueError, 'differs'):
                    with client.attach_draft_files(draft, details):
                        draft.Save()
                        setattr(draft.Attachments[0], corruption, b'bad' if corruption == 'content' else 'bad.txt')
                self.assertFalse(details['items'][0]['attached'])
                self.assertEqual(list(self.staging.iterdir()), [])

    def test_ordinary_short_path_and_no_attachments_need_no_staging(self):
        short = self.root / 'short.txt'
        short.write_bytes(self.payload)
        draft = Draft()
        details = client.prepare_draft_attachments([str(short)])
        with patch.object(client, 'attachment_staging_root', side_effect=AssertionError('no staging')):
            with client.attach_draft_files(draft, details):
                draft.Save()
            with client.attach_draft_files(draft, {}):
                draft.Save()
        self.assertEqual(draft.Attachments.calls, [str(short.resolve())])
        self.assertEqual(details['items'][0]['transport'], 'direct')

    def test_extended_path_is_staged_even_when_short(self):
        # The prefix itself is unsupported by some Outlook versions. Test the
        # decision separately from non-Windows filesystem interpretation.
        draft = Draft()
        details = {'items': [{'path': r'\\?\D:\short.txt', 'filename': 'short.txt', 'attached': False}]}
        original_open = Path.open
        def redirected_open(path, *args, **kwargs):
            if str(path) == details['items'][0]['path']:
                path = self.source
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', redirected_open):
            with client.attach_draft_files(draft, details):
                draft.Save()
        self.assertEqual(details['items'][0]['transport'], 'short_path_staging')
        self.assertTrue(details['items'][0]['attached'])

    def test_same_basename_keeps_independent_contents(self):
        other_dir = self.source.parent / 'other'
        other_dir.mkdir()
        other = other_dir / self.source.name
        other.write_bytes(b'different file')
        details = client.prepare_draft_attachments([str(self.source), str(other)])
        draft = Draft()
        with client.attach_draft_files(draft, details):
            draft.Save()
        self.assertEqual([item.content for item in draft.Attachments], [self.payload, b'different file'])
        self.assertTrue(all(item['content_verified'] for item in details['items']))
        self.assertEqual(list(self.staging.iterdir()), [])

    def test_near_limit_basename_is_truncated_without_changing_source(self):
        source = self.source.with_name('résumé-' + 'x' * 236 + '.pdf')
        source.write_bytes(self.payload)
        details = client.prepare_draft_attachments([str(source)])
        draft = Draft()
        with client.attach_draft_files(draft, details):
            draft.Save()
        item = details['items'][0]
        self.assertTrue(item['attached'] and item['filename_truncated'] and item['filename_verified'])
        self.assertEqual(item['filename'], source.name)
        self.assertEqual(item['attachment_filename'], draft.Attachments[0].FileName)
        self.assertTrue(item['attachment_filename'].endswith('.pdf'))
        self.assertIn('attachment_filename_truncated', item['warnings'])
        self.assertIn('attachment_filename_truncated', details['warnings'])
        self.assertLess(len(draft.Attachments.calls[0].encode('utf-16-le')) // 2, 260)
        self.assertEqual(source.read_bytes(), self.payload)
        self.assertEqual(list(self.staging.iterdir()), [])

    def test_truncation_is_unicode_safe_stable_and_disambiguates_names(self):
        directory = Path('E:/Temp/om-abcdefgh/0')
        first = '😀' * 115 + 'a.pdf'
        second = '😀' * 115 + 'b.pdf'
        names = [client.short_attachment_filename(name, directory) for name in (first, second)]
        self.assertNotEqual(*names)
        self.assertEqual(names[0], client.short_attachment_filename(first, directory))
        for name in names:
            self.assertTrue(name.endswith('.pdf'))
            self.assertLess(len(str(directory / name).encode('utf-16-le')) // 2, 260)
            self.assertEqual(name.encode('utf-16-le').decode('utf-16-le'), name)
        self.assertEqual(client.short_attachment_filename('plain.txt', directory), 'plain.txt')

    def test_extensionless_names_are_shortened_and_unrepresentable_extension_fails(self):
        directory = Path('E:/Temp/om-abcdefgh/0')
        shortened = client.short_attachment_filename('x' * 255, directory)
        self.assertNotIn('.', shortened)
        self.assertLess(len(str(directory / shortened)), 260)
        with self.assertRaisesRegex(ValueError, 'extension cannot fit'):
            client.short_attachment_filename('x.' + 'e' * 250, directory)

    def test_storage_selection_prefers_external_scratch_and_never_c(self):
        with patch.object(Path, 'is_dir', side_effect=lambda: False):
            with self.assertRaisesRegex(ValueError, 'E:/Temp or D:/Temp'):
                self.real_staging_root()
        with patch.object(Path, 'is_dir', autospec=True, side_effect=lambda path: str(path).startswith('D:')):
            with patch.object(Path, 'mkdir'):
                self.assertEqual(self.real_staging_root(), Path('D:/Temp'))


if __name__ == '__main__':
    unittest.main()
