"""Opt-in owned Outlook attachment probe. Never sends or touches existing drafts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client-home', type=Path, required=True)
    parser.add_argument('--runtime-home', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--extended', action='store_true')
    args = parser.parse_args()
    sys.path.insert(0, str(args.client_home / 'src'))
    from outlook_classic_mail_client import client
    args.scratch.mkdir(parents=True, exist_ok=True)
    source_dir = args.scratch / ('source-' + uuid.uuid4().hex) / ('nested-' * 18)
    source_dir.mkdir(parents=True)
    source = source_dir / ('attachment-résumé-' + 'long-name-' * 18 + '.txt')
    payload = b'Outlook long-path verification\x00\xff\n' * 32
    source.write_bytes(payload)
    short = args.scratch / ('short-' + uuid.uuid4().hex + '.txt')
    short.write_bytes(payload)
    report = {'baseline': args.baseline, 'client_home': str(args.client_home),
              'source_utf16_units': len(str(source).encode('utf-16-le')) // 2,
              'source_sha256': hashlib.sha256(payload).hexdigest(), 'sent': False}
    state = args.runtime_home / 'state'
    with client.queueing.acquire_queue_turn('long-attachment-probe', path=state / 'outlook_queue.sqlite'):
        with client.outlook_com_lock(path=state / 'outlook_com.lock'):
            _, session = client.connect_outlook()
            folder = session.GetDefaultFolder(client.OL_FOLDER_DRAFTS)
            item = client.create_mail_item_in_folder(folder)
            subject = 'Disposable long-path attachment probe ' + uuid.uuid4().hex
            item.Subject = subject
            item.Body = 'Local helper verification. Do not send.'
            saved = False
            try:
                if args.baseline:
                    item.Attachments.Add(str(short))
                    report['short_path_accepted'] = True
                    before = item.Attachments.Count
                    try:
                        item.Attachments.Add(str(source))
                        report['long_path_accepted'] = True
                    except Exception as exc:
                        report['long_path_accepted'] = False
                        report['error_type'] = type(exc).__name__
                        report['hresult'] = getattr(exc, 'hresult', None)
                        report['error'] = str(exc)
                    report['count_after_long_add'] = item.Attachments.Count
                    report['count_before_long_add'] = before
                else:
                    source_argument = ('\\\\?\\' + str(source)) if args.extended else str(source)
                    details = client.prepare_draft_attachments([source_argument])
                    with client.attach_draft_files(item, details):
                        item.Save()
                        saved = True
                    reopened = session.GetItemFromID(item.EntryID, folder.StoreID)
                    attachment = reopened.Attachments.Item(1)
                    exported = args.scratch / ('export-' + uuid.uuid4().hex + '.bin')
                    attachment.SaveAsFile(str(exported))
                    report.update({'filename_matches': attachment.FileName == source.name,
                                   'content_matches': exported.read_bytes() == payload,
                                   'attachment_count': reopened.Attachments.Count,
                                   'draft_attachments': details,
                                   'source_unchanged': source.read_bytes() == payload})
                    assert report['filename_matches'] and report['content_matches']
                    assert report['attachment_count'] == 1 and report['source_unchanged']
            finally:
                if saved:
                    item.Delete()  # Only our exact saved probe; never permanent deletion.
                    report['probe_removed_from_drafts'] = folder.Items.Restrict(f"[Subject] = '{subject}'").Count == 0
                    assert report['probe_removed_from_drafts']
                else:
                    item.Close(1)  # olDiscard
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
