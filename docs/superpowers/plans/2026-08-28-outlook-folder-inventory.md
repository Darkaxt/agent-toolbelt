# Outlook Folder Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent normal Outlook helper operations from recursively enumerating and visibly materializing the complete mailbox folder hierarchy.

**Architecture:** Extend the existing SQLite `folder_state` table with stable folder EntryIDs, use `NameSpace.GetFolderFromID` for known custom folders, and reserve recursive hierarchy traversal for an explicit rediscovery flag. Add response diagnostics so callers can prove whether a command enumerated the hierarchy.

**Tech Stack:** Python 3.11+, pywin32 Outlook COM, SQLite, argparse, unittest.

---

### Task 1: Persist And Query Folder Identities

**Files:**
- Modify: `families/outlook-classic-mail/local-client/src/outlook_classic_mail_client/mail_cache.py`
- Test: `families/outlook-classic-mail/local-client/tests/test_mail_cache.py`

- [ ] **Step 1: Write failing cache migration and inventory tests**

Add tests that initialize the old schema, call `ensure_schema()`, persist a
folder record containing `folder_entry_id`, and query inventory rows by account
and folder-name/path text.

- [ ] **Step 2: Run the focused tests and verify missing-column/API failures**

Run: `uv run python -m unittest tests.test_mail_cache`

Expected: failures because `folder_entry_id`, `folder_inventory()`, and
`search_folder_inventory()` do not exist.

- [ ] **Step 3: Implement the additive migration and inventory APIs**

Add the column with an idempotent `PRAGMA table_info` migration. Extend
`update_folder_state()` and add bounded inventory read/search methods. Do not
delete or rebuild the existing cache.

- [ ] **Step 4: Run the focused tests**

Run: `uv run python -m unittest tests.test_mail_cache`

Expected: all cache tests pass.

### Task 2: Resolve Known Folders Without Hierarchy Enumeration

**Files:**
- Modify: `families/outlook-classic-mail/local-client/src/outlook_classic_mail_client/client.py`
- Test: `families/outlook-classic-mail/local-client/tests/test_client.py`

- [ ] **Step 1: Write failing non-enumeration tests**

Add fake-session tests where accessing `root.Folders` raises. Prove a warm cache
refresh resolves a custom folder with `GetFolderFromID`, default
`find-folders` returns cached matches, and stale identities return warnings
without traversing the root.

- [ ] **Step 2: Run the focused tests and verify they fail for recursive access**

Run: `uv run python -m unittest tests.test_client.OutlookClassicMailClientTests`

Expected: failures from missing inventory behavior or forbidden `Folders`
access.

- [ ] **Step 3: Implement direct folder resolution and diagnostics**

Add helpers that seed the four default folders, resolve cached custom folders
through `session.GetFolderFromID`, and return
`folder_hierarchy_enumerated=false`. Never silently discover on stale IDs.

- [ ] **Step 4: Run the focused tests**

Run: `uv run python -m unittest tests.test_client.OutlookClassicMailClientTests`

Expected: focused client tests pass.

### Task 3: Add Explicit Rediscovery

**Files:**
- Modify: `families/outlook-classic-mail/local-client/src/outlook_classic_mail_client/client.py`
- Modify: `families/outlook-classic-mail/src/agent_toolbelt_outlook_classic_mail/outlook_classic_mail.py`
- Test: `families/outlook-classic-mail/local-client/tests/test_client.py`
- Test: `families/outlook-classic-mail/tests/test_outlook_classic_mail.py`

- [ ] **Step 1: Write failing parser, forwarding, and rediscovery tests**

Cover `find-folders --rediscover-folders`,
`cache-refresh --rediscover-folders`, and
`sync-mail --refresh-cache --rediscover-folders`. Verify explicit discovery
persists EntryIDs and reports `folder_hierarchy_enumerated=true`.

- [ ] **Step 2: Run focused local and bridge tests**

Run: `uv run python -m unittest tests.test_client`

Run: `python -m unittest families.outlook-classic-mail.tests.test_outlook_classic_mail`

Expected: parser/forwarding tests fail before implementation.

- [ ] **Step 3: Implement flags and rediscovery data flow**

Wire one boolean from package wrapper to client commands. Reuse the existing
recursive iterator only inside the explicit rediscovery path.

- [ ] **Step 4: Re-run focused tests**

Expected: both suites pass.

### Task 4: Update Agent Guidance And Documentation

**Files:**
- Modify: `families/outlook-classic-mail/README.md`
- Modify: `families/outlook-classic-mail/local-client/README.md`
- Modify: `families/outlook-classic-mail/codex/skills/outlook-classic-mail/SKILL.md`
- Modify: `families/outlook-classic-mail/claude/marketplaces/agent-toolbelt-local/plugins/outlook-classic-mail/skills/outlook-classic-mail/SKILL.md`
- Test: `families/outlook-classic-mail/tests/test_outlook_classic_mail.py`

- [ ] **Step 1: Add failing documentation assertions**

Require cache-first folder lookup, explicit rediscovery, hierarchy diagnostics,
and a prohibition on routine recursive discovery.

- [ ] **Step 2: Update canonical documentation and both skill bundles**

Remove the instruction to run live `find-folders` first for ordinary searches.
Explain that rediscovery can affect visible Outlook folder expansion.

- [ ] **Step 3: Validate docs and skills**

Run the family suite and `quick_validate.py` for both skill directories.

Expected: all assertions and validators pass.

### Task 5: Full Verification, Deployment, And Sync

**Files:**
- Deploy tested local-client files under `%LOCALAPPDATA%\Tools\outlook-classic-mail`
- Deploy canonical skill files under `<codex-skill-root>` and `<agents-skill-root>`

- [ ] **Step 1: Run all relevant test suites**

Run local-client discovery, Outlook family tests, and root family/wiring tests.

- [ ] **Step 2: Review ignored artifacts and remove only generated caches**

Use `git clean -ndX -- families/outlook-classic-mail` first. Preserve reusable
virtual environments and local state; remove only verified generated caches.

- [ ] **Step 3: Deploy and hash-compare installed files**

Verify installed source and skill SHA-256 hashes match the canonical repository
files. Run an installed read-only `cache-status` smoke check.

- [ ] **Step 4: Commit and synchronize through protected main**

Push a focused branch, open a PR, wait for required checks, merge, fast-forward
local `main`, delete the topic branch, and confirm a clean
`main...origin/main` status.
