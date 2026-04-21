---
name: yt-dlp-ffmpeg
description: Use `yt-dlp`, `ffprobe`, and `ffmpeg` for public media download and local file-level media operations.
---

# YT-DLP + FFmpeg

## Overview

Use `scripts/invoke_media_tool.py` for public URL download and local file-level media work. The wrapper delegates into the media family package in this repo.

## Routing Rules

Use this skill when:

- The user wants to download media from a public `http(s)` URL.
- The user wants subtitles from a public media URL.
- The user wants media metadata, streams, duration, bitrate, or container details.
- The user wants to clip a file, extract audio, remux, or transcode a local media file.
- The user explicitly names `yt-dlp`, `ffmpeg`, or `ffprobe`.

Do not use this skill when:

- The task is understanding or summarizing a public page. Use the Gemini skill for that.
- The source is authenticated, private-network, localhost, `.local`, or browser-cookie-based.
- The request is unrelated to media acquisition or file-level media operations.

## Script Interface

```bash
python scripts/invoke_media_tool.py download --url <public-url> [--output-dir <dir>] [--audio-only] [--subs] [--format <selector>]
python scripts/invoke_media_tool.py probe --input <file>
python scripts/invoke_media_tool.py clip --input <file> --start <time> --end <time> [--output <file>]
python scripts/invoke_media_tool.py extract-audio --input <file> [--codec <name>] [--output <file>]
python scripts/invoke_media_tool.py remux --input <file> --container <ext> [--output <file>]
python scripts/invoke_media_tool.py transcode --input <file> [--output <file>] [-- <ffmpeg-args>...]
```
