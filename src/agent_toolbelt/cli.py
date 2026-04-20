import argparse
import json
import sys

from . import everything, gemini, media, uvrun


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent-friendly local toolbelt.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gemini_url = subparsers.add_parser("gemini-url", help="Inspect a public URL with Gemini.")
    gemini_url.add_argument("--url", required=True)
    gemini_url.add_argument("--instruction", required=True)
    gemini_url.add_argument("--model")
    gemini_url.add_argument("--timeout-sec", type=int, default=180)
    gemini_url.add_argument("--output", choices=("json", "text"), default="json")

    gemini_research = subparsers.add_parser(
        "gemini-research",
        help="Run an independent Gemini research cross-check.",
    )
    gemini_research.add_argument("--question", required=True)
    gemini_research.add_argument("--model")
    gemini_research.add_argument("--timeout-sec", type=int, default=180)
    gemini_research.add_argument("--output", choices=("json", "text"), default="json")

    everything_parser = subparsers.add_parser(
        "everything",
        help="Find filenames and paths with Everything-first lookup.",
    )
    everything_parser.add_argument("--query", required=True)
    everything_parser.add_argument("--max-results", type=int, default=everything.DEFAULT_MAX_RESULTS)
    everything_parser.add_argument("--match-path", action="store_true")
    everything_parser.add_argument(
        "--mode",
        choices=("global", "repo-local", "path-resolve", "dir-scope"),
        default="global",
    )
    everything_parser.add_argument("--root")
    everything_parser.add_argument("--es-path")

    uvrun_parser = subparsers.add_parser(
        "uvrun",
        help="Route standalone Python scripts through uvrun when appropriate.",
    )
    uvrun_parser.add_argument("uvrun_args", nargs=argparse.REMAINDER)

    media_parser = subparsers.add_parser("media", help="Run media helper commands.")
    media_subparsers = media_parser.add_subparsers(dest="operation", required=True)

    media_download = media_subparsers.add_parser("download")
    media_download.add_argument("--url", required=True)
    media_download.add_argument("--output-dir")
    media_download.add_argument("--audio-only", action="store_true")
    media_download.add_argument("--subs", action="store_true")
    media_download.add_argument("--format", dest="format_selector")
    media_download.add_argument("--timeout-sec", type=int, default=media.DEFAULT_DOWNLOAD_TIMEOUT_SEC)

    media_probe = media_subparsers.add_parser("probe")
    media_probe.add_argument("--input", required=True)
    media_probe.add_argument("--timeout-sec", type=int, default=media.DEFAULT_PROBE_TIMEOUT_SEC)

    media_clip = media_subparsers.add_parser("clip")
    media_clip.add_argument("--input", required=True)
    media_clip.add_argument("--start", required=True)
    media_clip.add_argument("--end", required=True)
    media_clip.add_argument("--output")
    media_clip.add_argument("--timeout-sec", type=int, default=media.DEFAULT_MEDIA_TIMEOUT_SEC)

    media_extract = media_subparsers.add_parser("extract-audio")
    media_extract.add_argument("--input", required=True)
    media_extract.add_argument("--codec", default="mp3", choices=sorted(media.AUDIO_CODEC_SETTINGS))
    media_extract.add_argument("--output")
    media_extract.add_argument("--timeout-sec", type=int, default=media.DEFAULT_MEDIA_TIMEOUT_SEC)

    media_remux = media_subparsers.add_parser("remux")
    media_remux.add_argument("--input", required=True)
    media_remux.add_argument("--container", required=True)
    media_remux.add_argument("--output")
    media_remux.add_argument("--timeout-sec", type=int, default=media.DEFAULT_MEDIA_TIMEOUT_SEC)

    media_transcode = media_subparsers.add_parser("transcode")
    media_transcode.add_argument("--input", required=True)
    media_transcode.add_argument("--output")
    media_transcode.add_argument("--timeout-sec", type=int, default=media.DEFAULT_MEDIA_TIMEOUT_SEC)
    media_transcode.add_argument("ffmpeg_args", nargs=argparse.REMAINDER)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "gemini-url":
        result = gemini.invoke_gemini_url(
            url=args.url,
            instruction=args.instruction,
            model=args.model,
            timeout_sec=args.timeout_sec,
        )
        if args.output == "text":
            print(result["response"])
        else:
            print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    if args.command == "gemini-research":
        result = gemini.invoke_gemini_research(
            question=args.question,
            model=args.model,
            timeout_sec=args.timeout_sec,
        )
        if args.output == "text":
            print(result["response"])
        else:
            print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    if args.command == "everything":
        result = everything.lookup(
            query=args.query,
            mode=args.mode,
            root=args.root,
            max_results=args.max_results,
            match_path=args.match_path,
            es_path=args.es_path,
        )
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    if args.command == "uvrun":
        parsed_uvrun = uvrun.parse_args(args.uvrun_args)
        result = uvrun.invoke_script(
            script=parsed_uvrun.script,
            script_args=parsed_uvrun.script_args,
            cwd=parsed_uvrun.cwd,
            timeout_sec=parsed_uvrun.timeout_sec,
            check_only=parsed_uvrun.check,
        )
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

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
