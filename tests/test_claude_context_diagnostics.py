import hashlib
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT/'families/claude-context-diagnostics/codex/skills/claude-context-diagnostics/scripts/context_diagnostics.py'
SPEC = importlib.util.spec_from_file_location('claude_context_diagnostics',HELPER)
diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diag)
RELEASE_SPEC = importlib.util.spec_from_file_location('claude_context_release',ROOT/'families/claude-context-diagnostics/scripts/release_local.py')
release = importlib.util.module_from_spec(RELEASE_SPEC)
RELEASE_SPEC.loader.exec_module(release)
SID = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'


def record(uid,parent=None,kind='user',**kw):
    return {'uuid':uid,'parentUuid':parent,'type':kind,'sessionId':SID,'timestamp':'2026-01-01T00:00:00Z',**kw}


def assistant(uid,parent,tokens,cached=0,request=None,content=None):
    return record(uid,parent,'assistant',requestId=request or uid,message={'id':request or uid,'model':'fictional-model','usage':{'input_tokens':tokens,'cache_read_input_tokens':cached,'output_tokens':3},'content':content or []})


class ContextDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['CLAUDE_CONTEXT_TEST_ROOT'])/uuid.uuid4().hex
        cls.root.mkdir(parents=True,exist_ok=True)

    def setUp(self):
        self.path = self.root/(self._testMethodName+'.jsonl')

    def write(self,rows,trailing=b''):
        self.path.write_bytes(b''.join((json.dumps(r)+'\n').encode() for r in rows)+trailing)

    def test_cache_usage_and_source_unchanged(self):
        self.write([record('u'),assistant('a','u',80,20)])
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        report = diag.report_session(self.path,SID)
        self.assertEqual(report['latest_usage']['total_input_tokens'],100)
        self.assertEqual(report['latest_usage']['cache_read_input_tokens'],20)
        self.assertEqual(before,hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_latest_branch_duplicates_and_sidechain(self):
        rows = [record('root'),assistant('abandoned','root',900),assistant('chosen','root',100),
                assistant('side','root',5000),assistant('chosen','root',100)]
        rows[3]['isSidechain'] = True
        self.write(rows)
        report = diag.report_session(self.path,SID)
        self.assertEqual(report['latest_usage']['total_input_tokens'],100)
        self.assertEqual(report['coverage']['duplicate_uuids'],1)
        self.assertEqual(diag.report_session(self.path,SID,leaf='abandoned')['latest_usage']['total_input_tokens'],900)

    def test_compaction_logical_ancestry_and_no_cross_boundary_growth(self):
        boundary = record('compact',kind='system',subtype='compact_boundary',logicalParentUuid='old',
                          compactMetadata={'trigger':'auto','preTokens':240000,'postTokens':45000,'durationMs':200000})
        self.write([record('root'),assistant('old','root',230000),boundary,record('summary','compact',isCompactSummary=True),assistant('new','summary',70000)])
        report = diag.report_session(self.path,SID)
        self.assertEqual(report['compactions'][0]['first_observed_input_after'],70000)
        self.assertEqual(report['compaction_summary']['shown_duration_seconds'],200)
        self.assertEqual(report['largest_input_growth'],[])
        self.assertTrue(report['ancestry_complete'])

    def test_tool_result_growth_privacy_and_request_dedup(self):
        secret = 'SECRET-PROMPT-COMMAND-CREDENTIAL-CONTENT'
        tool = {'type':'tool_use','id':'tool-1','name':'Read','input':{'file_path':'X:/private/sample.asm','command':secret}}
        result = {'type':'tool_result','tool_use_id':'tool-1','content':secret*100}
        first = assistant('a','root',100,request='response-1',content=[tool])
        chunk = assistant('chunk','a',100,request='response-1')
        self.write([record('root',message={'content':secret}),first,chunk,record('result','chunk',message={'content':[result]}),assistant('b','result',150)])
        report = diag.report_session(self.path,SID)
        raw = json.dumps(report)
        self.assertNotIn(secret,raw)
        self.assertNotIn('private',raw)
        self.assertEqual(report['largest_tool_results'][0]['file'],'sample.asm')
        self.assertEqual(report['largest_tool_results'][0]['characters'],len(secret)*100)
        self.assertEqual(report['largest_input_growth'][0]['observed_input_delta'],50)

    def test_missing_usage_partial_append_and_bounded_output(self):
        self.write([record('u')],b'{"type":"assistant"')
        report = diag.report_session(self.path,SID)
        self.assertIsNone(report['latest_usage'])
        self.assertGreater(report['coverage']['trailing_partial_bytes'],0)
        self.assertLess(len(json.dumps(report)),5000)

    def test_invalid_identity_and_ambiguous_resolution(self):
        self.write([record('u',sessionId=OTHER)])
        with self.assertRaises(diag.DiagnosticError):
            diag.report_session(self.path,SID)
        with self.assertRaises(diag.DiagnosticError):
            diag.session_uuid('../latest')
        home = self.root/'ambiguous'
        for name in ('one','two'):
            p = home/'projects'/name/(SID+'.jsonl')
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text('{}\n')
        with self.assertRaises(diag.DiagnosticError):
            diag.resolve_transcript(home,SID)

    def test_malformed_and_missing_parent_disclosed(self):
        self.write([assistant('a','missing',10)])
        with self.path.open('ab') as stream:
            stream.write(b'not-json\n')
        report = diag.report_session(self.path,SID)
        self.assertFalse(report['ancestry_complete'])
        self.assertEqual(report['coverage']['malformed_records'],1)

    def test_invalid_parent_reference_cannot_claim_complete_ancestry(self):
        self.write([assistant('a','invalid parent value',10)])
        report = diag.report_session(self.path,SID)
        self.assertFalse(report['ancestry_complete'])
        self.assertEqual(report['coverage']['invalid_parent_references'],1)
        self.assertTrue(report['warnings'])

    def test_unsupported_tail_preserves_mainline_usage_and_is_disclosed(self):
        self.write([record('root'),assistant('a','root',100),record('extra',kind='future-record')])
        report = diag.report_session(self.path,SID)
        self.assertEqual(report['latest_usage']['total_input_tokens'],100)
        self.assertEqual(report['leaf_uuid'],'a')
        self.assertEqual(report['coverage']['unsupported_conversation_records'],1)
        self.assertTrue(report['warnings'])

    def test_unknown_parent_bridge_is_retained_without_becoming_default_leaf(self):
        self.write([record('root'),assistant('a','root',100),record('bridge','a',kind='future-record'),assistant('b','bridge',150)])
        report = diag.report_session(self.path,SID)
        self.assertEqual(report['latest_usage']['total_input_tokens'],150)
        self.assertTrue(report['ancestry_complete'])
        self.assertEqual(report['coverage']['unsupported_conversation_records'],1)

    def test_out_of_range_timestamp_returns_bounded_json_without_traceback(self):
        row=assistant('a',None,100)
        row['timestamp']='0001-01-01T00:00:00+23:59'
        self.write([row])
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            code=diag.main(['report','--session-id',SID,'--transcript',str(self.path)])
        self.assertEqual(code,0)
        report=json.loads(output.getvalue())
        self.assertIsNone(report['latest_usage']['timestamp'])
        self.assertEqual(report['coverage']['invalid_timestamps'],1)
        self.assertTrue(report['warnings'])
        self.assertNotIn(str(self.path),output.getvalue())

    def test_attachment_nodes_preserve_compaction_ancestry(self):
        boundary = record('compact',kind='system',subtype='compact_boundary',compactMetadata={'preTokens':240000})
        bridge = record('attachment','compact','attachment')
        self.write([boundary,bridge,assistant('a','attachment',90000)])
        report = diag.report_session(self.path,SID)
        self.assertTrue(report['ancestry_complete'])
        self.assertEqual(len(report['compactions']),1)

    def test_limits_and_invalid_usage_do_not_invent_headroom(self):
        row = assistant('a',None,100)
        row['message']['usage']['cache_read_input_tokens'] = -5
        self.write([row])
        report = diag.report_session(self.path,SID)
        self.assertIsNone(report['latest_usage']['total_input_tokens'])
        self.assertNotIn('remaining_tokens',report)
        with self.assertRaises(Exception):
            diag.bounded('100')

    def test_old_large_results_do_not_hide_recent_work(self):
        result = lambda n: {'type':'tool_result','tool_use_id':n,'content':'x'*(1000 if n == 'old' else 10)}
        boundary = record('compact',kind='system',subtype='compact_boundary',logicalParentUuid='oldresult',compactMetadata={})
        self.write([record('root'),record('oldresult','root',message={'content':[result('old')]}),boundary,
                    record('newresult','compact',message={'content':[result('new')]}),assistant('a','newresult',100)])
        report = diag.report_session(self.path,SID)
        self.assertEqual(report['largest_tool_results'][0]['tool_id'],'new')

    def test_release_idempotence_and_unrelated_file_protection(self):
        target = self.root/'installed'
        payload = {'SKILL.md':b'fixture','scripts/helper.py':b'fixture helper'}
        release.install_tree(target,payload)
        release.install_tree(target,payload)
        foreign = target/'user-file.txt'
        foreign.write_text('preserve')
        with self.assertRaises(RuntimeError):
            release.install_tree(target,payload)
        self.assertEqual(foreign.read_text(),'preserve')

    @unittest.skipUnless(os.name=='nt','Windows existing-bundle upgrade contract')
    def test_verified_upgrade_replaces_only_exact_previous_bytes(self):
        target=self.root/'upgrade-exact';old={'SKILL.md':b'old','scripts/helper.py':b'old helper'}
        new={'SKILL.md':b'new','scripts/helper.py':b'new helper'}
        release.install_tree(target,old)
        release.install_tree(target,new,old)
        release.install_tree(target,new,old)
        self.assertEqual({name:(target/name).read_bytes() for name in new},new)

    @unittest.skipUnless(os.name=='nt','Windows existing-bundle upgrade contract')
    def test_upgrade_preserves_local_edits_and_existing_writers(self):
        old={'SKILL.md':b'old','helper.py':b'old helper'};new={name:b'new' for name in old}
        changed=self.root/'upgrade-edited';release.install_tree(changed,old)
        (changed/'helper.py').write_bytes(b'local edit')
        with self.assertRaises(RuntimeError):release.install_tree(changed,new,old)
        self.assertEqual((changed/'SKILL.md').read_bytes(),b'old')
        self.assertEqual((changed/'helper.py').read_bytes(),b'local edit')
        locked=self.root/'upgrade-locked';release.install_tree(locked,old)
        with (locked/'helper.py').open('r+b'):
            with self.assertRaises(OSError):release.install_tree(locked,new,old)
        self.assertEqual({name:(locked/name).read_bytes() for name in old},old)

    @unittest.skipUnless(os.name=='nt','Windows existing-bundle upgrade contract')
    def test_failed_upgrade_restores_previous_bundle_before_unlocking(self):
        target=self.root/'upgrade-failure';old={'SKILL.md':b'old','helper.py':b'old helper'}
        new={name:b'new' for name in old};release.install_tree(target,old)
        original=release.write_locked;calls=0
        def interrupted(stream,data):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('Fictional write failure')
            original(stream,data)
        with patch.object(release,'write_locked',side_effect=interrupted):
            with self.assertRaises(OSError):release.install_tree(target,new,old)
        self.assertEqual({name:(target/name).read_bytes() for name in old},old)


if __name__ == '__main__':
    unittest.main()
