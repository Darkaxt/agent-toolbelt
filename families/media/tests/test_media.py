import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "media" / "src"
for path in (CORE_SRC, FAMILY_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_toolbelt_media import media


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


if __name__ == "__main__":
    unittest.main()
