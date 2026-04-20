# Windows prerequisites

## Required tools by feature

- Gemini features: Node.js plus authenticated access for `@google/gemini-cli`
- Everything lookup: `es.exe` available on `PATH` or under `%LOCALAPPDATA%\Tools`
- `uvrun`: `uv` available on `PATH`
- Media helpers: `yt-dlp`, `ffmpeg`, and `ffprobe` available on `PATH` or under `%LOCALAPPDATA%\Tools`

## Resolution order

For external binaries, the package prefers:

1. explicit CLI path override when supported
2. tool-specific environment override
3. `PATH`
4. `%LOCALAPPDATA%\Tools`

## Suggested environment overrides

- `AGENT_TOOLBELT_ES`
- `AGENT_TOOLBELT_YTDLP`
- `AGENT_TOOLBELT_FFMPEG`
- `AGENT_TOOLBELT_FFPROBE`

## Gemini notes

- The package calls `npx @google/gemini-cli` in headless JSON mode.
- Authenticate Gemini CLI before using the Gemini commands.
- URL inspection is public-web only.
- The research companion is still helper-only and does not replace direct source checking.
