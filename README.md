# agent-toolbelt

`agent-toolbelt` packages a set of Windows-first local-agent utilities into one reusable Python package with Codex and Claude integration bundles.

## Included tool families

- Gemini public URL inspection plus a Codex-oriented research companion cross-check
- Everything-first filename and path lookup with safe fallbacks
- `uvrun` routing for standalone local Python scripts
- `yt-dlp`, `ffprobe`, and `ffmpeg` helpers for media acquisition and local file operations

## Quick start

Install from a clone:

```bash
pip install -e .
```

Primary CLI:

```bash
agent-toolbelt gemini-url --url "https://example.com" --instruction "Summarize this page."
agent-toolbelt gemini-research --question "Going Medieval issues"
agent-toolbelt everything --query "README.md"
agent-toolbelt uvrun scratch.py --check
agent-toolbelt media probe --input sample.mp4
```

## Repo layout

- `src/agent_toolbelt/`: reusable package and packaged helper assets
- `integrations/codex/`: Codex skill bundles backed by the package
- `integrations/claude/`: Claude marketplace and plugin bundles backed by the package
- `docs/`: prerequisites and install guides
- `tests/`: package, CLI, and portability coverage

## Installation guides

- [Windows prerequisites](docs/windows-prerequisites.md)
- [Codex integration install](docs/codex-install.md)
- [Claude integration install](docs/claude-install.md)

## Notes

- Third-party binaries are not vendored. Install `uv`, Everything CLI, Gemini CLI auth, `yt-dlp`, `ffmpeg`, and `ffprobe` separately.
- The Codex Gemini skill includes the research companion lane.
- The Claude Gemini plugin remains URL-focused in v1.
