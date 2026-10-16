import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_toolbelt_transactional_cleanup.engine import Engine, CleanupError
from agent_toolbelt_transactional_cleanup.retirement import RetirementError
from agent_toolbelt_transactional_cleanup import generated_dependencies


class GitHubSourceTests(unittest.TestCase):
    def test_existing_cli_verifies_hash_without_login_or_credential_output(self):
        oid = 'a' * 40
        with patch.object(generated_dependencies.shutil, 'which', return_value='gh.exe'), \
                patch.object(generated_dependencies.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, oid + '\n', '')
            generated_dependencies.github_source_commit(['owner', 'repo'], oid)
            self.assertEqual(run.call_args.args[0], ['gh.exe', 'api', '--hostname', 'github.com',
                             f'repos/owner/repo/git/commits/{oid}', '--jq', '.sha'])
            run.return_value = subprocess.CompletedProcess([], 0, 'b' * 40 + '\n', '')
            with self.assertRaises(RetirementError):
                generated_dependencies.github_source_commit(['owner', 'repo'], oid)
            run.return_value = subprocess.CompletedProcess([], 1, '', 'authentication failed')
            with self.assertRaises(RetirementError):
                generated_dependencies.github_source_commit(['owner', 'repo'], oid)

    def test_missing_cli_uses_exact_public_api_response(self):
        oid = 'c' * 40
        with patch.object(generated_dependencies.shutil, 'which', return_value=None), \
                patch.object(generated_dependencies, 'urlopen') as request:
            request.return_value.__enter__.return_value.read.return_value = json.dumps({'sha': oid})
            generated_dependencies.github_source_commit(['owner', 'repo'], oid)
            request.side_effect = OSError('source unavailable')
            with self.assertRaises(RetirementError):
                generated_dependencies.github_source_commit(['owner', 'repo'], oid)


@unittest.skipUnless(os.name == 'nt', 'Windows exact-member cleanup')
class GeneratedDependencyTests(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.run(['git', '-C', str(root), *args], check=True,
                              capture_output=True, text=True).stdout

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        upstream = self.base / 'upstream'; upstream.mkdir()
        self.git(upstream, 'init')
        (upstream / 'source.txt').write_text('original source\n')
        self.git(upstream, 'add', '.')
        self.git(upstream, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'source')
        self.head = self.git(upstream, 'rev-parse', 'HEAD').strip()
        self.origin = self.base / 'origin.git'
        self.git(self.base, 'clone', '--bare', '--no-hardlinks', str(upstream), str(self.origin))
        self.project = self.base / 'project'; self.project.mkdir()
        self.git(self.project, 'init')
        self.recipe = self.project / 'CMakeLists.txt'
        self.recipe.write_text(f'FetchContent_Declare(example GIT_REPOSITORY {self.origin.as_posix()} GIT_TAG {self.head})\n')
        self.git(self.project, 'add', '.')
        self.git(self.project, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'recipe')
        self.repo = self.project / '.cxx/config/arm64/_deps/example-src'
        self.repo.parent.mkdir(parents=True)
        self.git(self.base, 'clone', '--no-hardlinks', str(self.origin), str(self.repo))
        self.validation = self.base / 'validation'; self.validation.mkdir()
        self.record = {'version': 1, 'mode': 'cmake-fetchcontent', 'repository': str(self.repo),
                       'project': str(self.project), 'producer': str(self.recipe),
                       'dependency': 'example', 'origin': self.origin.as_posix(), 'pin': self.head,
                       'patches': [], 'validation_root': str(self.validation),
                       'authorization': 'Remove this generated dependency cache',
                       'consumer_review': {'checked_at': '2026-10-16T00:00:00Z', 'ownership': 'test fixture',
                                           'schedulers_services': 'none', 'dependencies': 'rebuild from recipe',
                                           'active_consumers': []}}
        self.evidence = self.base / 'evidence.json'
        self.workspace = self.base / 'workspace'; self.workspace.mkdir()
        self.engine = Engine(self.base / 'state')
        self.tx = self.engine.begin(self.workspace, [self.repo])['transaction_id']
        self.processes = patch('agent_toolbelt_transactional_cleanup.retirement.active_processes', return_value=[])
        self.processes.start(); self.addCleanup(self.processes.stop)

    def register(self):
        self.evidence.write_text(json.dumps(self.record))
        return self.engine.register(self.tx, self.repo, 'generated-dependency-repository',
                                    'Pinned CMake generated dependency clone', regenerated=True,
                                    dependency_evidence=str(self.evidence),
                                    confirm_dependency_repository=str(self.repo))

    def ticket(self):
        self.register()
        review = self.engine.review(self.tx)
        return self.engine.ticket(self.tx, review['manifest_sha256'])['ticket_id']

    def test_outside_temp_location_is_accepted_and_source_recipe_preserved(self):
        before = self.recipe.read_bytes()
        with patch.object(self.engine, '_temp_roots', return_value=[self.base / 'elsewhere']):
            ticket = self.ticket()
        self.assertEqual(self.engine.apply(ticket)['ticket_state'], 'applied')
        self.assertFalse(self.repo.exists())
        self.assertEqual(self.recipe.read_bytes(), before)
        self.git(self.base, 'clone', '--no-hardlinks', str(self.origin), str(self.repo))
        self.assertEqual((self.repo / 'source.txt').read_text(), 'original source\n')

    def test_dirty_unknown_and_untracked_files_are_rejected(self):
        (self.repo / 'source.txt').write_text('private edit\n')
        with self.assertRaises(RetirementError): self.register()
        (self.repo / 'source.txt').write_text('original source\n')
        (self.repo / 'local.txt').write_text('private data')
        with self.assertRaises(RetirementError): self.register()

    def test_local_only_reflog_commit_is_preserved(self):
        (self.repo / 'source.txt').write_text('local commit\n')
        self.git(self.repo, 'add', '.')
        self.git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'private')
        self.git(self.repo, 'reset', '--hard', self.head)
        with self.assertRaises(RetirementError): self.register()

    def test_known_patch_is_reproduced_but_additional_edits_rejected(self):
        (self.repo / 'source.txt').write_text('maintained patch\n')
        patch_file = self.project / 'fix.patch'
        patch_file.write_text(self.git(self.repo, 'diff', '--binary'))
        self.recipe.write_text(self.recipe.read_text().replace(')', ' PATCH_COMMAND apply_fix)') + '\nset(patch_file ${CMAKE_CURRENT_SOURCE_DIR}/fix.patch)\n')
        self.git(self.project, 'add', '.')
        self.record['patches'] = [str(patch_file)]
        original_head = self.git(self.repo, 'rev-parse', 'HEAD')
        (self.repo / 'source.txt').write_text('private staged work\n')
        self.git(self.repo, 'add', 'source.txt')
        (self.repo / 'source.txt').write_text('maintained patch\n')
        with self.assertRaises(RetirementError): self.register()
        self.git(self.repo, 'reset', '--mixed', 'HEAD')
        ticket = self.ticket()
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), original_head)
        (self.repo / 'source.txt').write_text('unknown extra edit\n')
        with self.assertRaises(RetirementError): self.engine.apply(ticket)
        self.assertTrue(self.repo.exists())
        (self.repo / 'source.txt').write_text('maintained patch\n')
        self.assertEqual(self.engine.apply(ticket)['ticket_state'], 'applied')
        self.git(self.base, 'clone', '--no-hardlinks', str(self.origin), str(self.repo))
        self.git(self.repo, 'apply', str(patch_file))
        self.assertEqual((self.repo / 'source.txt').read_text(), 'maintained patch\n')

    def test_remote_tracking_ref_cannot_hide_private_history(self):
        (self.repo / 'source.txt').write_text('private history\n')
        self.git(self.repo, 'add', '.')
        self.git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'private')
        private = self.git(self.repo, 'rev-parse', 'HEAD').strip()
        self.git(self.repo, 'update-ref', 'refs/remotes/origin/private', private)
        self.git(self.repo, 'reset', '--hard', self.head)
        with self.assertRaises(RetirementError): self.register()

    def test_pin_recipe_location_and_active_consumers_are_checked(self):
        self.record['pin'] = 'wrong'
        with self.assertRaises(RetirementError): self.register()
        self.record['pin'] = self.head
        with patch('agent_toolbelt_transactional_cleanup.retirement.active_processes', return_value=[{'pid': 123}]):
            with self.assertRaises(RetirementError): self.register()

    def test_reviewed_file_edits_and_new_files_survive_partial_resume(self):
        ticket = self.ticket()
        source = self.repo / 'source.txt'
        source.write_text('concurrent work\n')
        with self.assertRaises(RetirementError): self.engine.apply(ticket)
        source.write_text('original source\n')
        (self.repo / 'new.txt').write_text('preserve concurrent file\n')
        with self.assertRaises(RetirementError): self.engine.apply(ticket)

    def test_local_branch_and_tag_names_are_not_discarded(self):
        self.git(self.repo, 'tag', 'private-tag')
        with self.assertRaises(RetirementError): self.register()
        self.git(self.repo, 'tag', '-d', 'private-tag')
        self.git(self.repo, 'branch', 'private-branch')
        with self.assertRaises(RetirementError): self.register()

    def test_ordinary_retirement_cannot_use_dependency_proof(self):
        self.evidence.write_text(json.dumps(self.record))
        with self.assertRaises(CleanupError):
            self.engine.register(self.tx, self.repo, 'retired-repository', 'wrong contract',
                                 regenerated=True, retirement_evidence=str(self.evidence),
                                 confirm_retire_repository=str(self.repo))

    def test_producer_changes_after_review_are_preserved(self):
        ticket = self.ticket()
        self.recipe.write_text(self.recipe.read_text() + '# user change\n')
        with self.assertRaises(RetirementError): self.engine.apply(ticket)
        self.assertTrue((self.repo / 'source.txt').exists())

    def test_partial_deletion_preserves_new_files_and_resumes_after_resolution(self):
        ticket = self.ticket()
        from agent_toolbelt_transactional_cleanup import filesystem
        original = filesystem.delete_exact
        created = self.repo / 'concurrent.txt'
        injected = False
        def inject(item, dry_run=False):
            nonlocal injected
            if not injected:
                created.write_text('new concurrent data')
                injected = True
            return original(item, dry_run=dry_run)
        with patch.object(filesystem, 'delete_exact', side_effect=inject):
            result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'partially_applied')
        retry = self.engine.apply(ticket)
        self.assertEqual(retry['ticket_state'], 'partially_applied')
        self.assertEqual(created.read_text(), 'new concurrent data')
        created.unlink()
        self.assertEqual(self.engine.apply(ticket)['ticket_state'], 'applied')

    def test_verified_upstream_tag_history_is_reproducible(self):
        self.git(self.repo, 'checkout', '--detach')
        (self.repo / 'source.txt').write_text('upstream release\n')
        self.git(self.repo, 'add', '.')
        self.git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'release')
        self.git(self.repo, 'tag', 'public-release')
        self.git(self.repo, 'push', 'origin', 'public-release')
        self.git(self.repo, 'checkout', '-')
        self.register()

    def test_recursive_generated_submodule_checks_preserve_local_changes(self):
        self.git(self.repo, '-c', 'protocol.file.allow=always', 'submodule', 'add', str(self.origin), 'vendor/child')
        # Local submodule clones hard-link loose objects by default. Match the
        # independent object storage of the real HTTPS-generated downloads.
        self.git(self.repo / 'vendor/child', 'repack', '-a', '-d')
        self.git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'public dependency pointer')
        new_pin = self.git(self.repo, 'rev-parse', 'HEAD').strip()
        self.git(self.repo, 'push', 'origin', 'HEAD')
        self.record['pin'] = new_pin
        self.recipe.write_text(self.recipe.read_text().replace(self.head, new_pin))
        self.git(self.repo, 'config', 'submodule.vendor/child.ignore', 'all')
        ticket = self.ticket()
        child = self.repo / 'vendor/child/source.txt'
        child.write_text('preserve submodule work\n')
        with self.assertRaises(RetirementError): self.engine.apply(ticket)
        self.assertTrue(child.exists())
        child.write_text('original source\n')
        result = self.engine.apply(ticket)
        self.assertEqual(result['ticket_state'], 'applied', result)

    def test_custom_git_configuration_and_hooks_are_preserved(self):
        hook = self.repo / '.git/hooks/pre-commit'
        hook.write_text('custom local hook')
        with self.assertRaises(RetirementError): self.register()
        hook.unlink()
        self.git(self.repo, 'config', 'user.name', 'Local private identity')
        with self.assertRaises(RetirementError): self.register()


if __name__ == '__main__': unittest.main()
