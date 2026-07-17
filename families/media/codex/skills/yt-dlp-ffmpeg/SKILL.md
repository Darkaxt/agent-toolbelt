---
name: yt-dlp-ffmpeg
description: Use `yt-dlp`, `ffprobe`, and `ffmpeg` for public video analysis preparation, media URL classification, metadata/format discovery, download, and local file-level operations.
license: MIT
metadata:
  compatibility: Requires yt-dlp, ffmpeg, and ffprobe. Intended for public media and local file operations only.
  version: "0.1.0"
---

# YT-DLP + FFmpeg

## Overview

Use `scripts/invoke_media_tool.py` for transcript-first public video analysis preparation, public URL download, and local file-level media work. The wrapper delegates into the media family package in this repo.

## Routing Rules

Use this skill when:

- The user wants to download media from a public `http(s)` URL.
- The user wants subtitles from a public media URL.
- The user wants to understand or summarize a public video using local evidence.
- The user wants media metadata, streams, duration, bitrate, or container details.
- The user needs to check whether a URL is safe public media input before downloading.
- The user needs available formats or playlist metadata before choosing a download.
- The user wants to clip a file, extract audio, remux, or transcode a local media file.
- The user explicitly names `yt-dlp`, `ffmpeg`, or `ffprobe`.

Do not use this skill when:

- The task is understanding a generic non-media public page.
- The source is authenticated, private-network, localhost, `.local`, or browser-cookie-based.
- The user asks to use cookies, browser-session extraction, or other access-control bypasses.
- The request is unrelated to media acquisition or file-level media operations.

## Behavior

- Use `prepare-analysis` for video understanding. It fetches metadata and
  subtitles first, writes a cleaned transcript plus `analysis-manifest.json`,
  and avoids downloading video unless `--include-visuals` is explicit.
- Read `metadata.evidence.transcript` first. Inspect interval and scene frames
  when visual context matters. Treat raw media as provenance, not as a reason
  to skip transcript/frame inspection.
- Add `--include-audio` when local transcription is needed. The helper prepares
  evidence only; it does not call a model or generate a summary.
- Prefer `classify-url`, `metadata`, or `formats` before `download` when source safety, playlist behavior, or format choice is unclear.
- `download` is single-item by default and uses `--playlist-mode single`; playlist downloads require explicit `--playlist-mode full`.
- Use `--playlist-items <selector>` only with `--playlist-mode full`.
- Treat structured JSON failures as authoritative; do not retry with cookies or authenticated browser state.

## Script Interface

```bash
python scripts/invoke_media_tool.py classify-url --url <public-url>
python scripts/invoke_media_tool.py metadata --url <public-url> [--playlist-mode single|flat|full]
python scripts/invoke_media_tool.py formats --url <public-url>
python scripts/invoke_media_tool.py prepare-analysis --url <public-video-url> [--output-dir <dir>]
python scripts/invoke_media_tool.py prepare-analysis --url <public-video-url> --include-visuals [--include-audio] [--max-height 480] [--frame-interval-sec 30] [--max-frames 24]
python scripts/invoke_media_tool.py download --url <public-url> [--output-dir <dir>] [--audio-only] [--subs] [--format <selector>]
python scripts/invoke_media_tool.py download --url <public-playlist-url> --playlist-mode full [--playlist-items <selector>]
python scripts/invoke_media_tool.py probe --input <file>
python scripts/invoke_media_tool.py clip --input <file> --start <time> --end <time> [--output <file>]
python scripts/invoke_media_tool.py extract-audio --input <file> [--codec <name>] [--output <file>]
python scripts/invoke_media_tool.py remux --input <file> --container <ext> [--output <file>]
python scripts/invoke_media_tool.py transcode --input <file> [--output <file>] [-- <ffmpeg-args>...]
```
