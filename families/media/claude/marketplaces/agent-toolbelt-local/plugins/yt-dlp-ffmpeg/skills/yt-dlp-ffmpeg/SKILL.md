---
name: yt-dlp-ffmpeg
description: Use `scripts/invoke_media_tool.py` for public media URL classification, metadata/format discovery, download, and local file-level media operations through the media family package.
version: 0.1.1
---

# YT-DLP + FFmpeg

Use `scripts/invoke_media_tool.py` for public media download and local file-level media operations. The wrapper delegates into the media family package in this repo; if the workspace lives somewhere else, set `AGENT_TOOLBELT_HOME`.

## When This Skill Applies

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

## Boundary Rules

- `download` is for public `http(s)` URLs only.
- Prefer `classify-url`, `metadata`, or `formats` before `download` when source safety, playlist behavior, or format choice is unclear.
- `download` is single-item by default; playlist downloads require explicit `--playlist-mode full`.
- Use `--playlist-items <selector>` only with `--playlist-mode full`.
- Reject `localhost`, loopback, private IPs, and `.local` hosts before invoking `yt-dlp`.
- Do not use cookies, browser-session extraction, or authenticated-site flows in v1.
- Default download output goes to the current working directory unless the user specifies `--output-dir`.
- Keep page understanding and summarization outside this skill.
- Some unauthenticated YouTube downloads may still fail because YouTube does not expose usable media formats to the local `yt-dlp` client; surface the wrapper error directly when that happens.

## Workflow

1. Use `classify-url`, `metadata`, or `formats` before downloading when format choice, playlist behavior, or source safety is unclear.
2. Route public media URL downloads through `download`.
3. Route local file inspection through `probe`.
4. Use `clip`, `extract-audio`, or `remux` for common file-level operations.
5. Use `transcode` only when the user explicitly asks for codec, size, or compatibility changes.
6. Read the wrapper JSON and report artifacts plus the relevant metadata.

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
