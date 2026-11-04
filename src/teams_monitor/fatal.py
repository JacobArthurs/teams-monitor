"""Makes fatal errors visible when there is no console, as under pythonw.exe."""

from __future__ import annotations

import ctypes
import os
import sys
import tempfile
from pathlib import Path

_MB_ICONERROR = 0x10
_MB_SETFOREGROUND = 0x10000


def report_without_console(message: str) -> None:
    """Save the error to a file and show a dialog. Does nothing if there is a console."""
    if sys.stderr is not None:
        return
    path = _write_error_file(message)
    saved = f"\n\nSaved to {path}" if path is not None else ""
    _show_message_box(f"{message}{saved}")


def _write_error_file(message: str) -> Path | None:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    path = Path(base) / "teams-monitor" / "startup-error.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(message + "\n", encoding="utf-8")
    except OSError:
        return None
    return path


def _show_message_box(text: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            None, text, "teams-monitor", _MB_ICONERROR | _MB_SETFOREGROUND
        )
    except (AttributeError, OSError):
        pass  # not on Windows, or no desktop to show it on: the file is all there is
