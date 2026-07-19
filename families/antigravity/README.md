# Antigravity Review Helper

`agent-toolbelt-antigravity` provides bounded, exact-model packet and public
evidence analysis through a helper-owned CLIProxyAPI runtime and Antigravity
OAuth. It replaces the retired `gemini-cli` skill without exposing a general
model proxy or model-side browsing tools.

## Commands

```powershell
agent-toolbelt-antigravity status
agent-toolbelt-antigravity update --check
agent-toolbelt-antigravity update
agent-toolbelt-antigravity login
agent-toolbelt-antigravity models
agent-toolbelt-antigravity review --packet C:\path\review-packet.md --instruction "Review this plan for requirement drift." --model <exact-model-id>
agent-toolbelt-antigravity analyze-url --url https://example.com/article --instruction "Summarize the evidence." --model <exact-model-id>
agent-toolbelt-antigravity analyze-video --manifest C:\path\analysis-manifest.json --instruction "Analyze the transcript and frames." --model <exact-model-id>
```

`review` reads only the explicit UTF-8 packet file, sends no tools, and succeeds
only when the response reports the exact requested model. Use `models` to find
the exact model id after login.

`analyze-url` validates DNS and redirect targets, rejects local/private
destinations, extracts bounded HTML/text, labels it as untrusted evidence, and
then uses the same exact-model contract. YouTube URLs must first be prepared
with `yt-dlp-ffmpeg prepare-analysis`; `analyze-video` reads the explicit
manifest, bounded transcript, and up to eight prepared frame images. It never
uploads the downloaded media or audio file automatically.

## Runtime Isolation

The helper owns `%LOCALAPPDATA%\Tools\antigravity-review`. It downloads and
verifies a versioned CLIProxyAPI release, keeps OAuth under its own auth root,
uses a random loopback port and API key for each request, starts no persistent
service, and stops only the process it created.

The helper never reads, modifies, restarts, or reuses Claude's CLIProxyAPI
installation, auth directory, process, configuration, or port `8317`.

`login` is the only interactive command. It runs visibly in the foreground,
has no cancellation timeout, and must not be killed while OAuth is active.

## Update Safety

`update --check` is read-only. `update` downloads the official Windows AMD64
release from `router-for-me/CLIProxyAPI`, verifies the GitHub-provided SHA-256
digest, rejects unsafe ZIP paths, verifies the binary-reported version, and
atomically activates the helper-owned release. Release assets are not
Authenticode-signed, so the manifest records the verified archive digest.
