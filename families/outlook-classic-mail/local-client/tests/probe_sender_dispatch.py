"""Opt-in live COM sender probe; never displays or sends existing/user messages."""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

client_home = Path(os.environ.get("OUTLOOK_CLASSIC_MAIL_HOME", str(Path(__file__).resolve().parents[1])))
sys.path.insert(0, str(client_home / "src"))
from outlook_classic_mail_client import client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--runtime-home", type=Path, default=Path(os.environ["LOCALAPPDATA"]) / "Tools" / "outlook-classic-mail")
    parser.add_argument("--verify-save", action="store_true", help="Save the empty probe, reopen to verify, then delete it from Drafts.")
    args = parser.parse_args()
    runtime_state = args.runtime_home / "state"
    if not runtime_state.is_dir():
        parser.error("Use the active installed runtime's existing state directory for shared COM coordination")
    with client.queueing.acquire_queue_turn("sender-dispatch-probe", path=runtime_state / "outlook_queue.sqlite"):
        with client.outlook_com_lock(path=runtime_state / "outlook_com.lock"):
            _, session = client.connect_outlook()
            account = client.resolve_account(session, args.account)
            folder = account["store"].GetDefaultFolder(client.OL_FOLDER_DRAFTS)
            item = client.create_mail_item_in_folder(folder)
            saved = False
            probe_subject = "agent-toolbelt disposable sender probe " + uuid.uuid4().hex
            try:
                assignment = {}
                client.set_send_using_account(item, account, [], diagnostics=assignment)
                ordinary_match = assignment["readback"]["matches_requested"]
                import pythoncom
                member = item._oleobj_.GetIDsOfNames("SendUsingAccount")
                item._oleobj_.Invoke(member, 0, pythoncom.DISPATCH_PROPERTYPUTREF, 0, account["account"])
                reference_match = client.inspect_sender_account(
                    item, expected=account["smtp_address"]
                )["verified"]
                persisted = None
                if args.verify_save:
                    if not ordinary_match:
                        raise AssertionError("Helper assignment failed; refusing to save the probe")
                    item.Subject = probe_subject
                    client.save_draft_with_sender(item, account, [], diagnostics=assignment)
                    saved = True
                    persisted = client.verify_saved_draft_sender(session, item, account)
                    if persisted["verified"] is not True:
                        raise AssertionError(f"Saved sender verification failed: {persisted['status']}")
                print(json.dumps({
                    "helper_assignment_method": assignment.get("method", "attribute_set"),
                    "client_home": str(Path(client.__file__).resolve().parents[2]),
                    "helper_assignment_matches": ordinary_match,
                    "reference_assignment_matches": reference_match,
                    "saved": saved,
                    "saved_sender_verified": (persisted or {}).get("verified"),
                    "sent": False,
                }, indent=2))
            finally:
                if saved:
                    item.Delete()  # Remove only this empty probe from Drafts.
                    if folder.Items.Restrict(f"[Subject] = '{probe_subject}'").Count:
                        raise AssertionError("Disposable probe remains in Drafts")
                    print(json.dumps({"probe_removed_from_drafts": True}))
                else:
                    item.Close(1)  # olDiscard: no saved draft for the default probe.


if __name__ == "__main__":
    main()
