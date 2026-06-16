import contextlib
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TOOL_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from outlook_classic_mail_client import client


OL_FOLDER_DELETED_ITEMS = 3
OL_FOLDER_SENT_MAIL = 5
OL_FOLDER_INBOX = 6
OL_FOLDER_DRAFTS = 16


class FakeItems(list):
    def __init__(self):
        super().__init__()
        self.parent = None
        self.reject_send_using = False

    def Add(self, item_type):
        draft = FakeReply(Subject="", To="")
        draft.Parent = self.parent
        draft.item_type = item_type
        draft.reject_send_using = self.reject_send_using
        self.append(draft)
        return draft


@dataclass
class FakeAttachment:
    FileName: str
    DisplayName: str = ""
    Size: int = 0
    Type: int = 1
    Position: int = 0


class FakeAttachments(list):
    def __init__(self, *args):
        super().__init__(*args)
        self.added_paths: list[str] = []

    @property
    def Count(self) -> int:
        return len(self)

    def Item(self, index):
        return self[index - 1]

    def Add(self, path):
        self.added_paths.append(str(path))
        attachment = FakeAttachment(FileName=Path(path).name, DisplayName=Path(path).name)
        self.append(attachment)
        return attachment


@dataclass
class FakeReply:
    Subject: str
    To: str
    CC: str = ""
    Body: str = "Quoted original"
    HTMLBody: str = "<html><body><table><tr><td>Quoted original</td></tr></table></body></html>"
    SendUsingAccount: object | None = None
    Parent: object | None = None
    reject_send_using: bool = False
    saved: bool = False
    Attachments: FakeAttachments = field(default_factory=FakeAttachments)

    def __setattr__(self, name, value):
        if name == "SendUsingAccount" and getattr(self, "reject_send_using", False):
            raise RuntimeError("SendUsingAccount rejected")
        super().__setattr__(name, value)

    @property
    def EntryID(self) -> str:
        return "draft-reply-id"

    def Save(self) -> None:
        self.saved = True


@dataclass
class FakeForward(FakeReply):
    @property
    def EntryID(self) -> str:
        return "draft-forward-id"


@dataclass
class FakeMessage:
    EntryID: str
    Subject: str
    SenderName: str
    SenderEmailAddress: str
    To: str
    ReceivedTime: datetime
    UnRead: bool
    Body: str
    ConversationID: str
    ConversationTopic: str
    CC: str = ""
    BCC: str = ""
    Parent: object | None = None
    deleted: bool = False
    sent: bool = False
    Categories: str = ""
    HTMLBody: str = ""
    Attachments: FakeAttachments = field(default_factory=FakeAttachments)
    last_reply: FakeReply | None = field(default=None, init=False)
    last_forward: FakeForward | None = field(default=None, init=False)

    def Reply(self) -> FakeReply:
        self.last_reply = FakeReply(Subject=f"RE: {self.Subject}", To=self.SenderEmailAddress)
        return self.last_reply

    def Forward(self) -> FakeForward:
        self.last_forward = FakeForward(Subject=f"FW: {self.Subject}", To="")
        return self.last_forward

    def Delete(self) -> None:
        self.deleted = True

    def Send(self) -> None:
        self.sent = True

    def Move(self, folder):
        source = self.Parent
        if source is not None and self in source.Items:
            source.Items.remove(self)
        self.Parent = folder
        folder.Items.append(self)
        return self

    def Save(self) -> None:
        return None


@dataclass
class FakeFolder:
    Name: str
    FolderPath: str
    Items: FakeItems = field(default_factory=FakeItems)
    Folders: list = field(default_factory=list)

    def __post_init__(self):
        self.Items.parent = self

    def add_child(self, folder: "FakeFolder") -> "FakeFolder":
        self.Folders.append(folder)
        return folder


@dataclass
class FakeStore:
    DisplayName: str
    StoreID: str
    root: FakeFolder
    defaults: dict

    def GetDefaultFolder(self, folder_id: int):
        return self.defaults[folder_id]

    def GetRootFolder(self):
        return self.root


@dataclass
class FakeAccount:
    DisplayName: str
    SmtpAddress: str
    DeliveryStore: FakeStore


@dataclass
class FakeSession:
    Accounts: list

    def __post_init__(self):
        self._messages = {}
        self._stores = []
        for account in self.Accounts:
            self._stores.append(account.DeliveryStore)
            for folder in client.iter_folder_tree(account.DeliveryStore.GetRootFolder()):
                for item in folder.Items:
                    item.Parent = folder
                    self._messages[item.EntryID] = item

    @property
    def Stores(self):
        return self._stores

    def GetItemFromID(self, entry_id, store_id=None):
        return self._messages[entry_id]


@dataclass
class FakeSyncObject:
    Name: str
    started: bool = False

    def Start(self) -> None:
        self.started = True


class FailingCreateItemApplication:
    def CreateItem(self, item_type):
        raise AssertionError("generic draft creation must use the target store Drafts folder")


def make_session() -> FakeSession:
    root = FakeFolder("Mailbox", r"\\Mailbox")
    inbox = root.add_child(FakeFolder("Inbox", r"\\Mailbox\\Inbox"))
    sent = root.add_child(FakeFolder("Sent Items", r"\\Mailbox\\Sent Items"))
    drafts = root.add_child(FakeFolder("Drafts", r"\\Mailbox\\Drafts"))
    trash = root.add_child(FakeFolder("Deleted Items", r"\\Mailbox\\Deleted Items"))
    projects = inbox.add_child(FakeFolder("Projects", r"\\Mailbox\\Inbox\\Projects"))
    delivery = inbox.add_child(FakeFolder("Delivery", r"\\Mailbox\\Inbox\\Delivery"))
    lettre24 = delivery.add_child(FakeFolder("Lettre24", r"\\Mailbox\\Inbox\\Delivery\\Lettre24"))

    now = datetime.now().replace(microsecond=0)
    inbox.Items.extend(
        [
            FakeMessage(
                EntryID="msg-1",
                Subject="Urgent: approval needed today",
                SenderName="Alice",
                SenderEmailAddress="alice@example.com",
                To="user@example.com",
                ReceivedTime=now,
                UnRead=True,
                Body="Need approval today for the contract.",
                ConversationID="conv-1",
                ConversationTopic="approval needed today",
            ),
            FakeMessage(
                EntryID="msg-2",
                Subject="FYI weekly digest",
                SenderName="Digest",
                SenderEmailAddress="digest@example.com",
                To="user@example.com",
                ReceivedTime=now - timedelta(hours=2),
                UnRead=False,
                Body="Highlights from this week.",
                ConversationID="conv-2",
                ConversationTopic="weekly digest",
            ),
        ]
    )
    sent.Items.append(
        FakeMessage(
            EntryID="msg-3",
            Subject="RE: approval needed today",
            SenderName="User",
            SenderEmailAddress="user@example.com",
            To="alice@example.com",
            ReceivedTime=now - timedelta(hours=1),
            UnRead=False,
            Body="I will review it shortly.",
            ConversationID="conv-1",
            ConversationTopic="approval needed today",
        )
    )
    projects.Items.append(
        FakeMessage(
            EntryID="msg-4",
            Subject="Project update question",
            SenderName="Bob",
            SenderEmailAddress="bob@example.com",
            To="user@example.com",
            ReceivedTime=now - timedelta(days=1),
            UnRead=True,
            Body="Can you confirm the project status?",
            ConversationID="conv-3",
            ConversationTopic="project update question",
        )
    )
    lettre24.Items.append(
        FakeMessage(
            EntryID="msg-5",
            Subject="En cours de traitement chez La Poste",
            SenderName="noreply@lettre24.lu",
            SenderEmailAddress="noreply@lettre24.lu",
            To="user@example.com",
            ReceivedTime=now - timedelta(minutes=30),
            UnRead=False,
            Body="La Poste confirme la prise en charge de votre courrier Lettre24.",
            ConversationID="conv-4",
            ConversationTopic="En cours de traitement chez La Poste",
        )
    )

    store = FakeStore(
        DisplayName="demo@example.com",
        StoreID="store-1",
        root=root,
        defaults={
            OL_FOLDER_INBOX: inbox,
            OL_FOLDER_SENT_MAIL: sent,
            OL_FOLDER_DRAFTS: drafts,
            OL_FOLDER_DELETED_ITEMS: trash,
        },
    )
    account = FakeAccount("Demo Account", "demo@example.com", store)
    return FakeSession([account])


def make_response_session() -> FakeSession:
    now = datetime.now().replace(microsecond=0)

    anchor_root = FakeFolder("Anchor Mailbox", r"\\Anchor Mailbox")
    anchor_inbox = anchor_root.add_child(FakeFolder("Inbox", r"\\Anchor Mailbox\\Inbox"))
    anchor_sent = anchor_root.add_child(FakeFolder("Sent Items", r"\\Anchor Mailbox\\Sent Items"))
    anchor_drafts = anchor_root.add_child(FakeFolder("Drafts", r"\\Anchor Mailbox\\Drafts"))
    anchor_trash = anchor_root.add_child(FakeFolder("Deleted Items", r"\\Anchor Mailbox\\Deleted Items"))
    anchor_inbox.Items.append(
        FakeMessage(
            EntryID="anchor-1",
            Subject="Relocation to Cyprus",
            SenderName="Client Services",
            SenderEmailAddress="clientservices@example.com",
            To="reply@example.com",
            ReceivedTime=now,
            UnRead=False,
            Body="Please confirm the Luxembourg schedule.",
            ConversationID="conv-42",
            ConversationTopic="Relocation to Cyprus",
        )
    )
    anchor_sent.Items.append(
        FakeMessage(
            EntryID="wrong-account-reply",
            Subject="RE: Relocation to Cyprus",
            SenderName="Anchor",
            SenderEmailAddress="anchor@example.com",
            To="clientservices@example.com",
            ReceivedTime=now + timedelta(minutes=30),
            UnRead=False,
            Body="This should only appear when fallback is enabled.",
            ConversationID="conv-42",
            ConversationTopic="Relocation to Cyprus",
        )
    )

    reply_root = FakeFolder("Reply Mailbox", r"\\Reply Mailbox")
    reply_inbox = reply_root.add_child(FakeFolder("Inbox", r"\\Reply Mailbox\\Inbox"))
    reply_sent = reply_root.add_child(FakeFolder("Sent Items", r"\\Reply Mailbox\\Sent Items"))
    reply_drafts = reply_root.add_child(FakeFolder("Drafts", r"\\Reply Mailbox\\Drafts"))
    reply_trash = reply_root.add_child(FakeFolder("Deleted Items", r"\\Reply Mailbox\\Deleted Items"))
    reply_sent.Items.append(
        FakeMessage(
            EntryID="reply-sent",
            Subject="RE: Relocation to Cyprus",
            SenderName="Reply User",
            SenderEmailAddress="reply@example.com",
            To="clientservices@example.com",
            ReceivedTime=now + timedelta(hours=1),
            UnRead=False,
            Body="I meant one week every three months.",
            ConversationID="conv-42",
            ConversationTopic="Relocation to Cyprus",
        )
    )
    reply_drafts.Items.append(
        FakeMessage(
            EntryID="reply-draft",
            Subject="RE: Relocation to Cyprus",
            SenderName="Reply User",
            SenderEmailAddress="reply@example.com",
            To="clientservices@example.com",
            ReceivedTime=now + timedelta(hours=2),
            UnRead=False,
            Body="Draft follow-up.",
            ConversationID="conv-42",
            ConversationTopic="Relocation to Cyprus",
        )
    )
    reply_sent.Items.append(
        FakeMessage(
            EntryID="older-reply",
            Subject="RE: Relocation to Cyprus",
            SenderName="Reply User",
            SenderEmailAddress="reply@example.com",
            To="clientservices@example.com",
            ReceivedTime=now - timedelta(hours=1),
            UnRead=False,
            Body="Older message should not be returned.",
            ConversationID="conv-42",
            ConversationTopic="Relocation to Cyprus",
        )
    )

    other_root = FakeFolder("Other Mailbox", r"\\Other Mailbox")
    other_inbox = other_root.add_child(FakeFolder("Inbox", r"\\Other Mailbox\\Inbox"))
    other_sent = other_root.add_child(FakeFolder("Sent Items", r"\\Other Mailbox\\Sent Items"))
    other_drafts = other_root.add_child(FakeFolder("Drafts", r"\\Other Mailbox\\Drafts"))
    other_trash = other_root.add_child(FakeFolder("Deleted Items", r"\\Other Mailbox\\Deleted Items"))
    other_sent.Items.append(
        FakeMessage(
            EntryID="fallback-reply",
            Subject="RE: Relocation to Cyprus",
            SenderName="Other User",
            SenderEmailAddress="other@example.com",
            To="clientservices@example.com",
            ReceivedTime=now + timedelta(hours=3),
            UnRead=False,
            Body="Fallback account response.",
            ConversationID="conv-42",
            ConversationTopic="Relocation to Cyprus",
        )
    )

    anchor_store = FakeStore(
        DisplayName="anchor@example.com",
        StoreID="store-anchor",
        root=anchor_root,
        defaults={
            OL_FOLDER_INBOX: anchor_inbox,
            OL_FOLDER_SENT_MAIL: anchor_sent,
            OL_FOLDER_DRAFTS: anchor_drafts,
            OL_FOLDER_DELETED_ITEMS: anchor_trash,
        },
    )
    reply_store = FakeStore(
        DisplayName="reply@example.com",
        StoreID="store-reply",
        root=reply_root,
        defaults={
            OL_FOLDER_INBOX: reply_inbox,
            OL_FOLDER_SENT_MAIL: reply_sent,
            OL_FOLDER_DRAFTS: reply_drafts,
            OL_FOLDER_DELETED_ITEMS: reply_trash,
        },
    )
    other_store = FakeStore(
        DisplayName="other@example.com",
        StoreID="store-other",
        root=other_root,
        defaults={
            OL_FOLDER_INBOX: other_inbox,
            OL_FOLDER_SENT_MAIL: other_sent,
            OL_FOLDER_DRAFTS: other_drafts,
            OL_FOLDER_DELETED_ITEMS: other_trash,
        },
    )
    return FakeSession(
        [
            FakeAccount("Anchor", "anchor@example.com", anchor_store),
            FakeAccount("Reply", "reply@example.com", reply_store),
            FakeAccount("Other", "other@example.com", other_store),
        ]
    )


class OutlookClassicMailClientTests(unittest.TestCase):
    def setUp(self):
        self.session = make_session()

    def test_collect_accounts_serializes_configured_accounts(self):
        accounts = client.collect_accounts(self.session)

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["smtp_address"], "demo@example.com")
        self.assertEqual(accounts[0]["delivery_store"], "demo@example.com")

    def test_resolve_folder_uses_default_and_custom_paths(self):
        account = client.resolve_account(self.session, "demo@example.com")

        inbox = client.resolve_folder(account, "inbox")
        custom = client.resolve_folder(account, "custom:Inbox/Projects")

        self.assertEqual(inbox.FolderPath, r"\\Mailbox\\Inbox")
        self.assertEqual(custom.FolderPath, r"\\Mailbox\\Inbox\\Projects")

    def test_search_messages_filters_by_query_and_unread(self):
        result = client.search_messages(
            self.session,
            account_selector="demo@example.com",
            folder_selector="inbox",
            query="approval",
            unread=True,
            sender=None,
            recipient=None,
            days=7,
            limit=10,
        )

        self.assertEqual(len(result["messages"]), 1)
        self.assertEqual(result["messages"][0]["entry_id"], "msg-1")

    def test_find_folders_finds_nested_folders_by_name(self):
        result = client.find_folders(
            self.session,
            query="lettre24",
            account_selector="demo@example.com",
            all_accounts=False,
            limit=10,
        )

        self.assertEqual(result["matches"][0]["name"], "Lettre24")
        self.assertEqual(result["matches"][0]["folder_selector"], "custom:Inbox/Delivery/Lettre24")

    def test_search_all_folders_searches_matched_folder_first(self):
        result = client.search_all_folders(
            self.session,
            account_selector="demo@example.com",
            all_accounts=False,
            query="lettre24",
            unread=False,
            sender=None,
            recipient=None,
            days=7,
            folder_limit=10,
            per_folder_limit=5,
            update_hints=False,
        )

        self.assertEqual([message["entry_id"] for message in result["messages"]], ["msg-5"])
        self.assertEqual(result["matched_folders"][0]["name"], "Lettre24")
        self.assertEqual(result["searched_folders"][0]["folder_selector"], "custom:Inbox/Delivery/Lettre24")
        self.assertEqual(result["scope"]["strategy"], "matched-folders")

    def test_search_all_folders_has_bounded_fallback_metadata(self):
        result = client.search_all_folders(
            self.session,
            account_selector="demo@example.com",
            all_accounts=False,
            query="unknown-service",
            unread=False,
            sender=None,
            recipient=None,
            days=7,
            folder_limit=2,
            per_folder_limit=1,
            update_hints=False,
        )

        self.assertEqual(result["messages"], [])
        self.assertEqual(result["matched_folders"], [])
        self.assertLessEqual(len(result["searched_folders"]), 2)
        self.assertEqual(result["scope"]["strategy"], "bounded-all-folders")
        self.assertTrue(result["scope"]["limited"])

    def test_folder_hints_accelerate_without_hiding_folder_discovery(self):
        hints = {"lettre24": ["custom:Inbox/Delivery/Lettre24"]}
        result = client.search_all_folders(
            self.session,
            account_selector="demo@example.com",
            all_accounts=False,
            query="lettre24",
            unread=False,
            sender=None,
            recipient=None,
            days=7,
            folder_limit=10,
            per_folder_limit=5,
            folder_hints=hints,
            update_hints=False,
        )

        self.assertEqual(result["searched_folders"][0]["source"], "hint")
        self.assertEqual(result["matched_folders"][0]["source"], "discovery")

    def test_cache_refresh_populates_metadata_without_bodies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = str(Path(temp_dir) / "mail_cache.sqlite")

            refresh = client.cache_refresh(
                self.session,
                account_selector="demo@example.com",
                all_accounts=False,
                days=90,
                force=True,
                cache_path=cache_path,
            )
            shown = client.cache_show(
                cache_path=cache_path,
                query="lettre24",
                account_selector=None,
                days=None,
                limit=10,
            )

        self.assertGreaterEqual(refresh["messages_cached"], 5)
        self.assertEqual(shown["messages"][0]["entry_id"], "msg-5")
        self.assertIn("candidate_folders", shown)
        self.assertNotIn("body", shown["messages"][0])
        self.assertNotIn("body_excerpt", shown["messages"][0])

    def test_search_all_folders_uses_cache_candidates_before_discovery(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = str(Path(temp_dir) / "mail_cache.sqlite")
            client.cache_refresh(
                self.session,
                account_selector="demo@example.com",
                all_accounts=False,
                days=90,
                force=True,
                cache_path=cache_path,
            )

            result = client.search_all_folders(
                self.session,
                account_selector="demo@example.com",
                all_accounts=False,
                query="lettre24",
                unread=False,
                sender=None,
                recipient=None,
                days=7,
                folder_limit=10,
                per_folder_limit=5,
                update_hints=False,
                use_cache=True,
                update_cache=True,
                cache_path=cache_path,
            )

        self.assertEqual(result["backend"], "mail-cache+live-com")
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["searched_folders"][0]["source"], "mail-cache")
        self.assertEqual([message["entry_id"] for message in result["messages"]], ["msg-5"])

    def test_search_all_folders_can_bypass_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = str(Path(temp_dir) / "mail_cache.sqlite")
            client.cache_refresh(
                self.session,
                account_selector="demo@example.com",
                all_accounts=False,
                days=90,
                force=True,
                cache_path=cache_path,
            )

            result = client.search_all_folders(
                self.session,
                account_selector="demo@example.com",
                all_accounts=False,
                query="lettre24",
                unread=False,
                sender=None,
                recipient=None,
                days=7,
                folder_limit=10,
                per_folder_limit=5,
                update_hints=False,
                use_cache=False,
                update_cache=False,
                cache_path=cache_path,
            )

        self.assertEqual(result["backend"], "live-com")
        self.assertFalse(result["cache_hit"])

    def test_cache_clear_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = str(Path(temp_dir) / "mail_cache.sqlite")

            with self.assertRaisesRegex(ValueError, "requires --confirm"):
                client.cache_clear(cache_path=cache_path, query=None, confirm=False)

    def test_cache_refresh_replaces_invalid_surrogate_text(self):
        account = client.resolve_account(self.session, "demo@example.com")
        inbox = client.resolve_folder(account, "inbox")
        inbox.Items.append(
            FakeMessage(
                EntryID="msg-surrogate",
                Subject="\udf0d broken subject",
                SenderName="Surrogate Sender",
                SenderEmailAddress="surrogate@example.com",
                To="user@example.com",
                ReceivedTime=datetime.now().replace(microsecond=0),
                UnRead=False,
                Body="Body",
                ConversationID="conv-surrogate",
                ConversationTopic="\udf0d broken subject",
            )
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = str(Path(temp_dir) / "mail_cache.sqlite")
            refresh = client.cache_refresh(
                self.session,
                account_selector="demo@example.com",
                all_accounts=False,
                days=90,
                force=True,
                cache_path=cache_path,
            )
            shown = client.cache_show(cache_path=cache_path, query="broken", limit=10)

        self.assertEqual(refresh["warnings"], [])
        self.assertIn("msg-surrogate", [message["entry_id"] for message in shown["messages"]])

    def test_sync_mail_starts_sync_objects(self):
        sync_object = FakeSyncObject("All Accounts")
        self.session.SyncObjects = [sync_object]

        result = client.sync_mail(
            application=None,
            session=self.session,
            refresh_cache=False,
            account_selector=None,
            all_accounts=True,
            days=90,
            force=False,
        )

        self.assertTrue(sync_object.started)
        self.assertEqual(result["attempted"][0]["method"], "SyncObjects.Start")
        self.assertEqual(result["status"], "started")

    def test_search_messages_handles_timezone_aware_outlook_datetimes(self):
        account = client.resolve_account(self.session, "demo@example.com")
        inbox = client.resolve_folder(account, "inbox")
        inbox.Items[0].ReceivedTime = datetime.now(timezone.utc)

        result = client.search_messages(
            self.session,
            account_selector="demo@example.com",
            folder_selector="inbox",
            query="approval",
            unread=True,
            sender=None,
            recipient=None,
            days=7,
            limit=10,
        )

        self.assertEqual(result["messages"][0]["entry_id"], "msg-1")

    def test_search_messages_cache_write_failures_become_warnings(self):
        class BrokenCache:
            def upsert_message(self, record):
                raise PermissionError("cache locked")

        result = client.search_messages(
            self.session,
            account_selector="demo@example.com",
            folder_selector="inbox",
            query="approval",
            unread=True,
            sender=None,
            recipient=None,
            days=7,
            limit=10,
            cache=BrokenCache(),
            update_cache=True,
        )

        self.assertEqual(result["messages"][0]["entry_id"], "msg-1")
        self.assertTrue(result["warnings"])
        self.assertIn("cache", result["warnings"][0].lower())

    def test_read_thread_collects_same_conversation_across_default_mail_folders(self):
        result = client.read_thread(
            self.session,
            account_selector="demo@example.com",
            message_id="msg-1",
        )

        self.assertEqual(result["anchor"]["entry_id"], "msg-1")
        self.assertEqual([message["entry_id"] for message in result["messages"]], ["msg-3", "msg-1"])

    def test_read_message_returns_full_body_and_attachment_list(self):
        account = client.resolve_account(self.session, "demo@example.com")
        message = client.resolve_message(self.session, account, "msg-1")
        message.Body = "Line one\r\nLine two\r\nFinal exact sentence."
        message.HTMLBody = "<html><body><p>Line one</p><p>Line two</p></body></html>"
        message.Attachments = FakeAttachments(
            [
                FakeAttachment(FileName="transfer.pdf", DisplayName="Transfer PDF", Size=12345),
                FakeAttachment(FileName="terms.txt", Size=99),
            ]
        )

        result = client.read_message(
            self.session,
            account_selector="demo@example.com",
            message_id="msg-1",
            include_html=True,
        )

        self.assertEqual(result["message"]["entry_id"], "msg-1")
        self.assertEqual(result["message"]["body"], "Line one\r\nLine two\r\nFinal exact sentence.")
        self.assertEqual(result["message"]["html_body"], message.HTMLBody)
        self.assertEqual(result["message"]["body_length"], len(message.Body))
        self.assertEqual(result["message"]["attachment_count"], 2)
        self.assertEqual(
            [attachment["file_name"] for attachment in result["message"]["attachments"]],
            ["transfer.pdf", "terms.txt"],
        )
        self.assertEqual(result["message"]["attachments"][0]["display_name"], "Transfer PDF")
        self.assertEqual(result["message"]["attachments"][0]["size"], 12345)
        self.assertTrue(result["message"]["has_attachments"])

    def test_find_response_uses_original_recipient_account_before_other_stores(self):
        response_session = make_response_session()

        result = client.find_response(
            response_session,
            account_selector="anchor@example.com",
            message_id="anchor-1",
            limit=10,
            fallback_all_accounts=False,
            include_drafts=True,
        )

        self.assertEqual(result["anchor"]["entry_id"], "anchor-1")
        self.assertEqual(result["recipient_accounts"], ["reply@example.com"])
        self.assertEqual([folder["folder_selector"] for folder in result["searched_folders"]], ["sent", "drafts"])
        self.assertEqual([message["entry_id"] for message in result["messages"]], ["reply-draft", "reply-sent"])
        self.assertNotIn("fallback-reply", [message["entry_id"] for message in result["messages"]])
        self.assertEqual(result["messages"][0]["match_reason"], "conversation_id")
        self.assertEqual(result["messages"][0]["scope"], "recipient-account")
        self.assertEqual(result["scope"]["strategy"], "recipient-account-first")

    def test_find_response_excludes_drafts_when_requested(self):
        response_session = make_response_session()

        result = client.find_response(
            response_session,
            account_selector="anchor@example.com",
            message_id="anchor-1",
            limit=10,
            fallback_all_accounts=False,
            include_drafts=False,
        )

        self.assertEqual([folder["folder_selector"] for folder in result["searched_folders"]], ["sent"])
        self.assertEqual([message["entry_id"] for message in result["messages"]], ["reply-sent"])

    def test_find_response_searches_other_stores_only_with_fallback(self):
        response_session = make_response_session()

        result = client.find_response(
            response_session,
            account_selector="anchor@example.com",
            message_id="anchor-1",
            limit=10,
            fallback_all_accounts=True,
            include_drafts=False,
        )

        self.assertIn("fallback-reply", [message["entry_id"] for message in result["messages"]])
        self.assertIn("fallback-account", {message["scope"] for message in result["messages"]})

    def test_find_response_falls_back_to_topic_when_conversation_id_missing(self):
        response_session = make_response_session()
        response_session.GetItemFromID("anchor-1").ConversationID = ""
        response_session.GetItemFromID("reply-sent").ConversationID = ""

        result = client.find_response(
            response_session,
            account_selector="anchor@example.com",
            message_id="anchor-1",
            limit=10,
            fallback_all_accounts=False,
            include_drafts=False,
        )

        self.assertEqual(result["messages"][0]["entry_id"], "reply-sent")
        self.assertEqual(result["messages"][0]["match_reason"], "conversation_topic")

    def test_triage_buckets_messages(self):
        result = client.triage_messages(
            self.session,
            account_selector=None,
            all_accounts=True,
            days=7,
            limit=10,
        )

        self.assertIn("Urgent", result["buckets"])
        urgent_ids = [message["entry_id"] for message in result["buckets"]["Urgent"]]
        self.assertIn("msg-1", urgent_ids)

    def test_draft_reply_preview_does_not_mutate_until_confirmed(self):
        preview = client.draft_reply(
            self.session,
            account_selector="demo@example.com",
            message_id="msg-1",
            instruction="Confirm I will review it this afternoon.",
            body=None,
            create_draft=False,
            confirm=False,
        )

        self.assertFalse(preview["created"])
        self.assertEqual(preview["suggested_body"], "")
        self.assertEqual(preview["instruction"], "Confirm I will review it this afternoon.")
        self.assertEqual(preview["draft_status"], "needs_body")
        self.assertEqual(preview["draft_body_source"], "missing")
        self.assertIn("draft_body_missing", preview["warnings"])

    def test_draft_reply_requires_confirmation_to_create_draft(self):
        with self.assertRaisesRegex(ValueError, "requires --confirm"):
            client.draft_reply(
                self.session,
                account_selector="demo@example.com",
                message_id="msg-1",
                instruction="Reply with thanks.",
                body="Thanks, reviewing now.",
                create_draft=True,
                confirm=False,
            )

    def test_draft_reply_requires_body_to_create_draft(self):
        message = self.session.GetItemFromID("msg-1")

        with self.assertRaisesRegex(ValueError, "--body with the final draft text"):
            client.draft_reply(
                self.session,
                account_selector="demo@example.com",
                message_id="msg-1",
                instruction="Reply with this exact-sounding instruction.",
                body=None,
                create_draft=True,
                confirm=True,
            )

        self.assertIsNone(message.last_reply)

    def test_draft_forward_requires_body_to_create_draft(self):
        message = self.session.GetItemFromID("msg-1")

        with self.assertRaisesRegex(ValueError, "--body with the final draft text"):
            client.draft_forward(
                self.session,
                account_selector="demo@example.com",
                message_id="msg-1",
                to="forward@example.com",
                instruction="Forward with this exact-sounding instruction.",
                body=" ",
                create_draft=True,
                confirm=True,
            )

        self.assertIsNone(message.last_forward)

    def test_draft_reply_create_preserves_existing_html_body(self):
        message = self.session.GetItemFromID("msg-1")

        def reply_with_thread():
            message.last_reply = FakeReply(
                Subject=f"RE: {message.Subject}",
                To=message.SenderEmailAddress,
                Body=f"Quoted original\r\n{message.Body}",
                HTMLBody=(
                    "<html><body><table><tr><td>Quoted original</td></tr></table>"
                    f"<p>{message.Body}</p></body></html>"
                ),
            )
            return message.last_reply

        message.Reply = reply_with_thread

        result = client.draft_reply(
            self.session,
            account_selector="demo@example.com",
            message_id="msg-1",
            instruction="Reply with <thanks>.\nConfirm review.",
            body="Thanks <Alice>.\nConfirming review.",
            create_draft=True,
            confirm=True,
        )

        draft = message.last_reply
        self.assertTrue(result["created"])
        self.assertIsNotNone(draft)
        self.assertTrue(draft.saved)
        self.assertIn("<p>Thanks &lt;Alice&gt;.<br>Confirming review.</p>", draft.HTMLBody)
        self.assertIn("<table><tr><td>Quoted original</td></tr></table>", draft.HTMLBody)
        self.assertIn("Need approval today for the contract.", draft.Body)
        self.assertEqual(result["draft_placement"]["strategy"], "native_reply")
        self.assertEqual(result["draft_content"]["thread_content_source"], "native_reply")
        self.assertEqual(result["draft_status"], "created")
        self.assertEqual(result["draft_body_source"], "body")

    def test_draft_reply_reconstructs_thread_when_native_reply_is_empty(self):
        message = self.session.GetItemFromID("msg-1")
        message.HTMLBody = "<html><body><p>Original thread HTML</p></body></html>"

        def empty_reply():
            message.last_reply = FakeReply(
                Subject=f"RE: {message.Subject}",
                To=message.SenderEmailAddress,
                Body="",
                HTMLBody="",
            )
            return message.last_reply

        message.Reply = empty_reply

        result = client.draft_reply(
            self.session,
            account_selector="demo@example.com",
            message_id="msg-1",
            instruction="Reply with thanks.",
            body="Thanks.",
            create_draft=True,
            confirm=True,
        )

        draft = message.last_reply
        self.assertTrue(result["created"])
        self.assertIn("<p>Thanks.</p>", draft.HTMLBody)
        self.assertIn("Original thread HTML", draft.HTMLBody)
        self.assertEqual(result["draft_content"]["thread_content_included"], True)
        self.assertEqual(result["draft_content"]["thread_content_source"], "manual_quote_fallback")
        self.assertIn("thread_quote_fallback_used", result["draft_content"]["warnings"])

    def test_draft_reply_reconstructs_thread_when_native_reply_only_has_signature(self):
        message = self.session.GetItemFromID("msg-1")

        def signature_only_reply():
            message.last_reply = FakeReply(
                Subject=f"RE: {message.Subject}",
                To=message.SenderEmailAddress,
                Body="Best regards, Demo",
                HTMLBody="<html><body><p>Best regards, Demo</p></body></html>",
            )
            return message.last_reply

        message.Reply = signature_only_reply

        result = client.draft_reply(
            self.session,
            account_selector="demo@example.com",
            message_id="msg-1",
            instruction="Reply with thanks.",
            body="Thanks.",
            create_draft=True,
            confirm=True,
        )

        draft = message.last_reply
        self.assertTrue(result["created"])
        self.assertIn("Best regards, Demo", draft.HTMLBody)
        self.assertIn("Need approval today for the contract.", draft.HTMLBody)
        self.assertEqual(result["draft_content"]["thread_content_source"], "manual_quote_fallback")
        self.assertIn("thread_quote_fallback_used", result["draft_content"]["warnings"])

    def test_same_account_reply_uses_target_store_drafts_when_sender_cannot_be_verified(self):
        message = self.session.GetItemFromID("msg-1")
        drafts = client.resolve_folder(client.resolve_account(self.session, "demo@example.com"), "drafts")

        def reply_rejecting_sender():
            message.last_reply = FakeReply(
                Subject=f"RE: {message.Subject}",
                To=message.SenderEmailAddress,
                reject_send_using=True,
            )
            return message.last_reply

        message.Reply = reply_rejecting_sender

        result = client.draft_reply(
            self.session,
            account_selector="demo@example.com",
            message_id="msg-1",
            instruction="Reply with thanks.",
            body="Thanks.",
            create_draft=True,
            confirm=True,
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["draft_placement"]["strategy"], "target_store_drafts")
        self.assertEqual(len(drafts.Items), 1)
        draft = drafts.Items[-1]
        self.assertTrue(draft.saved)
        self.assertEqual(draft.SendUsingAccount.SmtpAddress, "demo@example.com")
        self.assertEqual(draft.To, "alice@example.com")

    def test_draft_reply_cross_account_creates_draft_in_target_store_drafts(self):
        response_session = make_response_session()
        anchor = response_session.GetItemFromID("anchor-1")
        anchor_drafts = client.resolve_folder(client.resolve_account(response_session, "anchor@example.com"), "drafts")
        reply_account = client.resolve_account(response_session, "reply@example.com")
        reply_drafts = client.resolve_folder(reply_account, "drafts")

        result = client.draft_reply(
            response_session,
            account_selector="anchor@example.com",
            send_using_account_selector="reply@example.com",
            message_id="anchor-1",
            instruction="Reply from the recipient account.",
            body="Thanks.",
            create_draft=True,
            confirm=True,
        )

        self.assertEqual(result["account"], "anchor@example.com")
        self.assertEqual(result["send_using_account"], "reply@example.com")
        self.assertEqual(result["draft_placement"]["strategy"], "target_store_drafts")
        self.assertEqual(result["draft_placement"]["target_store"], "reply@example.com")
        self.assertTrue(result["draft_placement"]["placement_verified"])
        self.assertEqual(len(anchor_drafts.Items), 0)
        self.assertIsNotNone(anchor.last_reply)
        self.assertFalse(anchor.last_reply.saved)
        self.assertEqual(len(reply_drafts.Items), 2)
        draft = reply_drafts.Items[-1]
        self.assertTrue(draft.saved)
        self.assertIs(draft.Parent, reply_drafts)
        self.assertEqual(draft.SendUsingAccount.SmtpAddress, "reply@example.com")
        self.assertEqual(draft.To, "clientservices@example.com")
        self.assertIn("<p>Thanks.</p>", draft.HTMLBody)

    def test_draft_reply_create_adds_explicit_attachment_before_save(self):
        message = self.session.GetItemFromID("msg-1")
        with tempfile.TemporaryDirectory() as temp_dir:
            attachment_path = Path(temp_dir) / "transfer.pdf"
            attachment_path.write_bytes(b"%PDF-1.4\n")

            result = client.draft_reply(
                self.session,
                account_selector="demo@example.com",
                message_id="msg-1",
                instruction="Reply with the transfer PDF.",
                body="Attached.",
                create_draft=True,
                confirm=True,
                attachments=[str(attachment_path)],
            )

        draft = message.last_reply
        self.assertTrue(result["created"])
        self.assertIsNotNone(draft)
        self.assertTrue(draft.saved)
        self.assertEqual(draft.Attachments.added_paths, [str(attachment_path.resolve())])
        self.assertEqual(result["draft_attachments"]["count"], 1)
        self.assertEqual(result["draft_attachments"]["items"][0]["filename"], "transfer.pdf")
        self.assertTrue(result["draft_attachments"]["items"][0]["attached"])

    def test_draft_reply_missing_attachment_fails_before_draft_creation(self):
        message = self.session.GetItemFromID("msg-1")

        with self.assertRaisesRegex(ValueError, "Attachment path does not exist"):
            client.draft_reply(
                self.session,
                account_selector="demo@example.com",
                message_id="msg-1",
                instruction="Reply with the transfer PDF.",
                body="Attached.",
                create_draft=True,
                confirm=True,
                attachments=[str(Path(tempfile.gettempdir()) / "missing-transfer.pdf")],
            )

        self.assertIsNone(message.last_reply)

    def test_draft_forward_cross_account_creates_draft_in_target_store_drafts(self):
        response_session = make_response_session()
        reply_account = client.resolve_account(response_session, "reply@example.com")
        reply_drafts = client.resolve_folder(reply_account, "drafts")

        result = client.draft_forward(
            response_session,
            account_selector="anchor@example.com",
            send_using_account_selector="reply@example.com",
            message_id="anchor-1",
            to="third@example.com",
            instruction="Forward from the recipient account.",
            body="Forwarding.",
            create_draft=True,
            confirm=True,
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["draft_placement"]["strategy"], "target_store_drafts")
        draft = reply_drafts.Items[-1]
        self.assertTrue(draft.saved)
        self.assertEqual(draft.To, "third@example.com")
        self.assertEqual(draft.SendUsingAccount.SmtpAddress, "reply@example.com")
        self.assertIn("<p>Forwarding.</p>", draft.HTMLBody)

    def test_draft_forward_create_adds_explicit_attachment_before_save(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            attachment_path = Path(temp_dir) / "transfer.pdf"
            attachment_path.write_bytes(b"%PDF-1.4\n")

            result = client.draft_forward(
                self.session,
                account_selector="demo@example.com",
                message_id="msg-1",
                to="forward@example.com",
                instruction="Forward with the transfer PDF.",
                body="Forwarding.",
                create_draft=True,
                confirm=True,
                attachments=[str(attachment_path)],
            )

        draft = self.session.GetItemFromID("msg-1").last_forward
        self.assertTrue(result["created"])
        self.assertEqual(draft.Attachments.added_paths, [str(attachment_path.resolve())])
        self.assertEqual(result["draft_attachments"]["items"][0]["filename"], "transfer.pdf")

    def test_cross_account_draft_warns_when_send_using_account_cannot_be_set(self):
        response_session = make_response_session()
        reply_account = client.resolve_account(response_session, "reply@example.com")
        reply_drafts = client.resolve_folder(reply_account, "drafts")
        reply_drafts.Items.reject_send_using = True

        result = client.draft_reply(
            response_session,
            account_selector="anchor@example.com",
            send_using_account_selector="reply@example.com",
            message_id="anchor-1",
            instruction="Reply from the recipient account.",
            body="Thanks.",
            create_draft=True,
            confirm=True,
        )

        self.assertTrue(result["created"])
        self.assertIs(reply_drafts.Items[-1].Parent, reply_drafts)
        self.assertIn("send_using_account_unset", result["draft_placement"]["warnings"])

    def test_parser_accepts_send_using_account_for_drafts(self):
        parser = client.build_parser()

        reply_args = parser.parse_args(
            [
                "draft-reply",
                "--account",
                "anchor@example.com",
                "--send-using-account",
                "reply@example.com",
                "--message-id",
                "anchor-1",
                "--instruction",
                "Confirm.",
                "--attach",
                "C:/tmp/transfer.pdf",
            ]
        )
        forward_args = parser.parse_args(
            [
                "draft-forward",
                "--account",
                "anchor@example.com",
                "--send-using-account",
                "reply@example.com",
                "--message-id",
                "anchor-1",
                "--to",
                "third@example.com",
                "--instruction",
                "Forward.",
                "--attach",
                "C:/tmp/transfer.pdf",
            ]
        )

        self.assertEqual(reply_args.send_using_account, "reply@example.com")
        self.assertEqual(forward_args.send_using_account, "reply@example.com")
        self.assertEqual(reply_args.attach, ["C:/tmp/transfer.pdf"])
        self.assertEqual(forward_args.attach, ["C:/tmp/transfer.pdf"])

    def test_draft_forward_create_preserves_existing_html_body(self):
        message = self.session.GetItemFromID("msg-1")

        def forward_with_thread():
            message.last_forward = FakeForward(
                Subject=f"FW: {message.Subject}",
                To="",
                Body=f"Quoted original\r\n{message.Body}",
                HTMLBody=(
                    "<html><body><table><tr><td>Quoted original</td></tr></table>"
                    f"<p>{message.Body}</p></body></html>"
                ),
            )
            return message.last_forward

        message.Forward = forward_with_thread

        result = client.draft_forward(
            self.session,
            account_selector="demo@example.com",
            message_id="msg-1",
            to="forward@example.com",
            instruction="Forward with context.",
            body="Forwarding <context>.",
            create_draft=True,
            confirm=True,
        )

        draft = message.last_forward
        self.assertTrue(result["created"])
        self.assertIsNotNone(draft)
        self.assertTrue(draft.saved)
        self.assertIn("<p>Forwarding &lt;context&gt;.</p>", draft.HTMLBody)
        self.assertIn("<table><tr><td>Quoted original</td></tr></table>", draft.HTMLBody)
        self.assertIn("Need approval today for the contract.", draft.Body)
        self.assertEqual(result["draft_content"]["thread_content_source"], "native_forward")

    def test_apply_action_create_draft_uses_selected_account_drafts_folder(self):
        account = client.resolve_account(self.session, "demo@example.com")
        drafts = client.resolve_folder(account, "drafts")

        result = client.apply_action(
            self.session,
            account_selector="demo@example.com",
            message_id=None,
            action="create-draft",
            confirm=True,
            application=FailingCreateItemApplication(),
            subject="Manual follow-up",
            to="recipient@example.com",
            body="Draft body",
        )

        self.assertTrue(result["created"])
        self.assertEqual(len(drafts.Items), 1)
        draft = drafts.Items[-1]
        self.assertTrue(draft.saved)
        self.assertIs(draft.Parent, drafts)
        self.assertEqual(draft.SendUsingAccount.SmtpAddress, "demo@example.com")
        self.assertEqual(draft.Subject, "Manual follow-up")
        self.assertEqual(draft.To, "recipient@example.com")
        self.assertEqual(draft.Body, "Draft body")
        self.assertEqual(result["draft_placement"]["strategy"], "target_store_drafts")
        self.assertTrue(result["draft_placement"]["placement_verified"])

    def test_move_message_preview_does_not_mutate(self):
        account = client.resolve_account(self.session, "demo@example.com")
        inbox = client.resolve_folder(account, "inbox")
        projects = client.resolve_folder(account, "custom:Inbox/Projects")

        preview = client.move_message(
            self.session,
            account_selector="demo@example.com",
            message_id="msg-1",
            target_folder="custom:Inbox/Projects",
            confirm=False,
        )

        self.assertFalse(preview["moved"])
        self.assertTrue(preview["would_move"])
        self.assertEqual(preview["message"]["entry_id"], "msg-1")
        self.assertEqual(preview["source_folder"]["path"], r"\\Mailbox\\Inbox")
        self.assertEqual(preview["target_folder"]["path"], r"\\Mailbox\\Inbox\\Projects")
        self.assertIs(self.session.GetItemFromID("msg-1").Parent, inbox)
        self.assertNotIn(self.session.GetItemFromID("msg-1"), projects.Items)

    def test_move_message_confirm_moves_to_custom_folder(self):
        account = client.resolve_account(self.session, "demo@example.com")
        inbox = client.resolve_folder(account, "inbox")
        projects = client.resolve_folder(account, "custom:Inbox/Projects")

        result = client.move_message(
            self.session,
            account_selector="demo@example.com",
            message_id="msg-1",
            target_folder="custom:Inbox/Projects",
            confirm=True,
        )

        moved = self.session.GetItemFromID("msg-1")
        self.assertTrue(result["moved"])
        self.assertFalse(result["would_move"])
        self.assertEqual(result["message"]["folder_path"], r"\\Mailbox\\Inbox\\Projects")
        self.assertIs(moved.Parent, projects)
        self.assertIn(moved, projects.Items)
        self.assertNotIn(moved, inbox.Items)

    def test_move_message_rejects_unresolved_target_folder(self):
        with self.assertRaisesRegex(ValueError, "Custom folder path segment not found"):
            client.move_message(
                self.session,
                account_selector="demo@example.com",
                message_id="msg-1",
                target_folder="custom:Inbox/Missing",
                confirm=False,
            )

    def test_apply_action_requires_confirmation_for_mutations(self):
        with self.assertRaisesRegex(ValueError, "requires --confirm"):
            client.apply_action(
                self.session,
                account_selector="demo@example.com",
                message_id="msg-1",
                action="delete",
                confirm=False,
            )

    def test_dispatch_rejects_all_folder_search_without_query(self):
        parser = client.build_parser()
        args = parser.parse_args(["search", "--all-folders", "--all-accounts"])

        with self.assertRaisesRegex(ValueError, "requires --query"):
            client.dispatch_operation(args, application=None, session=self.session)

    def test_dispatch_routes_find_response(self):
        parser = client.build_parser()
        args = parser.parse_args(
            [
                "find-response",
                "--account",
                "anchor@example.com",
                "--message-id",
                "anchor-1",
                "--fallback-all-accounts",
                "--exclude-drafts",
            ]
        )

        result = client.dispatch_operation(args, application=None, session=make_response_session())

        self.assertEqual(result["operation"], "find-response")
        self.assertTrue(result["ok"])
        self.assertIn("reply-sent", [message["entry_id"] for message in result["result"]["messages"]])

    def test_dispatch_routes_move_message_preview(self):
        parser = client.build_parser()
        args = parser.parse_args(
            [
                "move-message",
                "--account",
                "demo@example.com",
                "--message-id",
                "msg-1",
                "--target-folder",
                "custom:Inbox/Projects",
            ]
        )

        result = client.dispatch_operation(args, application=None, session=self.session)

        self.assertEqual(result["operation"], "move-message")
        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["would_move"])
        self.assertFalse(result["result"]["moved"])

    def test_search_all_folders_hint_write_failures_become_warnings(self):
        original_remember = client.remember_folder_hints
        client.remember_folder_hints = lambda **kwargs: (_ for _ in ()).throw(PermissionError("hint file locked"))
        try:
            result = client.search_all_folders(
                self.session,
                account_selector="demo@example.com",
                all_accounts=False,
                query="lettre24",
                unread=False,
                sender=None,
                recipient=None,
                days=7,
                folder_limit=10,
                per_folder_limit=5,
                update_hints=True,
                use_cache=False,
                update_cache=False,
                broad_scan=False,
            )
        finally:
            client.remember_folder_hints = original_remember

        self.assertEqual(result["messages"][0]["entry_id"], "msg-5")
        self.assertTrue(result["warnings"])
        self.assertIn("hint", result["warnings"][0].lower())

    def test_queue_bypass_operations_do_not_enter_queue(self):
        original_queue = getattr(client, "outlook_operation_queue", None)
        original_connect = client.connect_outlook
        original_dispatch = client.dispatch_operation

        @contextlib.contextmanager
        def forbidden_queue(*args, **kwargs):
            raise AssertionError("queue should not be used")
            yield

        client.outlook_operation_queue = forbidden_queue
        client.connect_outlook = lambda: (_ for _ in ()).throw(AssertionError("COM should not connect"))
        client.dispatch_operation = lambda args, application=None, session=None: client.make_result(
            ok=True,
            operation="cache-status",
            result={"cache": {"messages": 0}},
        )
        try:
            from outlook_classic_mail_client import cli

            exit_code = cli.main(["cache-status"])
        finally:
            if original_queue is not None:
                client.outlook_operation_queue = original_queue
            else:
                delattr(client, "outlook_operation_queue")
            client.connect_outlook = original_connect
            client.dispatch_operation = original_dispatch

        self.assertEqual(exit_code, 0)

    def test_parser_accepts_cache_and_sync_commands(self):
        parser = client.build_parser()

        search_args = parser.parse_args(
            [
                "search",
                "--all-folders",
                "--all-accounts",
                "--query",
                "lettre24",
                "--bypass-cache",
                "--broad-scan",
                "--no-update-cache",
            ]
        )
        global_args = parser.parse_args(["--queue-timeout-sec", "30", "accounts"])
        refresh_args = parser.parse_args(["cache-refresh", "--all-accounts", "--days", "30", "--force"])
        sync_args = parser.parse_args(["sync-mail", "--refresh-cache", "--all-accounts"])

        self.assertTrue(search_args.bypass_cache)
        self.assertTrue(search_args.broad_scan)
        self.assertTrue(search_args.no_update_cache)
        self.assertEqual(global_args.queue_timeout_sec, 30)
        self.assertEqual(refresh_args.operation, "cache-refresh")
        self.assertEqual(sync_args.operation, "sync-mail")


if __name__ == "__main__":
    unittest.main()
