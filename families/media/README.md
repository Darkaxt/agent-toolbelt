# Media Family

Public media download plus local file-level media operations built on `yt-dlp`, `ffprobe`, and `ffmpeg`.

Use this family if you want:

- public media acquisition
- subtitle retrieval
- media probing
- clipping, remuxing, audio extraction, and explicit transcoding

External requirements:

- `yt-dlp` available on `PATH`
- `ffmpeg` available on `PATH`
- `ffprobe` available on `PATH`

CLI:

```bash
uv run --package agent-toolbelt-media agent-toolbelt-media download --url "https://example.com/video"
uv run --package agent-toolbelt-media agent-toolbelt-media probe --input sample.mp4
```

Codex integration:

- `families/media/codex/skills/yt-dlp-ffmpeg`

Claude integration:

- `families/media/claude/marketplaces/agent-toolbelt-local`
