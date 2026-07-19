# Windows prerequisites

## Choose the family first

- `families/antigravity`: helper-owned CLIProxyAPI runtime installed with `agent-toolbelt-antigravity update`, plus explicit Antigravity OAuth login
- `families/everything`: `es.exe` available on `PATH`
- `families/media`: `yt-dlp`, `ffmpeg`, and `ffprobe` available on `PATH`
- `families/outlook-classic-mail`: Outlook Classic installed and configured locally, `uv` available on `PATH`, and a local Outlook COM client project
- `families/amazon-cli`: `uv` available on `PATH`; the Amazon CLI client source is bundled, while browser/session runtime state remains under local app data
- `families/skroutz-cli`: `uv` available on `PATH`; the Skroutz CLI client source is bundled, while optional browser/session runtime state remains under local app data
- `families/aliexpress-cli`: `uv` available on `PATH`; the AliExpress CLI client source is bundled, while optional browser/session runtime state remains under local app data
- `families/linkedin-cv`: `uv` available on `PATH`; Playwright dependencies are resolved by the package, while managed browser profiles, sessions, and snapshots remain under local app data

## Shared resolution order

For external binaries, the family packages prefer:

1. explicit CLI path override when supported
2. tool-specific environment override
3. `PATH`

On Windows, binary families keep `%LOCALAPPDATA%\Tools` as a final compatibility fallback for older local installs. Do not treat it as required when that directory is already on `PATH`.

Project-style clients such as Outlook, WhatsApp, Amazon, Skroutz, and AliExpress need a project root for `uv run --project` or editable execution. Use the documented environment override or `--client-home` when the default project root is not suitable.

## Suggested environment overrides

- `AGENT_TOOLBELT_ES`
- `AGENT_TOOLBELT_YTDLP`
- `AGENT_TOOLBELT_FFMPEG`
- `AGENT_TOOLBELT_FFPROBE`

## Antigravity notes

- The Antigravity family downloads a versioned Windows AMD64 CLIProxyAPI release under `%LOCALAPPDATA%\Tools\antigravity-review` and verifies the GitHub-provided SHA-256 digest.
- Run `update --check`, then `update` when setup or refresh is needed. Run `login` interactively and never terminate an active OAuth flow.
- `models` and `review` use a helper-owned ephemeral loopback process. They never reuse or modify Claude's CLIProxyAPI binary, auth, configuration, process, or port `8317`.
- Use `yt-dlp-ffmpeg` for public-video evidence preparation. Antigravity accepts only an explicitly named packet file for independent review.

## Amazon notes

- The Amazon family runs the bundled `amazon-intent-cli` project with `uv run --project`.
- `AMAZON_INTENT_CLI_HOME` or `--client-home` can point at another checkout.
- Managed browser sessions, browser profiles, cookies, caches, and account state are runtime data and are not included in this repo.

## Shopping CLI notes

- Skroutz and AliExpress follow the same package-backed pattern as Amazon.
- `SKROUTZ_INTENT_CLI_HOME` and `ALIEXPRESS_INTENT_CLI_HOME` can point at alternate client checkouts.
- AliExpress supports read-only `--use-session` commands after explicit managed login; cart and checkout workflows are intentionally absent.
