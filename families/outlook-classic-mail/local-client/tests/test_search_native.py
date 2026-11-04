import json
import io
import os
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from test_client import make_session,FakeMessage
from outlook_classic_mail_client import client


class NativeSearch(unittest.TestCase):
    def search(self,session,**kwargs):
        return client.search_messages(session,account_selector='demo@example.com',folder_selector='inbox',
            query=kwargs.pop('query','needle'),unread=False,sender=None,recipient=None,
            days=kwargs.pop('days',None),limit=kwargs.pop('limit',5),**kwargs)

    def test_finds_complete_body_beyond_old_scan_window(self):
        session=make_session();folder=client.resolve_folder(client.resolve_account(session,'demo@example.com'),'inbox')
        original=folder.Items[0]
        folder.Items.clear()
        for index in range(250):
            item=FakeMessage(EntryID=str(index),Subject='Unrelated',Body='x'*900+(' needle' if index==249 else ''),
                             SenderName='Example',SenderEmailAddress='sender@example.com',To='demo@example.com',
                             UnRead=False,ConversationID='fixture',ConversationTopic='fixture',
                             ReceivedTime=datetime.now()-timedelta(minutes=index))
            item.Parent=folder;folder.Items.append(item);session._messages[item.EntryID]=item
        result=self.search(session)
        self.assertEqual([item['entry_id'] for item in result['messages']],['249'])
        self.assertIn('urn:schemas:httpmail:textdescription',folder.last_filter)
        self.assertEqual(result['search']['rows_examined'],250)

    def test_uses_native_candidate_rows_not_folder_items(self):
        session=make_session();folder=client.resolve_folder(client.resolve_account(session,'demo@example.com'),'inbox')
        table=folder.GetTable('');table.items=table.items[:1]
        with patch.object(folder,'GetTable',return_value=table) as native,patch.object(client,'iter_recent_messages',side_effect=AssertionError('Legacy enumeration')):
            result=self.search(session,query=None,since='2020-06-16',limit=1)
        self.assertIn('datereceived',native.call_args.args[0]);self.assertEqual(result['search']['items_opened'],1)

    def test_filter_literals_and_dates(self):
        filter=client.native_search_filter("O'Brien 100%_[x]",True,None,None,datetime(2026,6,16,tzinfo=timezone.utc))
        self.assertIn("O''Brien",filter);self.assertIn('2026-06-16 00:00:00',filter)
        self.assertIn('read" = false',filter)
        with self.assertRaises(ValueError):client.search_cutoff(7,'2026-06-16')

    def test_since_forwarded_and_scope_reports_remaining_candidates(self):
        session=make_session();result=self.search(session,query=None,limit=1)
        self.assertTrue(result['search']['remaining_candidates'])
        args=client.build_parser().parse_args(['search','--account','demo@example.com','--since','2026-06-16'])
        self.assertEqual(args.since,'2026-06-16')

    def test_progress_has_counts_without_mail_content(self):
        with patch.dict(os.environ,{'OUTLOOK_CLASSIC_MAIL_PROGRESS':'1'}),patch('sys.stderr',io.StringIO()) as output:
            self.search(make_session(),query=None,limit=1)
        events=[json.loads(line.removeprefix('OUTLOOK_PROGRESS ')) for line in output.getvalue().splitlines()]
        self.assertEqual(events[-1]['stage'],'folder_complete')
        self.assertNotIn('subject',str(events).lower())

    def test_indexed_is_explicit_and_never_silently_falls_back(self):
        session=make_session()
        with self.assertRaisesRegex(ValueError,'Indexed search unavailable'):
            self.search(session,indexed=True)
        filter=client.native_search_filter("O'Brien",False,None,None,None,True)
        self.assertIn("ci_phrasematch 'O''Brien'",filter)
        self.assertNotIn(' LIKE ',filter)

    def test_broad_scan_uses_inventory_even_when_folder_names_match(self):
        import tempfile
        from pathlib import Path
        from outlook_classic_mail_client import mail_cache
        session=make_session()
        with tempfile.TemporaryDirectory() as temp:
            path=str(Path(temp)/'cache.sqlite')
            client.find_folders(session,query='lettre24',account_selector='demo@example.com',all_accounts=False,
                                limit=10,rediscover_folders=True,cache_path=path)
            result=client.search_all_folders(session,account_selector='demo@example.com',all_accounts=False,
                query='lettre24',unread=False,sender=None,recipient=None,days=None,folder_limit=30,
                per_folder_limit=5,update_hints=False,broad_scan=True,cache_path=path)
        self.assertEqual(result['scope']['strategy'],'bounded-folder-inventory')
        self.assertGreater(len(result['searched_folders']),1)

if __name__=='__main__':unittest.main()
