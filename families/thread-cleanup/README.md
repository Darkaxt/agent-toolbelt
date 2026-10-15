# Thread Cleanup

Permanent exact-chat retirement, distinct from recoverable context transfer.
The canonical Codex/Claude bundle is `codex/skills/thread-cleanup`.

The helper uses Codex's supported `thread/delete` API and verifies database and
rollout residuals. Claude session artifacts and matching index rows use explicit
review/hash gates, live process checks and installed exact-handle file deletion.
No direct chat/history SQL, full-profile deletion or forced process
shutdown. Database row deletion is not necessarily physical file shrinkage.
A verified-orphan queue-revision adapter addresses a tested app deletion omission,
under an immediate SQLite transaction after the selected thread/content is gone.

Read SKILL.md before invoking the helper. Runtime requirements: Windows,
Python 3.11+, installed Codex executable and installed transactional-cleanup
filesystem runtime. Private plan/evidence files stay outside published bundles.

Focused verification: `python -B -m unittest tests.test_thread_cleanup`.
