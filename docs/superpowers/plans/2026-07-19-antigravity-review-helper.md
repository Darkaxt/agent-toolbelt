# Antigravity Review Helper Implementation Plan

> **Execution mode:** inline staged implementation with TDD and a verification
> checkpoint after every stage.

**Goal:** Replace the retired Gemini public skill with a deterministic,
exact-model Antigravity review helper backed by an isolated ephemeral
CLIProxyAPI runtime, including a safe `update` command.

**Architecture:** A stdlib-only Python package manages a helper-owned versioned
CLIProxyAPI installation. Login runs in the foreground. Models and review start
an isolated loopback process using a temporary locked-down configuration and
stop only that owned PID. Repository skill bundles expose bounded commands and
never expose a general proxy.

**Technology:** Python 3.11+, stdlib `argparse`, `urllib`, `subprocess`, `zipfile`,
`hashlib`, `socket`, `secrets`, `json`, and `unittest`.

---

## Stage 1: Package Scaffold And Isolation Contract

**Files:**

- Create `families/antigravity/pyproject.toml`
- Create `families/antigravity/src/agent_toolbelt_antigravity/__init__.py`
- Create `families/antigravity/src/agent_toolbelt_antigravity/runtime.py`
- Create `families/antigravity/src/agent_toolbelt_antigravity/cli.py`
- Create `families/antigravity/tests/test_antigravity.py`

**TDD sequence:**

1. Add tests for helper-owned paths, forbidden Claude paths, dynamic ports, and
   non-overlap assertions.
2. Run `python -m unittest discover -s families/antigravity/tests -p "test_*.py"`
   and confirm import/behavior failures.
3. Implement runtime path resolution and `status` normalization.
4. Re-run the focused suite and commit the stage.

## Stage 2: Versioned Runtime And `update`

**Files:**

- Modify `families/antigravity/src/agent_toolbelt_antigravity/runtime.py`
- Modify `families/antigravity/src/agent_toolbelt_antigravity/cli.py`
- Modify `families/antigravity/tests/test_antigravity.py`

**TDD sequence:**

1. Add fixtures for GitHub releases, Windows asset selection, ZIP traversal,
   reported-version mismatch, check-only behavior, atomic activation, and
   retention of active plus previous releases.
2. Confirm the new tests fail for missing update behavior.
3. Implement release lookup, download, hash/ZIP validation, version probe,
   manifest write, atomic activation, and helper-only cleanup.
4. Re-run the focused suite and commit the stage.

## Stage 3: Login, Models, And Exact-Model Review

**Files:**

- Create `families/antigravity/src/agent_toolbelt_antigravity/proxy.py`
- Modify `families/antigravity/src/agent_toolbelt_antigravity/cli.py`
- Modify `families/antigravity/tests/test_antigravity.py`

**TDD sequence:**

1. Add tests for locked-down YAML, hidden-process startup flags, foreground
   login, no tools in review payloads, packet hashing, model equality, missing
   attribution, model mismatch, and owned-PID cleanup.
2. Confirm the new tests fail.
3. Implement configuration generation, foreground login, ephemeral service
   lifecycle, models request, review request, and normalized failures.
4. Re-run the focused suite and commit the stage.

## Stage 4: Skill Bundles And Repository Migration

**Files:**

- Create `families/antigravity/README.md`
- Create Codex and Claude `antigravity-cli` skill bundles and wrappers
- Delete `families/gemini`
- Modify root workspace, tests, README, install docs, skills.sh docs,
  alternatives, prerequisites, backlog, and validator

**TDD sequence:**

1. Update root tests first to expect `antigravity` instead of `gemini` and add
   docs/skill assertions.
2. Confirm root tests fail while the old family remains.
3. Add bundles/wrappers, remove Gemini, and update all active documentation.
4. Run family tests, root wiring tests, skill validator, and skills.sh validator.
5. Commit and push the stage.

## Stage 5: Local Runtime And Publish Verification

1. Run `agent-toolbelt-antigravity status` and verify it reports the existing
   Claude proxy as detected and untouched.
2. Run `update --check`, then `update`, and verify the helper installs under its
   own release root while Claude remains PID/port/path stable.
3. Run `models` only if helper-owned Antigravity auth already exists; otherwise
   leave login as the explicit user-interactive next action and verify the
   structured `auth_unavailable` path.
4. Install/refresh the Codex and Claude skill bundles from the merged source.
5. Push the branch, merge through GitHub, fast-forward local `main`, and rerun
   focused/root validation.
6. Confirm `git status --short --branch` is clean and `main...origin/main` is
   `0 0`.

## Self-Review

- Specification coverage: every public command, safety invariant, model gate,
  update behavior, repository migration, local installation, and GitHub sync
  has a corresponding stage.
- Placeholder scan: no TBD/TODO or deferred implementation placeholders.
- Naming consistency: family `antigravity`, package
  `agent_toolbelt_antigravity`, executable `agent-toolbelt-antigravity`, skill
  `antigravity-cli`.
- Intent preservation: CLIProxyAPI is an internal adapter only; Claude's live
  proxy remains untouched and exact model selection fails closed.
