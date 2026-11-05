"""Reads newly appended complete lines from a file, starting at a byte offset."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_MAX_CHUNK = 1 << 20


def _split_lines(data: bytes) -> list[str]:
    # Not str.splitlines, which also breaks on characters like U+2028 inside a log line.
    lines = [line.removesuffix("\r") for line in data.decode("utf-8", "replace").split("\n")]
    if not lines[-1]:
        lines.pop()
    return lines


@dataclass(frozen=True, slots=True)
class ReadResult:
    lines: list[str]
    offset: int


class LineReader:
    """Opens, reads and closes on every call, so Teams can rotate or delete the file freely."""

    def __init__(self, max_chunk: int = DEFAULT_MAX_CHUNK) -> None:
        self._max_chunk = max_chunk

    @staticmethod
    def size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def read_available(self, path: Path, offset: int, final: bool = False) -> ReadResult:
        """Read complete lines from offset. With final, also return an unterminated last line."""
        try:
            size = path.stat().st_size
        except OSError:
            return ReadResult([], offset)

        if size < offset:
            log.info("%s was truncated, restarting at offset 0", path.name)
            offset = 0

        lines: list[str] = []
        while offset < size:
            data = self._read_at(path, offset, min(size - offset, self._max_chunk))
            if not data:
                break
            end = data.rfind(b"\n")
            if end == -1:
                if len(data) < self._max_chunk:
                    if final:
                        offset += len(data)
                        lines.extend(_split_lines(data))
                    break  # incomplete last line, wait for the rest
                offset += len(data)  # a single line larger than a chunk, skip it
                continue
            offset += end + 1
            lines.extend(_split_lines(data[: end + 1]))
        return ReadResult(lines, offset)

    def read_before(self, path: Path, end: int) -> list[str]:
        """Complete lines from up to one chunk of the file just before the end offset."""
        start = max(0, end - self._max_chunk)
        data = self._read_at(path, start, end - start)
        last_newline = data.rfind(b"\n")
        if last_newline == -1:
            return []
        lines = _split_lines(data[: last_newline + 1])
        return lines[1:] if start > 0 else lines  # a cut-off first line is not usable

    @staticmethod
    def _read_at(path: Path, offset: int, length: int) -> bytes:
        try:
            with path.open("rb") as handle:
                handle.seek(offset)
                return handle.read(length)
        except OSError as exc:
            log.debug("read failed for %s: %s", path.name, exc)
            return b""
