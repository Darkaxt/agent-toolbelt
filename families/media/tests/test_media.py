import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "media" / "src"
for path in (CORE_SRC, FAMILY_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_toolbelt_media import cli, media


class MediaTests(unittest.TestCase):
    def test_resolve_binary_prefers_explicit_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            yt = Path(temp_dir) / "yt-dlp.exe"
            ffmpeg = Path(temp_dir) / "ffmpeg.exe"
            ffprobe = Path(temp_dir) / "ffprobe.exe"
            for path in (yt, ffmpeg, ffprobe):
                path.write_text("placeholder", encoding="utf-8")

            self.assertEqual(Path(media.resolve_binary("yt-dlp", explicit_path=str(yt))), yt)
            self.assertEqual(Path(media.resolve_binary("ffmpeg", explicit_path=str(ffmpeg))), ffmpeg)
            self.assertEqual(Path(media.resolve_binary("ffprobe", explicit_path=str(ffprobe))), ffprobe)

    def test_validate_public_url_rejects_non_public_targets(self):
        with self.assertRaisesRegex(ValueError, "Only public http\\(s\\) URLs are allowed"):
            media.validate_public_url("file:///tmp/demo.mp4")
        with self.assertRaisesRegex(ValueError, "Localhost URLs are not allowed"):
            media.validate_public_url("http://127.0.0.1/demo")
        with self.assertRaisesRegex(ValueError, "Private-network IP targets are not allowed"):
            media.validate_public_url("http://192.168.1.8/demo")
        with self.assertRaisesRegex(ValueError, "`.local` hosts are not allowed"):
            media.validate_public_url("https://printer.local/demo")

    def test_classify_url_returns_structured_safety_metadata(self):
        accepted = media.invoke_classify_url(url="https://Example.COM/watch?v=1")
        rejected = media.invoke_classify_url(url="http://127.0.0.1/demo")

        self.assertTrue(accepted["ok"])
        self.assertEqual(accepted["tool"], "yt-dlp")
        self.assertEqual(accepted["operation"], "classify-url")
        self.assertEqual(accepted["metadata"]["scheme"], "https")
        self.assertEqual(accepted["metadata"]["host"], "example.com")
        self.assertEqual(accepted["metadata"]["safety_status"], "public")
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["exit_code"], 2)
        self.assertEqual(rejected["metadata"]["safety_status"], "rejected")
        self.assertIn("Localhost URLs are not allowed", rejected["metadata"]["reason"])

    def test_metadata_uses_explicit_playlist_modes_without_artifacts(self):
        calls = []

        def fake_run_process(command, **kwargs):
            calls.append(command)
            return media.subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "id": "abc123",
                        "title": "Demo",
                        "duration": 12.5,
                        "extractor": "generic",
                        "webpage_url": "https://example.com/video",
                    }
                ),
                stderr="",
            )

        original_run = media.run_process
        original_resolve = media.resolve_binary
        media.run_process = fake_run_process
        media.resolve_binary = lambda name, explicit_path=None: f"C:/Tools/{name}.exe"
        try:
            single = media.invoke_metadata(url="https://example.com/video", playlist_mode="single", timeout_sec=30)
            flat = media.invoke_metadata(url="https://example.com/playlist", playlist_mode="flat", timeout_sec=30)
            full = media.invoke_metadata(url="https://example.com/playlist", playlist_mode="full", timeout_sec=30)
        finally:
            media.run_process = original_run
            media.resolve_binary = original_resolve

        self.assertTrue(single["ok"])
        self.assertEqual(single["operation"], "metadata")
        self.assertEqual(single["artifacts"], [])
        self.assertEqual(single["metadata"]["playlist_mode"], "single")
        self.assertIn("--no-playlist", calls[0])
        self.assertIn("--flat-playlist", calls[1])
        self.assertNotIn("--no-playlist", calls[1])
        self.assertIn("--yes-playlist", calls[2])
        self.assertNotIn("--flat-playlist", calls[2])

    def test_formats_normalizes_structured_ytdlp_formats(self):
        def fake_run_process(command, **kwargs):
            return media.subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "id": "abc123",
                        "title": "Demo",
                        "formats": [
                            {
                                "format_id": "18",
                                "ext": "mp4",
                                "resolution": "640x360",
                                "fps": 30,
                                "vcodec": "avc1",
                                "acodec": "mp4a",
                                "tbr": 420.5,
                                "filesize": 123456,
                                "protocol": "https",
                                "format_note": "360p",
                            },
                            {
                                "format_id": "251",
                                "ext": "webm",
                                "vcodec": "none",
                                "acodec": "opus",
                            },
                        ],
                    }
                ),
                stderr="",
            )

        original_run = media.run_process
        original_resolve = media.resolve_binary
        media.run_process = fake_run_process
        media.resolve_binary = lambda name, explicit_path=None: f"C:/Tools/{name}.exe"
        try:
            result = media.invoke_formats(url="https://example.com/video", timeout_sec=30)
        finally:
            media.run_process = original_run
            media.resolve_binary = original_resolve

        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"], "formats")
        self.assertEqual(result["metadata"]["id"], "abc123")
        self.assertEqual(result["metadata"]["formats"][0]["format_id"], "18")
        self.assertEqual(result["metadata"]["formats"][0]["filesize"], 123456)
        self.assertEqual(result["metadata"]["formats"][1]["vcodec"], "none")

    def test_download_normalizes_metadata_and_artifacts(self):
        calls = []

        def fake_run_process(command, **kwargs):
            calls.append(command)
            if "--dump-single-json" in command:
                return media.subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps(
                        {
                            "id": "abc123",
                            "title": "Demo",
                            "duration": 12.5,
                            "extractor": "generic",
                            "webpage_url": "https://example.com/video",
                        }
                    ),
                    stderr="",
                )
            return media.subprocess.CompletedProcess(
                command,
                0,
                stdout="C:\\temp\\Demo [abc123].mp4\nC:\\temp\\Demo [abc123].en.vtt\n",
                stderr="[download] 100%",
            )

        original_run = media.run_process
        original_resolve = media.resolve_binary
        media.run_process = fake_run_process
        media.resolve_binary = lambda name, explicit_path=None: f"C:/Tools/{name}.exe"
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                result = media.invoke_download(
                    url="https://example.com/video",
                    output_dir=temp_dir,
                    audio_only=False,
                    subs=True,
                    format_selector="18",
                    timeout_sec=30,
                )
        finally:
            media.run_process = original_run
            media.resolve_binary = original_resolve

        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "yt-dlp")
        self.assertEqual(result["operation"], "download")
        self.assertEqual(result["metadata"]["title"], "Demo")
        self.assertEqual(result["metadata"]["id"], "abc123")
        self.assertEqual(len(result["artifacts"]), 2)
        self.assertEqual(len(calls), 2)
        self.assertIn("--no-playlist", calls[0])
        self.assertIn("--no-playlist", calls[1])

    def test_download_full_playlist_mode_and_items_are_explicit(self):
        calls = []

        def fake_run_process(command, **kwargs):
            calls.append(command)
            if "--dump-single-json" in command:
                return media.subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps({"id": "playlist", "title": "Playlist", "webpage_url": "https://example.com/list"}),
                    stderr="",
                )
            return media.subprocess.CompletedProcess(command, 0, stdout="C:\\temp\\one.mp4\n", stderr="")

        original_run = media.run_process
        original_resolve = media.resolve_binary
        media.run_process = fake_run_process
        media.resolve_binary = lambda name, explicit_path=None: f"C:/Tools/{name}.exe"
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                result = media.invoke_download(
                    url="https://example.com/list",
                    output_dir=temp_dir,
                    audio_only=False,
                    subs=False,
                    format_selector=None,
                    playlist_mode="full",
                    playlist_items="1-3",
                    timeout_sec=30,
                )
        finally:
            media.run_process = original_run
            media.resolve_binary = original_resolve

        self.assertTrue(result["ok"])
        self.assertIn("--yes-playlist", calls[0])
        self.assertIn("--yes-playlist", calls[1])
        self.assertIn("--playlist-items", calls[1])
        self.assertIn("1-3", calls[1])

    def test_playlist_items_without_full_playlist_mode_fails_closed(self):
        result = media.invoke_download(
            url="https://example.com/list",
            output_dir=None,
            audio_only=False,
            subs=False,
            format_selector=None,
            playlist_mode="single",
            playlist_items="1-3",
            timeout_sec=30,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 2)
        self.assertIn("--playlist-items requires --playlist-mode full", result["stderr"])

    def test_probe_normalizes_ffprobe_json(self):
        def fake_run_process(command, **kwargs):
            return media.subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "format": {
                            "filename": "sample.mp4",
                            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                            "duration": "3.000000",
                            "size": "45012",
                            "bit_rate": "120032",
                        },
                        "streams": [
                            {
                                "index": 0,
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 320,
                                "height": 240,
                            },
                            {
                                "index": 1,
                                "codec_type": "audio",
                                "codec_name": "aac",
                                "channels": 2,
                                "sample_rate": "44100",
                            },
                        ],
                    }
                ),
                stderr="",
            )

        original_run = media.run_process
        original_resolve = media.resolve_binary
        media.run_process = fake_run_process
        media.resolve_binary = lambda name, explicit_path=None: f"C:/Tools/{name}.exe"
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                sample = Path(temp_dir) / "sample.mp4"
                sample.write_bytes(b"demo")
                result = media.invoke_probe(input_path=str(sample), timeout_sec=15)
        finally:
            media.run_process = original_run
            media.resolve_binary = original_resolve

        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "ffprobe")
        self.assertEqual(result["operation"], "probe")
        self.assertEqual(result["metadata"]["format"]["duration"], 3.0)
        self.assertEqual(result["metadata"]["streams"][0]["codec_type"], "video")
        self.assertEqual(result["metadata"]["streams"][1]["codec_name"], "aac")

    def test_clip_extract_audio_and_remux_report_output_artifacts(self):
        def fake_run_process(command, **kwargs):
            Path(command[-1]).write_bytes(b"out")
            return media.subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        original_run = media.run_process
        original_resolve = media.resolve_binary
        media.run_process = fake_run_process
        media.resolve_binary = lambda name, explicit_path=None: f"C:/Tools/{name}.exe"
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                input_path = Path(temp_dir) / "sample.mp4"
                input_path.write_bytes(b"in")

                clip_result = media.invoke_clip(
                    input_path=str(input_path),
                    start="00:00:00",
                    end="00:00:01",
                    output_path=None,
                    timeout_sec=30,
                )
                audio_result = media.invoke_extract_audio(
                    input_path=str(input_path),
                    codec="mp3",
                    output_path=None,
                    timeout_sec=30,
                )
                remux_result = media.invoke_remux(
                    input_path=str(input_path),
                    container="mkv",
                    output_path=None,
                    timeout_sec=30,
                )
        finally:
            media.run_process = original_run
            media.resolve_binary = original_resolve

        self.assertTrue(clip_result["ok"])
        self.assertTrue(audio_result["ok"])
        self.assertTrue(remux_result["ok"])
        self.assertTrue(clip_result["artifacts"][0].endswith(".mp4"))
        self.assertTrue(audio_result["artifacts"][0].endswith(".mp3"))
        self.assertTrue(remux_result["artifacts"][0].endswith(".mkv"))

    def test_missing_binary_returns_readable_failure(self):
        original_resolve = media.resolve_binary
        media.resolve_binary = lambda name, explicit_path=None: None
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                sample = Path(temp_dir) / "sample.mp4"
                sample.write_bytes(b"demo")
                result = media.invoke_probe(input_path=str(sample), timeout_sec=15)
        finally:
            media.resolve_binary = original_resolve

        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 127)
        self.assertIn("ffprobe", result["stderr"])

    def test_ffmpeg_failure_is_reported_cleanly(self):
        original_resolve = media.resolve_binary
        original_run = media.run_process
        media.resolve_binary = lambda name, explicit_path=None: f"C:/Tools/{name}.exe"
        media.run_process = lambda command, **kwargs: media.subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="Unknown encoder",
        )
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                input_path = Path(temp_dir) / "sample.mp4"
                input_path.write_bytes(b"in")
                result = media.invoke_extract_audio(
                    input_path=str(input_path),
                    codec="mp3",
                    output_path=None,
                    timeout_sec=30,
                )
        finally:
            media.resolve_binary = original_resolve
            media.run_process = original_run

        self.assertFalse(result["ok"])
        self.assertEqual(result["tool"], "ffmpeg")
        self.assertIn("Unknown encoder", result["stderr"])

    def test_youtube_download_failure_is_contextualized(self):
        original_resolve = media.resolve_binary
        original_run = media.run_process
        media.resolve_binary = lambda name, explicit_path=None: f"C:/Tools/{name}.exe"
        media.run_process = lambda command, **kwargs: media.subprocess.CompletedProcess(
            command,
            1,
            stdout="null",
            stderr="ERROR: [youtube] KFisvc-AMII: Requested format is not available. Use --list-formats for a list of available formats",
        )
        try:
            result = media.invoke_download(
                url="https://youtu.be/KFisvc-AMII",
                output_dir=None,
                audio_only=False,
                subs=False,
                format_selector=None,
                timeout_sec=30,
            )
        finally:
            media.resolve_binary = original_resolve
            media.run_process = original_run

        self.assertFalse(result["ok"])
        self.assertIn("YouTube did not expose downloadable media formats", result["stderr"])

    def test_package_cli_returns_json_for_url_validation_errors(self):
        with patch("sys.stdout") as fake_stdout:
            exit_code = cli.main(["metadata", "--url", "file:///tmp/demo.mp4"])

        payload = json.loads("".join(call.args[0] for call in fake_stdout.write.call_args_list))
        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["operation"], "metadata")
        self.assertIn("Only public http(s) URLs are allowed", payload["stderr"])

    def test_codex_skill_wrapper_returns_json_for_url_validation_errors(self):
        script = REPO_ROOT / "families" / "media" / "codex" / "skills" / "yt-dlp-ffmpeg" / "scripts" / "invoke_media_tool.py"
        completed = subprocess.run(
            [sys.executable, str(script), "metadata", "--url", "file:///tmp/demo.mp4"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["operation"], "metadata")
        self.assertIn("Only public http(s) URLs are allowed", payload["stderr"])


if __name__ == "__main__":
    unittest.main()
