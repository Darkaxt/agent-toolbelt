# Media Family

Public media download plus local file-level media operations built on `yt-dlp`, `ffprobe`, and `ffmpeg`.

Use this family if you want:

- public media acquisition
- subtitle retrieval
- safe public URL classification before invoking `yt-dlp`
- metadata-only URL inspection and normalized format discovery
- media probing
- clipping, remuxing, audio extraction, and explicit transcoding

External requirements:

- `yt-dlp` available on `PATH`
- `ffmpeg` available on `PATH`
- `ffprobe` available on `PATH`

CLI:

```bash
uv run --package agent-toolbelt-media agent-toolbelt-media classify-url --url "https://example.com/video"
uv run --package agent-toolbelt-media agent-toolbelt-media metadata --url "https://example.com/video"
uv run --package agent-toolbelt-media agent-toolbelt-media formats --url "https://example.com/video"
uv run --package agent-toolbelt-media agent-toolbelt-media download --url "https://example.com/video"
uv run --package agent-toolbelt-media agent-toolbelt-media download --url "https://example.com/playlist" --playlist-mode full --playlist-items 1-3
uv run --package agent-toolbelt-media agent-toolbelt-media probe --input sample.mp4
```

`download` remains single-item by default. Use `metadata` or `formats` first when
format choice, playlist behavior, or source safety is unclear. Playlist downloads
require explicit `--playlist-mode full`.

Codex integration:

- `families/media/codex/skills/yt-dlp-ffmpeg`

Claude integration:

- `families/media/claude/marketplaces/agent-toolbelt-local`
