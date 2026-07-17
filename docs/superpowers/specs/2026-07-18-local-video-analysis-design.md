# Local Video Analysis Preparation Design

## Context

The `yt-dlp-ffmpeg` skill currently routes YouTube understanding to
`gemini-cli`. That route is no longer available on this machine, while the
media family already provides public URL validation, metadata discovery,
downloads, probing, and FFmpeg transforms.

## Decision

Add a model-free `prepare-analysis` command to the existing media family. It
will prepare bounded local evidence for Codex instead of trying to summarize a
video itself or creating a second overlapping skill.

The default path is transcript-first:

1. Validate the public URL and fetch single-item metadata.
2. Request human or automatic subtitles without downloading the media.
3. Produce a cleaned plain-text transcript when VTT subtitles are available.
4. Write an `analysis-manifest.json` describing evidence and missing lanes.

Visual and audio acquisition are explicit:

- `--include-visuals` downloads a bounded-height video and extracts interval
  and scene-change JPEG frames with configurable caps.
- `--include-audio` extracts an MP3 from the prepared video or performs a
  bounded audio-only acquisition when no video was requested.

## Interface

```text
prepare-analysis --url <public-url> [--output-dir <dir>]
  [--subtitle-langs <selector>] [--include-visuals] [--include-audio]
  [--max-height <pixels>] [--frame-interval-sec <seconds>]
  [--max-frames <count>]
```

The normalized result keeps the media family envelope and adds manifest
metadata:

- `ok`, `tool`, `operation`, `exit_code`, `stderr`, `artifacts`, `metadata`
- `metadata.analysis_ready`
- `metadata.analysis_dir`
- `metadata.source`
- `metadata.evidence` grouped into subtitles, transcript, media, audio,
  interval frames, scene frames, and manifest
- `metadata.warnings`
- `metadata.recommended_next_steps`

Partial evidence is not hidden. Metadata-only preparation succeeds but reports
that transcript or visual evidence is missing. Explicitly requested visual or
audio lanes fail the operation when they cannot be produced.

## Boundaries

- Public `http(s)` media only; no cookies, browser profiles, private targets,
  access-control bypass, playlists, or background crawling.
- Single-threaded subprocess execution.
- No embedded speech model, model API, or automatic summary.
- No full-resolution default download. The visual format is capped by height.
- Existing media commands and JSON fields remain compatible.

## Verification

Unit tests will prove transcript cleaning, subtitle-first execution, explicit
visual/audio routing, bounded FFmpeg frame commands, partial diagnostics, and
CLI forwarding. Skill and README tests will reject the stale Gemini routing
and document the new local workflow.
