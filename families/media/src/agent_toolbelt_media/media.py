# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///

import argparse
import html
import ipaddress
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agent_toolbelt_core.common import (
    normalize_host,
    resolve_windows_tool,
    run_process,
    validate_public_url,
)


DEFAULT_DOWNLOAD_TIMEOUT_SEC = 600
DEFAULT_MEDIA_TIMEOUT_SEC = 300
DEFAULT_PROBE_TIMEOUT_SEC = 60
DEFAULT_OUTPUT_TEMPLATE = "%(title)s [%(id)s].%(ext)s"
DEFAULT_TRANSCODE_ARGS = ["-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart"]

ENV_VARS = {
    "yt-dlp": "AGENT_TOOLBELT_YTDLP",
    "ffmpeg": "AGENT_TOOLBELT_FFMPEG",
    "ffprobe": "AGENT_TOOLBELT_FFPROBE",
}

LOCAL_TOOL_NAMES = {
    "yt-dlp": "yt-dlp.exe",
    "ffmpeg": "ffmpeg.exe",
    "ffprobe": "ffprobe.exe",
}

AUDIO_CODEC_SETTINGS = {
    "mp3": {"args": ["-c:a", "libmp3lame", "-b:a", "192k"], "extension": ".mp3"},
    "aac": {"args": ["-c:a", "aac", "-b:a", "192k"], "extension": ".m4a"},
    "flac": {"args": ["-c:a", "flac"], "extension": ".flac"},
    "wav": {"args": ["-c:a", "pcm_s16le"], "extension": ".wav"},
    "opus": {"args": ["-c:a", "libopus", "-b:a", "160k"], "extension": ".opus"},
}

VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}
SUBTITLE_EXTENSIONS = {".srt", ".vtt"}


def make_result(
    *,
    ok: bool,
    tool: str,
    operation: str,
    exit_code: int,
    stderr: str = "",
    artifacts: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "tool": tool,
        "operation": operation,
        "exit_code": exit_code,
        "stderr": stderr,
        "artifacts": artifacts or [],
        "metadata": metadata or {},
    }


def classify_public_url(url: str) -> dict[str, Any]:
    try:
        validated_url = validate_public_url(url)
    except ValueError as exc:
        parsed = urlparse(url)
        host = parsed.hostname
        return {
            "input_url": url,
            "url": None,
            "scheme": parsed.scheme or None,
            "host": normalize_host(host) if host else None,
            "safety_status": "rejected",
            "reason": str(exc),
        }

    parsed = urlparse(validated_url)
    return {
        "input_url": url,
        "url": validated_url,
        "scheme": parsed.scheme,
        "host": normalize_host(parsed.hostname),
        "safety_status": "public",
        "reason": None,
    }


def invoke_classify_url(*, url: str) -> dict[str, Any]:
    metadata = classify_public_url(url)
    return make_result(
        ok=metadata["safety_status"] == "public",
        tool="yt-dlp",
        operation="classify-url",
        exit_code=0 if metadata["safety_status"] == "public" else 2,
        stderr="" if metadata["safety_status"] == "public" else metadata["reason"],
        metadata=metadata,
    )


def validate_url_for_operation(url: str, operation: str) -> tuple[str | None, dict[str, Any] | None]:
    classification = classify_public_url(url)
    if classification["safety_status"] != "public":
        return None, make_result(
            ok=False,
            tool="yt-dlp",
            operation=operation,
            exit_code=2,
            stderr=classification["reason"] or "URL is not allowed.",
            metadata=classification,
        )
    return classification["url"], None


def resolve_binary(tool: str, explicit_path: str | None = None) -> str | None:
    return resolve_windows_tool(
        explicit_path=explicit_path,
        env_var=ENV_VARS[tool],
        path_names=(tool, f"{tool}.exe"),
        local_tool_name=LOCAL_TOOL_NAMES[tool],
    )


def ensure_input_file(path_text: str, operation: str, tool: str) -> tuple[Path | None, dict[str, Any] | None]:
    input_path = Path(path_text).expanduser().resolve()
    if not input_path.is_file():
        return None, make_result(
            ok=False,
            tool=tool,
            operation=operation,
            exit_code=2,
            stderr=f"Input file not found: {input_path}",
        )
    return input_path, None


def prepare_output_path(path_text: str | None, *, input_path: Path, suffix: str, extension: str) -> Path:
    if path_text:
        output_path = Path(path_text).expanduser().resolve()
    else:
        output_path = input_path.with_name(f"{input_path.stem}.{suffix}{extension}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def summarize_stderr(stderr: str, *, success: bool) -> str:
    stripped = stderr.strip()
    if not stripped:
        return ""
    if success:
        return ""

    lines = [line for line in stripped.splitlines() if line.strip()]
    if len(lines) > 40:
        lines = lines[-40:]
    joined = "\n".join(lines)
    if len(joined) > 8000:
        return joined[-8000:]
    return joined


def contextualize_download_error(url: str, stderr: str) -> str:
    summarized = summarize_stderr(stderr, success=False) or "yt-dlp download failed."
    host = normalize_host(urlparse(url).hostname)
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}:
        return summarized

    youtube_markers = (
        "Requested format is not available",
        "Only images are available for download",
        "Sign in to confirm you’re not a bot",
        "Sign in to confirm you're not a bot",
        "PO Token",
    )
    if any(marker in summarized for marker in youtube_markers):
        return (
            "YouTube did not expose downloadable media formats to the local unauthenticated yt-dlp client. "
            f"{summarized}"
        )
    return summarized


def maybe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def maybe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_json_output(raw_text: str) -> dict[str, Any]:
    return json.loads(raw_text.strip())


def playlist_args(playlist_mode: str) -> list[str] | None:
    if playlist_mode == "single":
        return ["--no-playlist"]
    if playlist_mode == "flat":
        return ["--flat-playlist"]
    if playlist_mode == "full":
        return ["--yes-playlist"]
    return None


def normalize_download_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload.get("id"),
        "title": payload.get("title"),
        "duration": maybe_float(payload.get("duration")),
        "extractor": payload.get("extractor"),
        "webpage_url": payload.get("webpage_url"),
        "uploader": payload.get("uploader"),
        "channel": payload.get("channel"),
        "ext": payload.get("ext"),
    }


def normalize_discovery_metadata(payload: dict[str, Any], *, playlist_mode: str) -> dict[str, Any]:
    metadata = normalize_download_metadata(payload)
    metadata.update(
        {
            "playlist_mode": playlist_mode,
            "playlist_id": payload.get("playlist_id") or payload.get("playlist"),
            "playlist_title": payload.get("playlist_title"),
            "playlist_count": maybe_int(payload.get("playlist_count")) or maybe_int(payload.get("n_entries")),
        }
    )
    entries = payload.get("entries")
    if isinstance(entries, list):
        metadata["entries"] = [
            {
                "id": entry.get("id"),
                "title": entry.get("title"),
                "duration": maybe_float(entry.get("duration")),
                "url": entry.get("url") or entry.get("webpage_url"),
            }
            for entry in entries
            if isinstance(entry, dict)
        ]
    return metadata


def normalize_format_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "format_id": entry.get("format_id"),
        "ext": entry.get("ext"),
        "resolution": entry.get("resolution"),
        "fps": maybe_float(entry.get("fps")),
        "vcodec": entry.get("vcodec"),
        "acodec": entry.get("acodec"),
        "tbr": maybe_float(entry.get("tbr")),
        "filesize": maybe_int(entry.get("filesize")) or maybe_int(entry.get("filesize_approx")),
        "protocol": entry.get("protocol"),
        "format_note": entry.get("format_note"),
    }


def normalize_probe_metadata(payload: dict[str, Any], input_path: Path) -> dict[str, Any]:
    format_data = payload.get("format", {})
    stream_entries = payload.get("streams", [])

    normalized_streams = []
    for stream in stream_entries:
        if not isinstance(stream, dict):
            continue
        normalized_streams.append(
            {
                "index": stream.get("index"),
                "codec_type": stream.get("codec_type"),
                "codec_name": stream.get("codec_name"),
                "width": maybe_int(stream.get("width")),
                "height": maybe_int(stream.get("height")),
                "channels": maybe_int(stream.get("channels")),
                "sample_rate": maybe_int(stream.get("sample_rate")),
                "duration": maybe_float(stream.get("duration")),
                "bit_rate": maybe_int(stream.get("bit_rate")),
            }
        )

    return {
        "input": str(input_path),
        "format": {
            "filename": format_data.get("filename", str(input_path)),
            "format_name": format_data.get("format_name"),
            "duration": maybe_float(format_data.get("duration")),
            "size": maybe_int(format_data.get("size")),
            "bit_rate": maybe_int(format_data.get("bit_rate")),
        },
        "streams": normalized_streams,
    }


def parse_download_artifacts(stdout: str, output_dir: Path) -> list[str]:
    artifacts: list[str] = []
    for line in stdout.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        artifact_path = Path(candidate)
        if not artifact_path.is_absolute():
            artifact_path = (output_dir / artifact_path).resolve()
        else:
            artifact_path = artifact_path.resolve()
        artifact_text = str(artifact_path)
        if artifact_text not in artifacts:
            artifacts.append(artifact_text)
    return artifacts


def clean_vtt_text(raw_text: str) -> str:
    cleaned_lines: list[str] = []
    skip_block = False
    for raw_line in raw_text.replace("\ufeff", "").splitlines():
        line = raw_line.strip()
        if line.startswith(("NOTE", "STYLE", "REGION")):
            skip_block = True
            continue
        if skip_block:
            if not line:
                skip_block = False
            continue
        if not line or line == "WEBVTT" or "-->" in line:
            continue
        if line.startswith(("Kind:", "Language:")) or line.isdigit():
            continue
        line = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
        if line and (not cleaned_lines or cleaned_lines[-1] != line):
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines) + ("\n" if cleaned_lines else "")


def analysis_run_directory(output_dir: str | None, source_id: str | None) -> Path:
    base_dir = Path(output_dir).expanduser().resolve() if output_dir else (Path.cwd() / "media-analysis").resolve()
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", source_id or "media").strip("-.") or "media"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = base_dir / f"analysis-{safe_id}-{timestamp}"
    suffix = 2
    while candidate.exists():
        candidate = base_dir / f"analysis-{safe_id}-{timestamp}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def paths_with_extensions(directory: Path, extensions: set[str]) -> list[Path]:
    return sorted(
        path.resolve()
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    )


def first_media_artifact(stdout: str, analysis_dir: Path) -> Path | None:
    reported = [Path(path) for path in parse_download_artifacts(stdout, analysis_dir)]
    candidates = [*reported, *paths_with_extensions(analysis_dir, VIDEO_EXTENSIONS)]
    for path in candidates:
        resolved = path.expanduser().resolve()
        if resolved.is_file() and resolved.suffix.lower() in VIDEO_EXTENSIONS:
            return resolved
    return None


def write_analysis_manifest(analysis_dir: Path, manifest: dict[str, Any]) -> Path:
    manifest_path = analysis_dir / "analysis-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest_path.resolve()


def missing_binary_result(tool: str, operation: str) -> dict[str, Any]:
    return make_result(
        ok=False,
        tool=tool,
        operation=operation,
        exit_code=127,
        stderr=(
            f"{tool} is not available via explicit path, environment override, or PATH. "
            "%LOCALAPPDATA%\\Tools remains a Windows compatibility fallback for older local installs."
        ),
    )


def invoke_download(
    *,
    url: str,
    output_dir: str | None,
    audio_only: bool,
    subs: bool,
    format_selector: str | None,
    playlist_mode: str = "single",
    playlist_items: str | None = None,
    timeout_sec: int = DEFAULT_DOWNLOAD_TIMEOUT_SEC,
    binary_path: str | None = None,
) -> dict[str, Any]:
    playlist_flags = playlist_args(playlist_mode)
    if playlist_flags is None:
        return make_result(
            ok=False,
            tool="yt-dlp",
            operation="download",
            exit_code=2,
            stderr=f"Unsupported playlist mode: {playlist_mode}",
        )
    if playlist_items and playlist_mode != "full":
        return make_result(
            ok=False,
            tool="yt-dlp",
            operation="download",
            exit_code=2,
            stderr="--playlist-items requires --playlist-mode full.",
        )

    validated_url, validation_error = validate_url_for_operation(url, "download")
    if validation_error is not None:
        return validation_error

    ytdlp = resolve_binary("yt-dlp", explicit_path=binary_path)
    if ytdlp is None:
        return missing_binary_result("yt-dlp", "download")

    target_dir = Path(output_dir).expanduser().resolve() if output_dir else Path.cwd().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    metadata_command = [
        ytdlp,
        "--dump-single-json",
        "--no-warnings",
        *playlist_flags,
        validated_url,
    ]
    if playlist_items:
        metadata_command[-1:-1] = ["--playlist-items", playlist_items]
    metadata_run = run_process(metadata_command, timeout_sec=timeout_sec)
    if metadata_run.returncode != 0:
        return make_result(
            ok=False,
            tool="yt-dlp",
            operation="download",
            exit_code=metadata_run.returncode,
            stderr=contextualize_download_error(validated_url, metadata_run.stderr),
        )

    try:
        metadata = normalize_download_metadata(parse_json_output(metadata_run.stdout))
    except json.JSONDecodeError:
        return make_result(
            ok=False,
            tool="yt-dlp",
            operation="download",
            exit_code=1,
            stderr="Failed to parse yt-dlp metadata JSON output.",
        )

    download_command = [
        ytdlp,
        "--no-playlist",
        "--no-progress",
        "--newline",
        "--paths",
        str(target_dir),
        "-o",
        DEFAULT_OUTPUT_TEMPLATE,
        "--print",
        "after_move:filepath",
    ]
    download_command.extend(playlist_flags)
    if playlist_items:
        download_command.extend(["--playlist-items", playlist_items])
    if audio_only:
        download_command.extend(["-f", "bestaudio/best"])
    elif format_selector:
        download_command.extend(["-f", format_selector])
    if subs:
        download_command.extend(["--write-subs", "--write-auto-subs", "--sub-langs", "all"])
    download_command.append(validated_url)

    download_run = run_process(download_command, timeout_sec=timeout_sec, cwd=str(target_dir))
    artifacts = parse_download_artifacts(download_run.stdout, target_dir)
    if download_run.returncode != 0:
        return make_result(
            ok=False,
            tool="yt-dlp",
            operation="download",
            exit_code=download_run.returncode,
            stderr=contextualize_download_error(validated_url, download_run.stderr),
            artifacts=artifacts,
            metadata=metadata,
        )
    if not artifacts:
        return make_result(
            ok=False,
            tool="yt-dlp",
            operation="download",
            exit_code=1,
            stderr="yt-dlp completed without reporting downloaded artifacts.",
            metadata=metadata,
        )
    return make_result(
        ok=True,
        tool="yt-dlp",
        operation="download",
        exit_code=0,
        artifacts=artifacts,
        metadata=metadata,
    )


def invoke_metadata(
    *,
    url: str,
    playlist_mode: str = "single",
    timeout_sec: int = DEFAULT_DOWNLOAD_TIMEOUT_SEC,
    binary_path: str | None = None,
) -> dict[str, Any]:
    playlist_flags = playlist_args(playlist_mode)
    if playlist_flags is None:
        return make_result(
            ok=False,
            tool="yt-dlp",
            operation="metadata",
            exit_code=2,
            stderr=f"Unsupported playlist mode: {playlist_mode}",
        )
    validated_url, validation_error = validate_url_for_operation(url, "metadata")
    if validation_error is not None:
        return validation_error
    ytdlp = resolve_binary("yt-dlp", explicit_path=binary_path)
    if ytdlp is None:
        return missing_binary_result("yt-dlp", "metadata")

    command = [
        ytdlp,
        "--dump-single-json",
        "--no-warnings",
        *playlist_flags,
        validated_url,
    ]
    completed = run_process(command, timeout_sec=timeout_sec)
    if completed.returncode != 0:
        return make_result(
            ok=False,
            tool="yt-dlp",
            operation="metadata",
            exit_code=completed.returncode,
            stderr=contextualize_download_error(validated_url, completed.stderr),
        )
    try:
        payload = parse_json_output(completed.stdout)
    except json.JSONDecodeError:
        return make_result(
            ok=False,
            tool="yt-dlp",
            operation="metadata",
            exit_code=1,
            stderr="Failed to parse yt-dlp metadata JSON output.",
        )
    return make_result(
        ok=True,
        tool="yt-dlp",
        operation="metadata",
        exit_code=0,
        metadata=normalize_discovery_metadata(payload, playlist_mode=playlist_mode),
    )


def invoke_formats(
    *,
    url: str,
    timeout_sec: int = DEFAULT_DOWNLOAD_TIMEOUT_SEC,
    binary_path: str | None = None,
) -> dict[str, Any]:
    validated_url, validation_error = validate_url_for_operation(url, "formats")
    if validation_error is not None:
        return validation_error
    ytdlp = resolve_binary("yt-dlp", explicit_path=binary_path)
    if ytdlp is None:
        return missing_binary_result("yt-dlp", "formats")

    command = [
        ytdlp,
        "--dump-single-json",
        "--no-warnings",
        "--no-playlist",
        validated_url,
    ]
    completed = run_process(command, timeout_sec=timeout_sec)
    if completed.returncode != 0:
        return make_result(
            ok=False,
            tool="yt-dlp",
            operation="formats",
            exit_code=completed.returncode,
            stderr=contextualize_download_error(validated_url, completed.stderr),
        )
    try:
        payload = parse_json_output(completed.stdout)
    except json.JSONDecodeError:
        return make_result(
            ok=False,
            tool="yt-dlp",
            operation="formats",
            exit_code=1,
            stderr="Failed to parse yt-dlp metadata JSON output.",
        )
    formats = payload.get("formats") if isinstance(payload.get("formats"), list) else []
    metadata = normalize_download_metadata(payload)
    metadata["formats"] = [normalize_format_entry(entry) for entry in formats if isinstance(entry, dict)]
    return make_result(
        ok=True,
        tool="yt-dlp",
        operation="formats",
        exit_code=0,
        metadata=metadata,
    )


def invoke_prepare_analysis(
    *,
    url: str,
    output_dir: str | None,
    subtitle_langs: str,
    include_visuals: bool,
    include_audio: bool,
    max_height: int,
    frame_interval_sec: float,
    max_frames: int,
) -> dict[str, Any]:
    if max_height < 144:
        return make_result(
            ok=False,
            tool="yt-dlp+ffmpeg",
            operation="prepare-analysis",
            exit_code=2,
            stderr="--max-height must be at least 144.",
        )
    if frame_interval_sec <= 0:
        return make_result(
            ok=False,
            tool="yt-dlp+ffmpeg",
            operation="prepare-analysis",
            exit_code=2,
            stderr="--frame-interval-sec must be greater than zero.",
        )
    if max_frames < 2:
        return make_result(
            ok=False,
            tool="yt-dlp+ffmpeg",
            operation="prepare-analysis",
            exit_code=2,
            stderr="--max-frames must be at least 2.",
        )

    validated_url, validation_error = validate_url_for_operation(url, "prepare-analysis")
    if validation_error is not None:
        validation_error["tool"] = "yt-dlp+ffmpeg"
        return validation_error
    ytdlp = resolve_binary("yt-dlp")
    if ytdlp is None:
        missing = missing_binary_result("yt-dlp", "prepare-analysis")
        missing["tool"] = "yt-dlp+ffmpeg"
        return missing

    metadata_command = [
        ytdlp,
        "--dump-single-json",
        "--no-warnings",
        "--no-playlist",
        validated_url,
    ]
    metadata_run = run_process(metadata_command, timeout_sec=None)
    if metadata_run.returncode != 0:
        return make_result(
            ok=False,
            tool="yt-dlp+ffmpeg",
            operation="prepare-analysis",
            exit_code=metadata_run.returncode,
            stderr=contextualize_download_error(validated_url, metadata_run.stderr),
        )
    try:
        source_payload = parse_json_output(metadata_run.stdout)
    except json.JSONDecodeError:
        return make_result(
            ok=False,
            tool="yt-dlp+ffmpeg",
            operation="prepare-analysis",
            exit_code=1,
            stderr="Failed to parse yt-dlp metadata JSON output.",
        )

    source = normalize_download_metadata(source_payload)
    source["chapters"] = source_payload.get("chapters") if isinstance(source_payload.get("chapters"), list) else []
    analysis_dir = analysis_run_directory(output_dir, source.get("id"))
    warnings: list[str] = []
    requested_failures: list[str] = []
    evidence: dict[str, Any] = {
        "subtitles": [],
        "transcript": None,
        "media": None,
        "audio": None,
        "interval_frames": [],
        "scene_frames": [],
        "manifest": None,
    }
    stage_results: dict[str, Any] = {}

    subtitle_command = [
        ytdlp,
        "--no-playlist",
        "--no-progress",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        subtitle_langs,
        "--sub-format",
        "vtt",
        "--paths",
        str(analysis_dir),
        "-o",
        DEFAULT_OUTPUT_TEMPLATE,
        validated_url,
    ]
    subtitle_run = run_process(subtitle_command, timeout_sec=None, cwd=str(analysis_dir))
    subtitle_paths = paths_with_extensions(analysis_dir, SUBTITLE_EXTENSIONS)
    evidence["subtitles"] = [str(path) for path in subtitle_paths]
    stage_results["subtitles"] = {
        "exit_code": subtitle_run.returncode,
        "artifact_count": len(subtitle_paths),
    }
    if subtitle_run.returncode != 0:
        warnings.append(
            "Subtitle acquisition failed: "
            + (summarize_stderr(subtitle_run.stderr, success=False) or "yt-dlp subtitle request failed.")
        )
    if not subtitle_paths:
        warnings.append("No subtitles were available for the requested language selector.")
    else:
        preferred_vtt = next((path for path in subtitle_paths if path.suffix.lower() == ".vtt"), None)
        if preferred_vtt is not None:
            transcript_text = clean_vtt_text(preferred_vtt.read_text(encoding="utf-8", errors="replace"))
            if transcript_text:
                transcript_path = analysis_dir / "transcript.txt"
                transcript_path.write_text(transcript_text, encoding="utf-8")
                evidence["transcript"] = str(transcript_path.resolve())
            else:
                warnings.append("The selected subtitle artifact did not contain readable transcript text.")

    media_path: Path | None = None
    if include_visuals:
        visual_format = (
            f"bestvideo[height<={max_height}]+bestaudio/"
            f"best[height<={max_height}]"
        )
        visual_command = [
            ytdlp,
            "--no-playlist",
            "--no-progress",
            "--newline",
            "--paths",
            str(analysis_dir),
            "-o",
            DEFAULT_OUTPUT_TEMPLATE,
            "--print",
            "after_move:filepath",
            "-f",
            visual_format,
            validated_url,
        ]
        visual_run = run_process(visual_command, timeout_sec=None, cwd=str(analysis_dir))
        media_path = first_media_artifact(visual_run.stdout, analysis_dir)
        stage_results["visual_media"] = {
            "exit_code": visual_run.returncode,
            "artifact_count": 1 if media_path else 0,
            "max_height": max_height,
        }
        if visual_run.returncode != 0 or media_path is None:
            message = contextualize_download_error(validated_url, visual_run.stderr)
            requested_failures.append(message or "Requested visual media could not be prepared.")
        else:
            evidence["media"] = str(media_path)
            ffmpeg = resolve_binary("ffmpeg")
            if ffmpeg is None:
                requested_failures.append("ffmpeg is unavailable, so requested visual frames could not be extracted.")
            else:
                frames_dir = analysis_dir / "frames"
                frames_dir.mkdir(parents=True, exist_ok=True)
                interval_limit = max(1, max_frames // 2)
                scene_limit = max_frames - interval_limit
                interval_pattern = frames_dir / "interval-%03d.jpg"
                interval_command = [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(media_path),
                    "-vf",
                    f"fps=1/{frame_interval_sec:g}",
                    "-frames:v",
                    str(interval_limit),
                    str(interval_pattern),
                ]
                interval_run = run_process(interval_command, timeout_sec=None, cwd=str(analysis_dir))
                evidence["interval_frames"] = [
                    str(path) for path in sorted(frames_dir.glob("interval-*.jpg"))[:interval_limit]
                ]
                stage_results["interval_frames"] = {
                    "exit_code": interval_run.returncode,
                    "artifact_count": len(evidence["interval_frames"]),
                    "limit": interval_limit,
                }
                if interval_run.returncode != 0:
                    warnings.append(
                        "Interval frame extraction failed: "
                        + (summarize_stderr(interval_run.stderr, success=False) or "ffmpeg failed.")
                    )

                scene_pattern = frames_dir / "scene-%03d.jpg"
                scene_command = [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(media_path),
                    "-vf",
                    "select=gt(scene\\,0.35)",
                    "-fps_mode",
                    "vfr",
                    "-frames:v",
                    str(scene_limit),
                    str(scene_pattern),
                ]
                scene_run = run_process(scene_command, timeout_sec=None, cwd=str(analysis_dir))
                evidence["scene_frames"] = [
                    str(path) for path in sorted(frames_dir.glob("scene-*.jpg"))[:scene_limit]
                ]
                stage_results["scene_frames"] = {
                    "exit_code": scene_run.returncode,
                    "artifact_count": len(evidence["scene_frames"]),
                    "limit": scene_limit,
                }
                if scene_run.returncode != 0:
                    warnings.append(
                        "Scene frame extraction failed: "
                        + (summarize_stderr(scene_run.stderr, success=False) or "ffmpeg failed.")
                    )
                if not evidence["interval_frames"] and not evidence["scene_frames"]:
                    requested_failures.append("Requested visual frames were not created.")

    if include_audio:
        if media_path is not None:
            ffmpeg = resolve_binary("ffmpeg")
            audio_path = analysis_dir / "audio.mp3"
            if ffmpeg is None:
                audio_run = subprocess.CompletedProcess([], 127, stdout="", stderr="ffmpeg is unavailable.")
            else:
                audio_command = [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(media_path),
                    "-vn",
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "128k",
                    str(audio_path),
                ]
                audio_run = run_process(audio_command, timeout_sec=None, cwd=str(analysis_dir))
        else:
            audio_command = [
                ytdlp,
                "--no-playlist",
                "--no-progress",
                "--newline",
                "--paths",
                str(analysis_dir),
                "-o",
                DEFAULT_OUTPUT_TEMPLATE,
                "--print",
                "after_move:filepath",
                "-f",
                "bestaudio/best",
                "-x",
                "--audio-format",
                "mp3",
                validated_url,
            ]
            audio_run = run_process(audio_command, timeout_sec=None, cwd=str(analysis_dir))
            reported_audio = [Path(path) for path in parse_download_artifacts(audio_run.stdout, analysis_dir)]
            audio_path = next(
                (path.resolve() for path in reported_audio if path.resolve().is_file() and path.suffix.lower() == ".mp3"),
                analysis_dir / "missing-audio.mp3",
            )
        if audio_run.returncode == 0 and audio_path.is_file():
            evidence["audio"] = str(audio_path.resolve())
        else:
            requested_failures.append(
                summarize_stderr(audio_run.stderr, success=False) or "Requested audio could not be prepared."
            )
        stage_results["audio"] = {
            "exit_code": audio_run.returncode,
            "artifact_count": 1 if evidence["audio"] else 0,
        }

    analysis_ready = bool(
        evidence["transcript"]
        or evidence["media"]
        or evidence["audio"]
        or evidence["interval_frames"]
        or evidence["scene_frames"]
    )
    next_steps: list[str] = []
    if evidence["transcript"]:
        next_steps.append("Read the cleaned transcript before acquiring heavier media artifacts.")
    else:
        next_steps.append("No transcript was prepared; request audio for transcription or visual frames as needed.")
    if not include_visuals:
        next_steps.append("Rerun with --include-visuals when visual context is material to the question.")
    elif evidence["interval_frames"] or evidence["scene_frames"]:
        next_steps.append("Inspect interval and scene frames alongside transcript evidence.")
    if evidence["audio"]:
        next_steps.append("Transcribe the prepared audio locally when spoken content is required.")

    manifest = {
        "operation": "prepare-analysis",
        "source": source,
        "analysis_dir": str(analysis_dir),
        "analysis_ready": analysis_ready,
        "requested": {
            "subtitle_langs": subtitle_langs,
            "include_visuals": include_visuals,
            "include_audio": include_audio,
            "max_height": max_height,
            "frame_interval_sec": frame_interval_sec,
            "max_frames": max_frames,
        },
        "evidence": evidence,
        "stages": stage_results,
        "warnings": warnings,
        "requested_failures": requested_failures,
        "recommended_next_steps": next_steps,
    }
    manifest_path = write_analysis_manifest(analysis_dir, manifest)
    evidence["manifest"] = str(manifest_path)
    manifest["evidence"]["manifest"] = str(manifest_path)
    write_analysis_manifest(analysis_dir, manifest)

    artifacts: list[str] = []
    for key in ("subtitles", "interval_frames", "scene_frames"):
        artifacts.extend(evidence[key])
    for key in ("transcript", "media", "audio", "manifest"):
        if evidence[key]:
            artifacts.append(evidence[key])

    ok = not requested_failures
    return make_result(
        ok=ok,
        tool="yt-dlp+ffmpeg",
        operation="prepare-analysis",
        exit_code=0 if ok else 1,
        stderr="\n".join(requested_failures),
        artifacts=list(dict.fromkeys(artifacts)),
        metadata={
            "analysis_ready": analysis_ready,
            "analysis_dir": str(analysis_dir),
            "source": source,
            "evidence": evidence,
            "stages": stage_results,
            "warnings": warnings,
            "recommended_next_steps": next_steps,
        },
    )


def invoke_probe(
    *,
    input_path: str,
    timeout_sec: int = DEFAULT_PROBE_TIMEOUT_SEC,
    binary_path: str | None = None,
) -> dict[str, Any]:
    resolved_input, error_result = ensure_input_file(input_path, "probe", "ffprobe")
    if error_result is not None:
        return error_result

    ffprobe = resolve_binary("ffprobe", explicit_path=binary_path)
    if ffprobe is None:
        return missing_binary_result("ffprobe", "probe")

    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(resolved_input),
    ]
    completed = run_process(command, timeout_sec=timeout_sec)
    if completed.returncode != 0:
        return make_result(
            ok=False,
            tool="ffprobe",
            operation="probe",
            exit_code=completed.returncode,
            stderr=summarize_stderr(completed.stderr, success=False) or "ffprobe failed.",
        )

    try:
        payload = parse_json_output(completed.stdout)
    except json.JSONDecodeError:
        return make_result(
            ok=False,
            tool="ffprobe",
            operation="probe",
            exit_code=1,
            stderr="Failed to parse ffprobe JSON output.",
        )

    return make_result(
        ok=True,
        tool="ffprobe",
        operation="probe",
        exit_code=0,
        artifacts=[str(resolved_input)],
        metadata=normalize_probe_metadata(payload, resolved_input),
    )


def invoke_clip(
    *,
    input_path: str,
    start: str,
    end: str,
    output_path: str | None,
    timeout_sec: int = DEFAULT_MEDIA_TIMEOUT_SEC,
    binary_path: str | None = None,
) -> dict[str, Any]:
    resolved_input, error_result = ensure_input_file(input_path, "clip", "ffmpeg")
    if error_result is not None:
        return error_result

    ffmpeg = resolve_binary("ffmpeg", explicit_path=binary_path)
    if ffmpeg is None:
        return missing_binary_result("ffmpeg", "clip")

    resolved_output = prepare_output_path(
        output_path,
        input_path=resolved_input,
        suffix="clip",
        extension=resolved_input.suffix or ".mp4",
    )
    command = [
        ffmpeg,
        "-y",
        "-ss",
        start,
        "-to",
        end,
        "-i",
        str(resolved_input),
        "-map",
        "0",
        "-c",
        "copy",
        str(resolved_output),
    ]
    completed = run_process(command, timeout_sec=timeout_sec)
    if completed.returncode != 0:
        return make_result(
            ok=False,
            tool="ffmpeg",
            operation="clip",
            exit_code=completed.returncode,
            stderr=summarize_stderr(completed.stderr, success=False) or "ffmpeg clip failed.",
            metadata={"input": str(resolved_input), "start": start, "end": end},
        )
    if not resolved_output.exists():
        return make_result(
            ok=False,
            tool="ffmpeg",
            operation="clip",
            exit_code=1,
            stderr=f"Expected clip output was not created: {resolved_output}",
            metadata={"input": str(resolved_input), "start": start, "end": end},
        )
    return make_result(
        ok=True,
        tool="ffmpeg",
        operation="clip",
        exit_code=0,
        artifacts=[str(resolved_output)],
        metadata={"input": str(resolved_input), "start": start, "end": end},
    )


def invoke_extract_audio(
    *,
    input_path: str,
    codec: str,
    output_path: str | None,
    timeout_sec: int = DEFAULT_MEDIA_TIMEOUT_SEC,
    binary_path: str | None = None,
) -> dict[str, Any]:
    resolved_input, error_result = ensure_input_file(input_path, "extract-audio", "ffmpeg")
    if error_result is not None:
        return error_result

    ffmpeg = resolve_binary("ffmpeg", explicit_path=binary_path)
    if ffmpeg is None:
        return missing_binary_result("ffmpeg", "extract-audio")

    normalized_codec = codec.lower()
    if normalized_codec not in AUDIO_CODEC_SETTINGS:
        return make_result(
            ok=False,
            tool="ffmpeg",
            operation="extract-audio",
            exit_code=2,
            stderr=f"Unsupported audio codec: {codec}",
        )

    codec_settings = AUDIO_CODEC_SETTINGS[normalized_codec]
    resolved_output = prepare_output_path(
        output_path,
        input_path=resolved_input,
        suffix="audio",
        extension=codec_settings["extension"],
    )
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(resolved_input),
        "-vn",
        *codec_settings["args"],
        str(resolved_output),
    ]
    completed = run_process(command, timeout_sec=timeout_sec)
    if completed.returncode != 0:
        return make_result(
            ok=False,
            tool="ffmpeg",
            operation="extract-audio",
            exit_code=completed.returncode,
            stderr=summarize_stderr(completed.stderr, success=False) or "ffmpeg audio extraction failed.",
            metadata={"input": str(resolved_input), "codec": normalized_codec},
        )
    if not resolved_output.exists():
        return make_result(
            ok=False,
            tool="ffmpeg",
            operation="extract-audio",
            exit_code=1,
            stderr=f"Expected audio output was not created: {resolved_output}",
            metadata={"input": str(resolved_input), "codec": normalized_codec},
        )
    return make_result(
        ok=True,
        tool="ffmpeg",
        operation="extract-audio",
        exit_code=0,
        artifacts=[str(resolved_output)],
        metadata={"input": str(resolved_input), "codec": normalized_codec},
    )


def invoke_remux(
    *,
    input_path: str,
    container: str,
    output_path: str | None,
    timeout_sec: int = DEFAULT_MEDIA_TIMEOUT_SEC,
    binary_path: str | None = None,
) -> dict[str, Any]:
    resolved_input, error_result = ensure_input_file(input_path, "remux", "ffmpeg")
    if error_result is not None:
        return error_result

    ffmpeg = resolve_binary("ffmpeg", explicit_path=binary_path)
    if ffmpeg is None:
        return missing_binary_result("ffmpeg", "remux")

    normalized_container = container.lower().lstrip(".")
    resolved_output = prepare_output_path(
        output_path,
        input_path=resolved_input,
        suffix="remux",
        extension=f".{normalized_container}",
    )
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(resolved_input),
        "-map",
        "0",
        "-c",
        "copy",
        str(resolved_output),
    ]
    completed = run_process(command, timeout_sec=timeout_sec)
    if completed.returncode != 0:
        return make_result(
            ok=False,
            tool="ffmpeg",
            operation="remux",
            exit_code=completed.returncode,
            stderr=summarize_stderr(completed.stderr, success=False) or "ffmpeg remux failed.",
            metadata={"input": str(resolved_input), "container": normalized_container},
        )
    if not resolved_output.exists():
        return make_result(
            ok=False,
            tool="ffmpeg",
            operation="remux",
            exit_code=1,
            stderr=f"Expected remux output was not created: {resolved_output}",
            metadata={"input": str(resolved_input), "container": normalized_container},
        )
    return make_result(
        ok=True,
        tool="ffmpeg",
        operation="remux",
        exit_code=0,
        artifacts=[str(resolved_output)],
        metadata={"input": str(resolved_input), "container": normalized_container},
    )


def invoke_transcode(
    *,
    input_path: str,
    output_path: str | None,
    ffmpeg_args: list[str],
    timeout_sec: int = DEFAULT_MEDIA_TIMEOUT_SEC,
    binary_path: str | None = None,
) -> dict[str, Any]:
    resolved_input, error_result = ensure_input_file(input_path, "transcode", "ffmpeg")
    if error_result is not None:
        return error_result

    ffmpeg = resolve_binary("ffmpeg", explicit_path=binary_path)
    if ffmpeg is None:
        return missing_binary_result("ffmpeg", "transcode")

    cleaned_args = list(ffmpeg_args)
    if cleaned_args and cleaned_args[0] == "--":
        cleaned_args = cleaned_args[1:]
    resolved_output = prepare_output_path(
        output_path,
        input_path=resolved_input,
        suffix="transcoded",
        extension=".mp4",
    )
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(resolved_input),
        *(cleaned_args or DEFAULT_TRANSCODE_ARGS),
        str(resolved_output),
    ]
    completed = run_process(command, timeout_sec=timeout_sec)
    if completed.returncode != 0:
        return make_result(
            ok=False,
            tool="ffmpeg",
            operation="transcode",
            exit_code=completed.returncode,
            stderr=summarize_stderr(completed.stderr, success=False) or "ffmpeg transcode failed.",
            metadata={"input": str(resolved_input), "ffmpeg_args": cleaned_args or DEFAULT_TRANSCODE_ARGS},
        )
    if not resolved_output.exists():
        return make_result(
            ok=False,
            tool="ffmpeg",
            operation="transcode",
            exit_code=1,
            stderr=f"Expected transcode output was not created: {resolved_output}",
            metadata={"input": str(resolved_input), "ffmpeg_args": cleaned_args or DEFAULT_TRANSCODE_ARGS},
        )
    return make_result(
        ok=True,
        tool="ffmpeg",
        operation="transcode",
        exit_code=0,
        artifacts=[str(resolved_output)],
        metadata={"input": str(resolved_input), "ffmpeg_args": cleaned_args or DEFAULT_TRANSCODE_ARGS},
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wrap yt-dlp, ffprobe, and ffmpeg for public downloads and local media operations."
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    classify_parser = subparsers.add_parser("classify-url", help="Classify whether a URL is safe public media input.")
    classify_parser.add_argument("--url", required=True)

    metadata_parser = subparsers.add_parser("metadata", help="Inspect public media URL metadata without downloading.")
    metadata_parser.add_argument("--url", required=True)
    metadata_parser.add_argument("--playlist-mode", choices=["single", "flat", "full"], default="single")
    metadata_parser.add_argument("--timeout-sec", type=int, default=DEFAULT_DOWNLOAD_TIMEOUT_SEC)

    formats_parser = subparsers.add_parser("formats", help="List normalized downloadable formats for a public media URL.")
    formats_parser.add_argument("--url", required=True)
    formats_parser.add_argument("--timeout-sec", type=int, default=DEFAULT_DOWNLOAD_TIMEOUT_SEC)

    download_parser = subparsers.add_parser("download", help="Download media from a public URL.")
    download_parser.add_argument("--url", required=True)
    download_parser.add_argument("--output-dir")
    download_parser.add_argument("--audio-only", action="store_true")
    download_parser.add_argument("--subs", action="store_true")
    download_parser.add_argument("--format", dest="format_selector")
    download_parser.add_argument("--playlist-mode", choices=["single", "full"], default="single")
    download_parser.add_argument("--playlist-items")
    download_parser.add_argument("--timeout-sec", type=int, default=DEFAULT_DOWNLOAD_TIMEOUT_SEC)

    prepare_analysis_parser = subparsers.add_parser(
        "prepare-analysis",
        help="Prepare transcript-first local evidence for public video analysis.",
    )
    prepare_analysis_parser.add_argument("--url", required=True)
    prepare_analysis_parser.add_argument("--output-dir")
    prepare_analysis_parser.add_argument("--subtitle-langs", default="en.*,en")
    prepare_analysis_parser.add_argument("--include-visuals", action="store_true")
    prepare_analysis_parser.add_argument("--include-audio", action="store_true")
    prepare_analysis_parser.add_argument("--max-height", type=int, default=480)
    prepare_analysis_parser.add_argument("--frame-interval-sec", type=float, default=30.0)
    prepare_analysis_parser.add_argument("--max-frames", type=int, default=24)

    probe_parser = subparsers.add_parser("probe", help="Inspect a local media file with ffprobe.")
    probe_parser.add_argument("--input", required=True)
    probe_parser.add_argument("--timeout-sec", type=int, default=DEFAULT_PROBE_TIMEOUT_SEC)

    clip_parser = subparsers.add_parser("clip", help="Clip a local media file with ffmpeg.")
    clip_parser.add_argument("--input", required=True)
    clip_parser.add_argument("--start", required=True)
    clip_parser.add_argument("--end", required=True)
    clip_parser.add_argument("--output")
    clip_parser.add_argument("--timeout-sec", type=int, default=DEFAULT_MEDIA_TIMEOUT_SEC)

    extract_audio_parser = subparsers.add_parser("extract-audio", help="Extract audio from a local media file.")
    extract_audio_parser.add_argument("--input", required=True)
    extract_audio_parser.add_argument("--codec", default="mp3", choices=sorted(AUDIO_CODEC_SETTINGS))
    extract_audio_parser.add_argument("--output")
    extract_audio_parser.add_argument("--timeout-sec", type=int, default=DEFAULT_MEDIA_TIMEOUT_SEC)

    remux_parser = subparsers.add_parser("remux", help="Change container without re-encoding.")
    remux_parser.add_argument("--input", required=True)
    remux_parser.add_argument("--container", required=True)
    remux_parser.add_argument("--output")
    remux_parser.add_argument("--timeout-sec", type=int, default=DEFAULT_MEDIA_TIMEOUT_SEC)

    transcode_parser = subparsers.add_parser("transcode", help="Transcode a local media file with explicit ffmpeg args.")
    transcode_parser.add_argument("--input", required=True)
    transcode_parser.add_argument("--output")
    transcode_parser.add_argument("--timeout-sec", type=int, default=DEFAULT_MEDIA_TIMEOUT_SEC)
    transcode_parser.add_argument("ffmpeg_args", nargs=argparse.REMAINDER)

    return parser
