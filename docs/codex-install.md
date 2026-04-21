# Codex install guide

Each family ships its own Codex skill bundle. Install only the family you want.

## Skill locations

- Gemini: `families/gemini/codex/skills/gemini-cli`
- Everything: `families/everything/codex/skills/everything-search`
- UVRun: `families/uvrun/codex/skills/uvrun-python`
- Media: `families/media/codex/skills/yt-dlp-ffmpeg`

## Install flow

1. Open the family README you want.
2. Copy that family skill folder into your Codex home skills directory.
3. Keep the clone intact so the wrapper scripts can bootstrap the matching family package plus `packages/core`.
