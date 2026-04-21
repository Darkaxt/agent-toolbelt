# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///

import argparse
import ipaddress
import json
import subprocess
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
    timeout_sec: int = DEFAULT_DOWNLOAD_TIMEOUT_SEC,
    binary_path: str | None = None,
) -> dict[str, Any]:
    validated_url = validate_public_url(url)
    ytdlp = resolve_binary("yt-dlp", explicit_path=binary_path)
    if ytdlp is None:
        return missing_binary_result("yt-dlp", "download")

    target_dir = Path(output_dir).expanduser().resolve() if output_dir else Path.cwd().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    metadata_command = [
        ytdlp,
        "--dump-single-json",
        "--no-warnings",
        "--no-playlist",
        validated_url,
    ]
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

    download_parser = subparsers.add_parser("download", help="Download media from a public URL.")
    download_parser.add_argument("--url", required=True)
    download_parser.add_argument("--output-dir")
    download_parser.add_argument("--audio-only", action="store_true")
    download_parser.add_argument("--subs", action="store_true")
    download_parser.add_argument("--format", dest="format_selector")
    download_parser.add_argument("--timeout-sec", type=int, default=DEFAULT_DOWNLOAD_TIMEOUT_SEC)

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
