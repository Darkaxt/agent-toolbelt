# ADB Archive Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, test, document, install, and publish a manifest-driven ADB transfer helper that packs only tiny files into uncompressed TAR bundles and verifies one explicitly selected endpoint and destination.

**Architecture:** Add a self-contained `families/adb-archive-transfer` Python package. Keep pure source classification, identity, path-safety, and manifest logic separate from the subprocess-backed ADB/7-Zip executor so tests can prove the protocol without mutating a device. Package-backed Codex and Claude wrappers invoke the same CLI.

**Tech Stack:** Python 3.11+, standard library, Android SDK `adb`, Windows 7-Zip/NanaZip command alias, `unittest`, agent-toolbelt workspace bootstrap.

---

### Task 1: Family contract and root wiring

**Files:**
- Create: `families/adb-archive-transfer/pyproject.toml`
- Create: `families/adb-archive-transfer/README.md`
- Create: `families/adb-archive-transfer/src/agent_toolbelt_adb_archive_transfer/__init__.py`
- Create: `families/adb-archive-transfer/src/agent_toolbelt_adb_archive_transfer/cli.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_monorepo_layout.py`
- Modify: `tests/test_family_isolation.py`
- Modify: `tests/test_family_clis.py`

- [ ] Write root tests that expect the new family, package, script, and CLI import.
- [ ] Run the root tests and confirm they fail because the family does not exist.
- [ ] Add the package shell, workspace member, and CLI routing.
- [ ] Run the root tests and confirm the new family imports without unrelated-family references.
- [ ] Commit the family shell.

### Task 2: Pure planning and manifest behavior

**Files:**
- Create: `families/adb-archive-transfer/src/agent_toolbelt_adb_archive_transfer/transfer.py`
- Create: `families/adb-archive-transfer/tests/test_adb_archive_transfer.py`

- [ ] Write tests for 64 MiB tiny classification, medium direct transfer, mandatory direct transfer at 1 GiB, a single tiny file remaining direct, deterministic 4 GiB bundle partitioning, symlink rejection, relative-path collision rejection, and source snapshot hashing.
- [ ] Run the family tests and confirm missing planning functions fail.
- [ ] Implement exact file enumeration, hashing, classification, and canonical manifest serialization.
- [ ] Run the family tests and confirm the pure planning cases pass.
- [ ] Commit planning behavior.

### Task 3: Endpoint selection and destination preflight

**Files:**
- Modify: `families/adb-archive-transfer/src/agent_toolbelt_adb_archive_transfer/transfer.py`
- Modify: `families/adb-archive-transfer/tests/test_adb_archive_transfer.py`

- [ ] Write tests for parsing `adb devices -l`, zero/one/multiple ready endpoints, explicit serial selection, stable identity hashing, transport-id exclusion, protected destination rejection, exact `-s` command construction, capability detection, and free-space parsing.
- [ ] Run the family tests and confirm the endpoint tests fail.
- [ ] Implement subprocess-runner injection, endpoint inventory, identity collection, path safety, destination checks, and capacity estimation without cancellation timeouts.
- [ ] Run the family tests and confirm endpoint/preflight cases pass.
- [ ] Commit endpoint binding.

### Task 4: Transactional apply and cleanup

**Files:**
- Modify: `families/adb-archive-transfer/src/agent_toolbelt_adb_archive_transfer/transfer.py`
- Modify: `families/adb-archive-transfer/src/agent_toolbelt_adb_archive_transfer/cli.py`
- Modify: `families/adb-archive-transfer/tests/test_adb_archive_transfer.py`

- [ ] Write tests proving no mutation without `--confirm-transfer`, source drift fails before ADB mutation, 7-Zip uses `-ttar` without compression switches, direct files bypass TAR, remote TAR hashes precede extraction, extraction uses `--restrict`, final placement follows complete hash verification, every ADB command uses `-s`, and cleanup is confined to manifest-owned staging.
- [ ] Run the family tests and confirm the execution tests fail.
- [ ] Implement `devices`, `plan`, `apply`, and `cleanup` command handlers and structured JSON results.
- [ ] Run the family tests and confirm the transactional protocol passes.
- [ ] Commit execution behavior.

### Task 5: Skill bundles and wrappers

**Files:**
- Create: `families/adb-archive-transfer/codex/skills/adb-archive-transfer/SKILL.md`
- Create: `families/adb-archive-transfer/codex/skills/adb-archive-transfer/agents/openai.yaml`
- Create: `families/adb-archive-transfer/codex/skills/adb-archive-transfer/scripts/invoke_adb_archive_transfer.py`
- Create: `families/adb-archive-transfer/claude/marketplaces/agent-toolbelt-local/plugins/adb-archive-transfer/skills/adb-archive-transfer/SKILL.md`
- Create: `families/adb-archive-transfer/claude/marketplaces/agent-toolbelt-local/plugins/adb-archive-transfer/skills/adb-archive-transfer/scripts/invoke_adb_archive_transfer.py`
- Modify: `families/adb-archive-transfer/tests/test_adb_archive_transfer.py`

- [ ] Write tests for skill routing, endpoint ambiguity, explicit confirmation, direct-large-file rules, uncompressed TAR rules, diagnostics, and installed-root wrapper bootstrap.
- [ ] Run the family tests and confirm skill/wrapper tests fail.
- [ ] Add concise skill instructions and package-backed wrappers.
- [ ] Validate both skill bundles and run wrapper help/status smoke checks.
- [ ] Commit skill bundles.

### Task 6: Repository documentation and validation

**Files:**
- Modify: `README.md`
- Modify: `docs/codex-install.md`
- Modify: `docs/claude-install.md`
- Modify: `scripts/validate_skills_sh.ps1`

- [ ] Add the family and skill to repository/install documentation and skills.sh validation.
- [ ] Run family tests, root wiring/isolation/layout tests, skill validators, and `scripts/validate_skills_sh.ps1`.
- [ ] Run a read-only live `devices` and `plan` dry smoke against the connected Thor using a disposable `D:\Temp` fixture; perform no `apply`.
- [ ] Remove the disposable fixture and generated caches.
- [ ] Commit documentation and validation.

### Task 7: Install and synchronize

**Files:**
- Install: `C:\Users\darka\.codex\skills\adb-archive-transfer`
- Install: `C:\Users\darka\.agents\skills\adb-archive-transfer`

- [ ] Copy the tested Codex and Claude bundles into their active roots without symlinks.
- [ ] Compare source/install SHA-256 values and validate installed skills.
- [ ] Push the focused branch, open a PR, wait for repository checks, merge, and fast-forward local `main`.
- [ ] Confirm `main` tracks `origin/main`, the worktree is clean, and no helper temp files remain.
