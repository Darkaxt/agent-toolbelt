"""Opt-in owned empty draft probe; separate invocations prove cold readback. No Send."""
import argparse,hashlib,json,os,sys,uuid
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('operation',choices=('create','read','edit','cleanup'))
p.add_argument('--account',required=True);p.add_argument('--client-home',type=Path,required=True)
p.add_argument('--runtime-home',type=Path,required=True);p.add_argument('--scratch',type=Path,required=True)
p.add_argument('--report',type=Path,required=True);a=p.parse_args()
sys.path.insert(0,str(a.client_home/'src'))
from outlook_classic_mail_client import client
a.scratch.mkdir(parents=True,exist_ok=True);identity=a.scratch/'identity.json'
with client.queueing.acquire_queue_turn('sender-persistence-probe-'+a.operation,path=a.runtime_home/'state/outlook_queue.sqlite'):
  with client.outlook_com_lock(path=a.runtime_home/'state/outlook_com.lock'):
    _,session=client.connect_outlook();account=client.resolve_account(session,a.account)
    if a.operation=='create':
      assert not identity.exists()
      attachment=a.scratch/'sender-probe.txt';attachment.write_bytes(b'Owned sender preservation fixture\n')
      body='Owned sender persistence body.'
      record={'subject':'agent-toolbelt owned sender persistence '+uuid.uuid4().hex,'body':body,
              'account':a.account,'attachment_sha256':hashlib.sha256(attachment.read_bytes()).hexdigest()}
      identity.write_text(json.dumps(record))
      result=client.create_target_store_draft(account,session=session,subject=record['subject'],to=None,body=body,
          draft_attachments=client.prepare_draft_attachments([str(attachment)]))
      record['entry_id']=result['draft_entry_id'];identity.write_text(json.dumps(record))
      assert result['draft_placement']['sender_verification']['verified'],result['draft_placement']['sender_verification']
    else:record=json.loads(identity.read_text())
    item=client.resolve_message(session,account,record['entry_id'])
    assert item.Subject==record['subject'] and item.Recipients.Count==0 and not item.Sent
    if a.operation=='edit':
      record['body']='Updated owned sender persistence body.'
      result=client.edit_draft(session,account_selector=a.account,message_id=record['entry_id'],
          send_using_account_selector=a.account,body=record['body'],confirm=True)
      identity.write_text(json.dumps(record));assert result['draft_sender']['verified'],result['draft_sender']
    sender=client.inspect_persisted_sender(item,expected=a.account)
    if a.operation!='cleanup':
      assert sender['verified'],sender
      assert record['body'] in item.Body and item.Attachments.Count==1
      exported=a.scratch/(a.operation+'-attachment.txt');item.Attachments.Item(1).SaveAsFile(str(exported))
      assert hashlib.sha256(exported.read_bytes()).hexdigest()==record['attachment_sha256']
    else:
      item.Delete()
      trash=account['store'].GetDefaultFolder(client.OL_FOLDER_DELETED_ITEMS)
      matches=trash.Items.Restrict("[Subject] = '"+record['subject']+"'")
      assert matches.Count==1
      owned=matches.Item(1);assert owned.Subject==record['subject'] and owned.Recipients.Count==0
      owned.Delete()
    report={'ok':True,'operation':a.operation,'sender_verified':sender['verified'],
            'native_persistence':sender.get('persistence'),'body_and_attachment_preserved':a.operation!='cleanup',
            'sent':False,'user_drafts_mutated':False,'owned_fixture_removed':a.operation=='cleanup'}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2));print(json.dumps(report))
