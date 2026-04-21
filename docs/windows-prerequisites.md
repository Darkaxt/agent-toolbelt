# Windows prerequisites

## Choose the family first

- `families/gemini`: Node.js plus authenticated access for `@google/gemini-cli`
- `families/everything`: `es.exe` available on `PATH` or under `%LOCALAPPDATA%\Tools`
- `families/uvrun`: `uv` available on `PATH`, plus `uvrun.ps1` or deprecated `uvrun.bat`
- `families/media`: `yt-dlp`, `ffmpeg`, and `ffprobe` available on `PATH` or under `%LOCALAPPDATA%\Tools`
- `families/outlook-classic-mail`: Outlook Classic installed and configured locally, `uv` available on `PATH`, and the local client project under `%LOCALAPPDATA%\Tools\outlook-classic-mail`
- `families/amazon-cli`: `uv` available on `PATH`; the Amazon CLI client source is bundled, while browser/session runtime state remains under local app data

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

## Amazon notes

- The Amazon family runs the bundled `amazon-intent-cli` project with `uv run --project`.
- `AMAZON_INTENT_CLI_HOME` or `--client-home` can point at another checkout.
- Managed browser sessions, browser profiles, cookies, caches, and account state are runtime data and are not included in this repo.
