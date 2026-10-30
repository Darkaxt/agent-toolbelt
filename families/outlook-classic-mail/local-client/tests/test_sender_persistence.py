"""Model the native Save/compose-commit distinction and protected send selection."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from outlook_classic_mail_client import client
from tests.test_client import FakeReply,make_session


class SenderPersistence(unittest.TestCase):
    def setUp(self):
        self.session=make_session()
        self.account=client.resolve_account(self.session,'demo@example.com')

    def test_save_commits_owned_hidden_compose_editor(self):
        item=FakeReply(Subject='Owned',To='')
        item.Application=SimpleNamespace(Inspectors=SimpleNamespace(Count=0))
        item._oleobj_=SimpleNamespace(GetIDsOfNames=Mock(return_value=64209),
            Invoke=Mock(side_effect=lambda *args:object.__setattr__(item,'SendUsingAccount',args[-1])))
        persisted=SimpleNamespace(SendUsingAccount=None)
        def commit(mode):
            self.assertEqual(mode,0);self.assertTrue(item.saved)
            persisted.SendUsingAccount=item.SendUsingAccount
        inspector=SimpleNamespace(Close=Mock(side_effect=commit))
        item.GetInspector=inspector
        details={}
        client.save_draft_with_sender(item,self.account,[],diagnostics=details)
        self.assertEqual(persisted.SendUsingAccount.SmtpAddress,'demo@example.com')
        self.assertTrue(details['editor_commit']['closed_saved'])

    def test_cached_account_without_native_stamp_cannot_verify_saved_sender(self):
        item=FakeReply(Subject='Cached',To='',SendUsingAccount=self.account['account'])
        item._oleobj_=object();item.PropertyAccessor=SimpleNamespace(GetProperty=lambda tag:'')
        self.session.GetItemFromID=Mock(return_value=item)
        result=client.verify_saved_draft_sender(self.session,item,self.account)
        self.assertFalse(result['verified'])
        self.assertEqual(result['status'],'not_persisted')

    def test_existing_editor_is_preserved(self):
        item=FakeReply(Subject='Existing',To='',SendUsingAccount=self.account['account'])
        inspector=SimpleNamespace(CurrentItem=item,Close=Mock())
        item.Application=SimpleNamespace(Inspectors=SimpleNamespace(Count=1,Item=lambda index:inspector))
        item.GetInspector=inspector
        item._oleobj_=SimpleNamespace(GetIDsOfNames=Mock(return_value=64209),Invoke=Mock())
        details={};client.save_draft_with_sender(item,self.account,[],diagnostics=details)
        inspector.Close.assert_not_called()
        self.assertTrue(details['editor_commit']['existing_preserved'])

    def draft(self,sender):
        folder=self.account['store'].GetDefaultFolder(client.OL_FOLDER_DRAFTS)
        item=FakeReply(Subject='Send fixture',To='recipient@example.com',Parent=folder,SendUsingAccount=sender)
        item.Send=Mock();self.session.GetItemFromID=Mock(return_value=item)
        return item

    def test_native_stamp_mismatch_cannot_borrow_cached_sender(self):
        item=FakeReply(Subject='Cached',To='',SendUsingAccount=self.account['account'])
        item._oleobj_=object()
        item.PropertyAccessor=SimpleNamespace(GetProperty=lambda tag:'Other Account' if tag.endswith('8580001F') else 'private-stamp')
        result=client.inspect_persisted_sender(item,expected='demo@example.com')
        self.assertFalse(result['verified']);self.assertEqual(result['status'],'not_persisted')
        self.assertNotIn('private-stamp',str(result))

    def test_failed_save_discards_only_new_hidden_editor(self):
        item=FakeReply(Subject='Owned',To='')
        item.Application=SimpleNamespace(Inspectors=SimpleNamespace(Count=0))
        item._oleobj_=SimpleNamespace(GetIDsOfNames=Mock(return_value=64209),Invoke=Mock())
        item.GetInspector=SimpleNamespace(Close=Mock());item.Save=Mock(side_effect=OSError('store unavailable'))
        with self.assertRaisesRegex(OSError,'store unavailable'):
            client.save_draft_with_sender(item,self.account,[],diagnostics={})
        item.GetInspector.Close.assert_called_once_with(1)

    def send(self,item):
        return client.apply_action(self.session,account_selector='demo@example.com',
            message_id=item.EntryID,action='send',confirm=True)

    def test_unset_sender_never_silently_uses_store_account(self):
        item=self.draft(None)
        with self.assertRaisesRegex(ValueError,'sender'):self.send(item)
        item.Send.assert_not_called()

    def test_send_assignment_failure_prevents_dispatch(self):
        item=self.draft(self.account['account']);item.reject_send_using=True
        with self.assertRaisesRegex(ValueError,'sender'):self.send(item)
        item.Send.assert_not_called()

    def test_dispatch_uses_existing_sender_not_store(self):
        other=SimpleNamespace(SmtpAddress='other@example.com',DisplayName='Other',DeliveryStore=self.account['store'])
        self.session.Accounts.append(other)
        item=self.draft(other);result=self.send(item)
        self.assertIs(item.SendUsingAccount,other)
        item.Send.assert_called_once_with()
        self.assertTrue(result['submitted']);self.assertFalse(result['delivery_verified'])


if __name__=='__main__':unittest.main()
