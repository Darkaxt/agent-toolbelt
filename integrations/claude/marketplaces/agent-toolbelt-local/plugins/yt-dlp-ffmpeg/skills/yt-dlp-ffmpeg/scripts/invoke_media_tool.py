import json
import sys
from pathlib import Path


def bootstrap_repo_src() -> None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        src_dir = parent / "src"
        if (parent / "pyproject.toml").exists() and (src_dir / "agent_toolbelt").exists():
            if str(src_dir) not in sys.path:
                sys.path.insert(0, str(src_dir))
            return
    raise RuntimeError("Could not locate the repository src/agent_toolbelt directory.")


bootstrap_repo_src()

from agent_toolbelt import media  # noqa: E402


def main() -> int:
    parser = media.build_parser()
    args = parser.parse_args()

    try:
        if args.operation == "download":
            result = media.invoke_download(
                url=args.url,
                output_dir=args.output_dir,
                audio_only=args.audio_only,
                subs=args.subs,
                format_selector=args.format_selector,
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
            tool="yt-dlp" if args.operation == "download" else "ffmpeg",
            operation=args.operation,
            exit_code=2,
            stderr=str(exc),
        )
    except Exception as exc:
        result = media.make_result(
            ok=False,
            tool="yt-dlp" if args.operation == "download" else "ffmpeg",
            operation=args.operation,
            exit_code=1,
            stderr=str(exc),
        )

    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
