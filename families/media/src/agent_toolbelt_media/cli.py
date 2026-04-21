import json
import sys

from . import media


def main(argv: list[str] | None = None) -> int:
    parser = media.build_parser()
    args = parser.parse_args(argv)

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

    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))
