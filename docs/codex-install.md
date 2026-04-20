# Codex integration install

## Option 1: use the package only

Install the package from a clone:

```bash
pip install -e .
```

Then call `agent-toolbelt` directly from your local workflow.

## Option 2: install the Codex skills from this repo

The Codex-ready skill bundles live under `integrations/codex/skills/`.

Copy the desired skill folders into your Codex home skills directory:

- `gemini-cli`
- `everything-search`
- `uvrun-python`
- `yt-dlp-ffmpeg`

Each bundled wrapper script bootstraps the local `src/` tree from the clone, so the skill can run directly from the repository checkout.

## Skill notes

- `gemini-cli` includes both URL inspection and the research companion lane.
- `everything-search` stays filename/path-only and does not replace `rg` for content search.
- `uvrun-python` keeps project-managed Python workflows out of scope.
- `yt-dlp-ffmpeg` handles acquisition and file-level media operations, not YouTube summarization.
