from __future__ import annotations

from pathlib import Path

LOG_PATTERN = "MSTeams_*.log"


class LogLocator:
    """Teams starts a new file per launch and at about 2.1 MB, so the newest one is live."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def existing(self) -> list[Path]:
        try:
            return list(self._directory.glob(LOG_PATTERN))
        except OSError:
            return []

    def newest(self) -> Path | None:
        best: tuple[tuple[float, str], Path] | None = None
        for path in self.existing():
            try:
                key = (path.stat().st_mtime, path.name)
            except OSError:
                continue  # file vanished between glob and stat
            if best is None or key > best[0]:
                best = (key, path)
        return best[1] if best else None
