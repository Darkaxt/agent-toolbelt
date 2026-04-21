# Windows prerequisites

## Choose the family first

- `families/gemini`: Node.js plus authenticated access for `@google/gemini-cli`
- `families/everything`: `es.exe` available on `PATH` or under `%LOCALAPPDATA%\Tools`
- `families/uvrun`: `uv` available on `PATH`, plus `uvrun.ps1` or deprecated `uvrun.bat`
- `families/media`: `yt-dlp`, `ffmpeg`, and `ffprobe` available on `PATH` or under `%LOCALAPPDATA%\Tools`
- `families/outlook-classic-mail`: Outlook Classic installed and configured locally, `uv` available on `PATH`, and the local client project under `%LOCALAPPDATA%\Tools\outlook-classic-mail`
- `families/whatsapp-local-read`: WhatsApp Desktop installed locally, `uv` available on `PATH`, and the read-only local client project under `%LOCALAPPDATA%\Tools\whatsapp-local-read`

## Shared resolution order

For external binaries, the family packages prefer:

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

- The Gemini family calls `npx @google/gemini-cli` in headless JSON mode.
- Authenticate Gemini CLI before using the Gemini family commands.
- URL inspection stays public-web only.
- The research companion remains Codex-only in v1.

## WhatsApp notes

- The WhatsApp family is read-only and personal-desktop scoped.
- Local database probing is limited to file discovery, size, and magic-byte checks; encrypted or non-SQLite stores are reported as unsupported.
- Conversation content comes from text already visible in WhatsApp Desktop, so summaries and response suggestions should always state that limited scope.
