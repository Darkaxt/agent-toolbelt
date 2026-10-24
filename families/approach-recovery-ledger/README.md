# Approach Recovery Ledger

Version 0.1.1: shared, dated approach and cybersecurity rejection history for recovered threads and subsequent
planning. The thread records its own actual execution plan after recovery.
The helper does not detect blocks, recover a thread, retry requests or decide
what is permitted.

`references/rejections.md` defines the rejection-register use of the same private
database. ReCodex Policy Diagnostics can attach local analysis as evidence;
backend rejection causes remain separate and unknown when not established.

The canonical self-contained bundle is
`codex/skills/approach-recovery-ledger`. It works with Codex or Claude and needs
Python 3.11+ only. Share the whole folder; start with its `SKILL.md` and
`references/integration.md`. This first version is not installed automatically.

Records stay outside the bundle and Git. On Windows the default is
`E:/Codex/ledgers/approach-recovery/ledger.sqlite3`. Other hosts use
`~/.local/share/agent-toolbelt/approach-recovery/ledger.sqlite3`.
`APPROACH_RECOVERY_LEDGER` or global `--ledger <path>` selects the shared file.
All participants on one host must use the same path. This is a local SQLite
ledger, not a network-share service or a cross-machine synchronization system.

```powershell
$helper = 'families/approach-recovery-ledger/codex/skills/approach-recovery-ledger/scripts/invoke_approach_recovery_ledger.py'
python -B $helper status
python -B $helper search --query 'parser reference' --limit 10
python -B $helper record --input <private-attempt.json>
python -B $helper show --attempt-id <stable-id>
python -B $helper context --input <scoped-metadata.json> --source codex_turn_context
```

See `references/entry.md` for the entry contract and the fictional example under
`examples/attempt.json`. Never use that example as evidence for a real attempt.
Helper validation verifies structure and bookkeeping, not the truth of a plan,
evidence reference, safety assessment or claimed verification.

```powershell
python -B -m unittest tests.test_approach_recovery_ledger
```
