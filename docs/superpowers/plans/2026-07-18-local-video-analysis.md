# Local Video Analysis Preparation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a transcript-first, optionally multimodal `prepare-analysis` operation to `yt-dlp-ffmpeg` and replace its stale Gemini routing.

**Architecture:** Extend the existing media family rather than adding another package. The orchestrator will reuse public URL validation and binary resolution, acquire subtitle and bounded media artifacts with `yt-dlp`, create clean transcripts and manifests with the standard library, and extract bounded frames/audio with `ffmpeg`.

**Tech Stack:** Python standard library, `yt-dlp`, `ffmpeg`, `unittest`, existing agent-toolbelt wrapper/bootstrap code.

---

### Task 1: Specify the operation through failing tests

**Files:**
- Modify: `families/media/tests/test_media.py`
- Modify: `tests/test_family_clis.py`
- Modify: `tests/test_monorepo_layout.py`

- [ ] Add tests for VTT cleanup and transcript-first preparation without media download.
- [ ] Add tests proving `--include-visuals` uses a height-capped format and bounded interval/scene frame commands.
- [ ] Add tests proving `--include-audio` reports a prepared audio artifact.
- [ ] Add CLI routing and skill-text assertions for `prepare-analysis` and removal of Gemini routing.
- [ ] Run `python -m unittest discover -s families/media/tests -p "test_*.py"` and verify failures are caused by the missing operation.

### Task 2: Implement preparation and manifest generation

**Files:**
- Modify: `families/media/src/agent_toolbelt_media/media.py`
- Modify: `families/media/src/agent_toolbelt_media/cli.py`
- Modify: `families/media/codex/skills/yt-dlp-ffmpeg/scripts/invoke_media_tool.py`
- Modify: `families/media/claude/marketplaces/agent-toolbelt-local/plugins/yt-dlp-ffmpeg/skills/yt-dlp-ffmpeg/scripts/invoke_media_tool.py`

- [ ] Add focused helpers for safe artifact naming, VTT cleanup, artifact classification, manifest writing, and bounded frame extraction.
- [ ] Add `invoke_prepare_analysis(...)` with subtitle-first orchestration and explicit visual/audio lanes.
- [ ] Add parser flags and route them consistently through package and installed-skill wrappers.
- [ ] Run the focused tests and make the minimal implementation pass.

### Task 3: Update public instructions and validation

**Files:**
- Modify: `families/media/README.md`
- Modify: `families/media/codex/skills/yt-dlp-ffmpeg/SKILL.md`
- Modify: `families/media/claude/marketplaces/agent-toolbelt-local/plugins/yt-dlp-ffmpeg/skills/yt-dlp-ffmpeg/SKILL.md`
- Modify: `README.md`
- Modify: `docs/skills-sh.md`

- [ ] Document transcript-first routing and when to request visual/audio evidence.
- [ ] State that Codex analyzes the manifest and artifacts; the helper is model-free.
- [ ] Remove instructions that defer public-video understanding to `gemini-cli`.
- [ ] Run family, root wiring, and skills.sh validation suites.

### Task 4: Publish and refresh the installed skill

**Files:**
- Refresh after merge: `C:/Users/darka/.codex/skills/yt-dlp-ffmpeg`

- [ ] Inspect the final diff and confirm only media-analysis scope is present.
- [ ] Commit, push, open and merge the GitHub PR.
- [ ] Fast-forward local `main` to `origin/main` and remove the remote feature branch.
- [ ] Refresh the installed Codex skill from the merged canonical bundle.
- [ ] Confirm the repository is clean and the installed skill advertises `prepare-analysis`.
