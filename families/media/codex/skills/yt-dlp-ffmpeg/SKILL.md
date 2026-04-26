---
name: yt-dlp-ffmpeg
description: Use `yt-dlp`, `ffprobe`, and `ffmpeg` for public media URL classification, metadata/format discovery, download, and local file-level media operations.
license: MIT
compatibility: Requires yt-dlp, ffmpeg, and ffprobe. Intended for public media and local file operations only.
metadata:
  version: "0.1.0"
---

# YT-DLP + FFmpeg

## Overview

Use `scripts/invoke_media_tool.py` for public URL download and local file-level media work. The wrapper delegates into the media family package in this repo.

## Routing Rules

Use this skill when:

- The user wants to download media from a public `http(s)` URL.
- The user wants subtitles from a public media URL.
- The user wants media metadata, streams, duration, bitrate, or container details.
- The user needs to check whether a URL is safe public media input before downloading.
- The user needs available formats or playlist metadata before choosing a download.
- The user wants to clip a file, extract audio, remux, or transcode a local media file.
- The user explicitly names `yt-dlp`, `ffmpeg`, or `ffprobe`.

Do not use this skill when:

- The task is understanding or summarizing a public page. Use the Gemini skill for that.
- The source is authenticated, private-network, localhost, `.local`, or browser-cookie-based.
- The user asks to use cookies, browser-session extraction, or other access-control bypasses.
- The request is unrelated to media acquisition or file-level media operations.

## Behavior

- Prefer `classify-url`, `metadata`, or `formats` before `download` when source safety, playlist behavior, or format choice is unclear.
- `download` is single-item by default and uses `--playlist-mode single`; playlist downloads require explicit `--playlist-mode full`.
- Use `--playlist-items <selector>` only with `--playlist-mode full`.
- Treat structured JSON failures as authoritative; do not retry with cookies or authenticated browser state.

## Script Interface

```bash
python scripts/invoke_media_tool.py classify-url --url <public-url>
python scripts/invoke_media_tool.py metadata --url <public-url> [--playlist-mode single|flat|full]
python scripts/invoke_media_tool.py formats --url <public-url>
python scripts/invoke_media_tool.py download --url <public-url> [--output-dir <dir>] [--audio-only] [--subs] [--format <selector>]
python scripts/invoke_media_tool.py download --url <public-playlist-url> --playlist-mode full [--playlist-items <selector>]
python scripts/invoke_media_tool.py probe --input <file>
python scripts/invoke_media_tool.py clip --input <file> --start <time> --end <time> [--output <file>]
python scripts/invoke_media_tool.py extract-audio --input <file> [--codec <name>] [--output <file>]
python scripts/invoke_media_tool.py remux --input <file> --container <ext> [--output <file>]
python scripts/invoke_media_tool.py transcode --input <file> [--output <file>] [-- <ffmpeg-args>...]
```
