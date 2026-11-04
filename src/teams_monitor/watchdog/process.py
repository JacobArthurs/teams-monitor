"""Checks whether the Teams process is running."""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class ProcessProbe(ABC):
    @abstractmethod
    def is_running(self) -> bool | None:
        """True or False when known, None when the check itself failed."""


class TasklistProbe(ProcessProbe):
    """Uses the built-in Windows `tasklist` command, no extra dependencies."""

    def __init__(
        self,
        image_name: str,
        runner: Runner = subprocess.run,
        timeout: float = 10.0,
    ) -> None:
        self._image_name = image_name
        self._runner = runner
        self._timeout = timeout

    def is_running(self) -> bool | None:
        command = ["tasklist", "/FI", f"IMAGENAME eq {self._image_name}", "/FO", "CSV", "/NH"]
        try:
            result = self._runner(
                command,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return self._image_name.lower() in result.stdout.lower()
