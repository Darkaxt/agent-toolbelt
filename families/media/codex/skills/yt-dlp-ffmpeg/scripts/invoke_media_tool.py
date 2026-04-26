import json
import sys
from pathlib import Path


def bootstrap_core_src() -> None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        pyproject = parent / "pyproject.toml"
        core_src = parent / "packages" / "core" / "src"
        if pyproject.exists() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            if str(core_src) not in sys.path:
                sys.path.insert(0, str(core_src))
            return
    raise RuntimeError("Could not locate the repository packages/core/src directory.")


bootstrap_core_src()

from agent_toolbelt_core.bootstrap import bootstrap_family_package  # noqa: E402

bootstrap_family_package(__file__, family_name="media", package_dir_name="agent_toolbelt_media")

from agent_toolbelt_media import media  # noqa: E402


def operation_tool(operation: str) -> str:
    if operation in {"classify-url", "metadata", "formats", "download"}:
        return "yt-dlp"
    if operation == "probe":
        return "ffprobe"
    return "ffmpeg"


def main() -> int:
    parser = media.build_parser()
    args = parser.parse_args()

    try:
        if args.operation == "classify-url":
            result = media.invoke_classify_url(url=args.url)
        elif args.operation == "metadata":
            result = media.invoke_metadata(
                url=args.url,
                playlist_mode=args.playlist_mode,
                timeout_sec=args.timeout_sec,
            )
        elif args.operation == "formats":
            result = media.invoke_formats(url=args.url, timeout_sec=args.timeout_sec)
        elif args.operation == "download":
            result = media.invoke_download(
                url=args.url,
                output_dir=args.output_dir,
                audio_only=args.audio_only,
                subs=args.subs,
                format_selector=args.format_selector,
                playlist_mode=args.playlist_mode,
                playlist_items=args.playlist_items,
                timeout_sec=args.timeout_sec,
            )
        elif args.operation == "probe":
            result = media.invoke_probe(input_path=args.input, timeout_sec=args.timeout_sec)
        elif args.operation == "clip":
            result = media.invoke_clip(
                input_path=args.input,
                start=args.start,
                end=args.end,
                output_path=args.output,
                timeout_sec=args.timeout_sec,
            )
        elif args.operation == "extract-audio":
            result = media.invoke_extract_audio(
                input_path=args.input,
                codec=args.codec,
                output_path=args.output,
                timeout_sec=args.timeout_sec,
            )
        elif args.operation == "remux":
            result = media.invoke_remux(
                input_path=args.input,
                container=args.container,
                output_path=args.output,
                timeout_sec=args.timeout_sec,
            )
        else:
            result = media.invoke_transcode(
                input_path=args.input,
                output_path=args.output,
                ffmpeg_args=args.ffmpeg_args,
                timeout_sec=args.timeout_sec,
            )
    except ValueError as exc:
        result = media.make_result(
            ok=False,
            tool=operation_tool(args.operation),
            operation=args.operation,
            exit_code=2,
            stderr=str(exc),
        )
    except Exception as exc:
        result = media.make_result(
            ok=False,
            tool=operation_tool(args.operation),
            operation=args.operation,
            exit_code=1,
            stderr=str(exc),
        )

    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
