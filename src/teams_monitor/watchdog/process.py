"""Checks whether the Teams process is running."""

from __future__ import annotations

import subprocess
from typing import Protocol

TASKLIST_TIMEOUT_SECONDS = 10.0


class ProcessProbe(Protocol):
    def is_running(self) -> bool | None:
        """True or False when known, None when the check itself failed."""
        ...


class TasklistProbe:
    """Uses the built-in Windows `tasklist` command, no extra dependencies."""

    def __init__(self, image_name: str) -> None:
        self._image_name = image_name

    def is_running(self) -> bool | None:
        command = ["tasklist", "/FI", f"IMAGENAME eq {self._image_name}", "/FO", "CSV", "/NH"]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=TASKLIST_TIMEOUT_SECONDS,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return self._image_name.lower() in result.stdout.lower()
