# Antigravity Review Helper Design

## Purpose

Replace the retired individual-tier `gemini-cli` skill with a bounded
`antigravity-cli` skill backed by a package helper. The helper uses
CLIProxyAPI only as a private, short-lived protocol adapter so agents receive
structured JSON without receiving a general-purpose local model proxy.

The helper is reviewer-first. It accepts an explicit packet file and exact
model, sends no tools, verifies the returned model, and fails closed on model
fallback or missing attribution.

## Non-Interference Contract

Claude CLI already uses a separately installed CLIProxyAPI instance. The new
helper must never mutate or control that instance.

The following resources are off-limits:

- `%LOCALAPPDATA%\Programs\CLIProxyAPI`
- `%USERPROFILE%\.cli-proxy-api`
- `127.0.0.1:8317`
- any process not started by the current helper invocation
- Claude settings, model aliases, API keys, logs, and OAuth records

The helper owns only:

- `%LOCALAPPDATA%\Tools\antigravity-review\releases`
- `%LOCALAPPDATA%\Tools\antigravity-review\state`
- `%LOCALAPPDATA%\Tools\antigravity-review\auth`
- per-invocation temporary configurations and processes

Every service invocation uses a dynamically selected loopback port and a
random per-run API key. The helper stops only the PID it created. There is no
Windows service, scheduled task, startup entry, resident daemon, or shared
configuration.

## Public Interface

Package and skill names:

- family: `families/antigravity`
- package: `agent-toolbelt-antigravity`
- executable: `agent-toolbelt-antigravity`
- public skill: `antigravity-cli`

Commands:

```powershell
agent-toolbelt-antigravity status
agent-toolbelt-antigravity update [--check] [--version <version>]
agent-toolbelt-antigravity login [--no-browser]
agent-toolbelt-antigravity models
agent-toolbelt-antigravity review --packet <path> --instruction <text> --model <exact-model>
```

All commands emit one JSON document. `login` is the only command that may open
a browser and runs interactively in the foreground until CLIProxyAPI completes
OAuth. Agents must never terminate an active login process.

## Runtime Installation And Update

`update` queries the official GitHub release API for
`router-for-me/CLIProxyAPI`, selects the Windows AMD64 asset, and installs it
under a versioned helper-owned release directory.

The update flow:

1. Resolve the requested or latest non-prerelease version.
2. Download the release ZIP to a helper-owned staging directory.
3. Compute SHA-256 and reject malformed or path-traversing archives.
4. Extract `cli-proxy-api.exe` into `releases/<version>`.
5. Run `-help` and require its reported version to match the release.
6. Write a release manifest containing version, source URL, asset name, size,
   SHA-256, and installation timestamp.
7. Atomically replace `state/current.json` with the new helper release path.
8. Retain only the active and immediately previous helper releases.

`update --check` is read-only and reports whether a newer release exists.
Neither mode reads, replaces, stops, or restarts Claude's CLIProxyAPI binary.

## Locked-Down Proxy Configuration

Each `models` or `review` invocation writes a temporary configuration with:

- `host: 127.0.0.1`
- a dynamically selected unused port
- helper-owned `auth-dir`
- a random API key
- management API and control panel disabled
- plugins disabled
- file logging, debug logging, and usage statistics disabled
- request retries disabled
- maximum retry credentials set to one
- project switching, preview-model switching, and credit fallback disabled
- deterministic fill-first routing

The process is started without a visible console window on Windows. Readiness
checks are monitoring heartbeats, not cancellation timeouts. If the child exits
before readiness, the command returns a structured startup failure.

## Review Contract

`review` reads one explicit packet file and combines it with the explicit
instruction. It does not crawl the workspace, fetch URLs, expose filesystem
tools, or send shell tools.

The request uses an OpenAI-compatible non-streaming endpoint with no `tools`
field. The normalized result includes:

- `ok`, `operation`, `invocation_id`
- `packet_path`, `packet_sha256`
- `model_requested`, `model_reported`, `model_verified`
- `response`, `usage`
- `proxy_version`, `proxy_pid`, `proxy_port`
- `warnings`, `errors`, and `failure_kind`
- `claude_proxy_detected` and `claude_proxy_untouched`

Success requires an exact reported-model match. Missing model attribution or a
different model returns `model_attribution_missing` or `model_mismatch` and a
non-zero exit code even if response text exists.

## Command Behavior

### `status`

Reports the active helper release, auth-file count without names or contents,
helper-owned process state, and separately detected Claude proxy metadata. It
does not start a process or refresh OAuth.

### `login`

Runs the helper-owned binary with `-antigravity-login` and the helper-owned
configuration. It is foreground and unbounded. It may open the user's browser
unless `--no-browser` is passed. It never copies credentials from Antigravity,
Gemini CLI, Claude, or the existing CLIProxyAPI installation.

### `models`

Starts an ephemeral helper proxy, calls `/v1/models`, returns the model catalog,
and stops the owned process.

### `review`

Starts an ephemeral helper proxy, performs one exact-model request, validates
model attribution, returns normalized JSON, and stops the owned process.

### `update`

Installs or checks a helper-owned CLIProxyAPI release without changing the live
Claude proxy.

## Repository Migration

The `families/gemini` public package and `gemini-cli` skill are replaced by
`families/antigravity` and `antigravity-cli`. Documentation must route public
video evidence preparation to `yt-dlp-ffmpeg` and independent packet review to
`antigravity-cli`.

Amazon's private intent resolver remains unchanged in this phase because it is
vendored inside the Amazon family and requires a separate behavior migration.
The backlog must record that remaining dependency rather than silently claiming
all Gemini CLI use has been removed.

## Safety And Privacy

- No credentials, API keys, packet content, or response content are committed.
- Auth files are treated as passwords and never listed by name in JSON output.
- No model fallback, project switching, account pooling, or automatic retry.
- No general-purpose proxy command is exposed by the skill.
- No background persistence or visible console popup for non-login commands.
- The helper never sends a packet unless the user or agent explicitly names it.

## Acceptance Criteria

1. Unit tests prove runtime paths cannot overlap the Claude installation,
   credential directory, or port.
2. `update --check` is read-only; `update` installs and activates only a
   helper-owned versioned release.
3. `status` detects the existing Claude proxy without modifying it.
4. `login` uses the helper config and does not impose a timeout.
5. `review` sends no tools and rejects missing or mismatched model attribution.
6. Owned proxy processes are hidden, bounded to loopback, and cleaned up by PID.
7. Codex and Claude skill bundles describe exact-model review and the explicit
   login boundary.
8. Root package, isolation, layout, and skills.sh validation remain green with
   the public skill count unchanged.
9. The installed local skill resolves its repo-backed wrapper successfully.
10. GitHub is synchronized and the final local branch tracks clean
    `origin/main`.
