"""Capture the real non-elevating dialog and report viewport/layout evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent_toolbelt_windows_elevation_gate.dialog import ExplanationDialog
from agent_toolbelt_windows_elevation_gate.engine import prepare


def inspect(width=None, height=None, screenshot=None, capture_helper=None):
    request = prepare([sys.executable, "-c", "print('Read-only identity check')"],
                      cwd=str(Path.cwd()), task="Verify administrator identity",
                      thread_name="Skill Creator", reason="Confirm the administrator token before the authorized action.",
                      changes="Read-only verification. No files, configuration, accounts or services will change.",
                      targets=["Current Windows process identity"])
    dialog = ExplanationDialog(request, preview=True)
    root = dialog.root
    try:
        if width and height:
            root.geometry(f"{width}x{height}+40+40")
        root.update()
        metrics = {
            "preview_only": True, "topmost": bool(root.attributes("-topmost")),
            "width": root.winfo_width(), "height": root.winfo_height(),
            "screen": [root.winfo_screenwidth(), root.winfo_screenheight()],
            "footer_bottom": dialog.footer.winfo_y() + dialog.footer.winfo_height(),
            "cancel_visible": bool(dialog.cancel.winfo_viewable()),
            "accept_visible": bool(dialog.accept.winfo_viewable()),
            "preview_button": dialog.accept.cget("text"),
            "preview_button_enabled": dialog.accept.cget("state") == "normal",
            "buttons_within_window": all(
                button.winfo_rootx() >= root.winfo_rootx() and
                button.winfo_rootx() + button.winfo_width() <= root.winfo_rootx() + root.winfo_width()
                for button in (dialog.accept, dialog.cancel)),
            "content_scrollable": dialog.canvas.bbox("all")[3] > dialog.canvas.winfo_height(),
            "command_exact": dialog.command.get("1.0", "end-1c") == subprocess.list2cmdline(request["command"]),
        }
        assert metrics["footer_bottom"] <= metrics["height"]
        assert metrics["cancel_visible"] and metrics["command_exact"] and metrics["topmost"]
        assert metrics["buttons_within_window"] and metrics["preview_button_enabled"]
        assert metrics["preview_button"] == "Looks Good"
        if screenshot:
            if not capture_helper:
                raise ValueError("An explicit installed screenshot helper is required")
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            region = f"{root.winfo_rootx()},{root.winfo_rooty()},{root.winfo_width()},{root.winfo_height()}"
            subprocess.run(["powershell.exe", "-NoProfile", "-File", str(capture_helper),
                            "-Path", str(screenshot.resolve()), "-Region", region], check=True)
            metrics["screenshot"] = str(screenshot.resolve())
        return metrics
    finally:
        dialog.finish(False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--capture-helper", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.width, args.height, args.screenshot, args.capture_helper), indent=2))
