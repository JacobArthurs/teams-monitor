"""Follows the newest Teams log file across rotations."""

from __future__ import annotations

import logging
from pathlib import Path

from teams_monitor.tailing.locator import LogLocator
from teams_monitor.tailing.reader import LineReader

log = logging.getLogger(__name__)


class LogTailer:
    """Remembers how far each file was read, so returning to one never replays it.

    Files present at startup count as already read. Any file that appears later is new
    and is read from its beginning.
    """

    def __init__(
        self,
        locator: LogLocator,
        reader: LineReader,
        from_start: bool = False,
    ) -> None:
        self._locator = locator
        self._reader = reader
        self._from_start = from_start
        self._started = False
        self._path: Path | None = None
        self._offsets: dict[Path, int] = {}

    def poll(self) -> list[str]:
        """Return complete lines written since the previous poll."""
        if not self._started:
            self._start()

        newest = self._locator.newest()
        if newest is None:
            return []

        lines: list[str] = []
        if newest != self._path:
            if self._path is not None:
                lines += self._drain(final=True)  # finish the file Teams just left
                log.info("rotated %s to %s", self._path.name, newest.name)
            self._path = newest
            self._forget_deleted_files()
            log.info("tailing %s from offset %d", newest.name, self._offsets.get(newest, 0))
        lines += self._drain()
        return lines

    def _start(self) -> None:
        self._started = True
        for path in self._locator.existing():
            self._offsets[path] = self._reader.size(path)
        if self._from_start:
            newest = self._locator.newest()
            if newest is not None:
                self._offsets[newest] = 0

    def _forget_deleted_files(self) -> None:
        existing = set(self._locator.existing())
        self._offsets = {path: offset for path, offset in self._offsets.items() if path in existing}

    def _drain(self, final: bool = False) -> list[str]:
        if self._path is None:
            return []
        offset = self._offsets.get(self._path, 0)
        result = self._reader.read_available(self._path, offset, final=final)
        self._offsets[self._path] = result.offset
        return result.lines
