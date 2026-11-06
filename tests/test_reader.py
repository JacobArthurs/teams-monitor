from __future__ import annotations

from pathlib import Path

import pytest

from teams_monitor.tailing import LineReader


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "MSTeams_1.log"


def test_read_before_stops_at_the_end_offset(path: Path) -> None:
    path.write_bytes(b"one\ntwo\nlater\n")
    assert LineReader().read_before(path, 8) == ["one", "two"]


def test_read_before_drops_an_incomplete_last_line(path: Path) -> None:
    path.write_bytes(b"one\ntwo\n")
    assert LineReader().read_before(path, 6) == ["one"]


def test_read_before_drops_the_cut_off_first_line_when_limited(path: Path) -> None:
    path.write_bytes(b"one\ntwo\nthree\n")
    assert LineReader(max_chunk=9).read_before(path, 14) == ["three"]


def test_read_before_handles_a_missing_file(path: Path) -> None:
    assert LineReader().read_before(path, 8) == []


def test_reads_complete_lines_and_reports_the_offset(path: Path) -> None:
    path.write_bytes(b"one\ntwo\n")
    result = LineReader().read_available(path, 0)
    assert result.lines == ["one", "two"]
    assert result.offset == 8


def test_starts_at_the_given_offset(path: Path) -> None:
    path.write_bytes(b"one\ntwo\n")
    assert LineReader().read_available(path, 4).lines == ["two"]


def test_nothing_new_returns_nothing(path: Path) -> None:
    path.write_bytes(b"one\n")
    result = LineReader().read_available(path, 4)
    assert result.lines == []
    assert result.offset == 4


def test_partial_line_waits_for_the_rest(path: Path) -> None:
    reader = LineReader()
    path.write_bytes(b"one\npart")
    first = reader.read_available(path, 0)
    assert first.lines == ["one"]
    assert first.offset == 4

    path.write_bytes(b"one\npartial\n")
    second = reader.read_available(path, first.offset)
    assert second.lines == ["partial"]
    assert second.offset == 12


def test_final_returns_the_partial_line(path: Path) -> None:
    path.write_bytes(b"one\npart")
    result = LineReader().read_available(path, 0, final=True)
    assert result.lines == ["one", "part"]
    assert result.offset == 8


def test_crlf_is_stripped(path: Path) -> None:
    path.write_bytes(b"one\r\ntwo\r\n")
    assert LineReader().read_available(path, 0).lines == ["one", "two"]


def test_blank_lines_are_kept(path: Path) -> None:
    path.write_bytes(b"one\n\ntwo\n")
    assert LineReader().read_available(path, 0).lines == ["one", "", "two"]


def test_unicode_line_separator_does_not_split_a_line(path: Path) -> None:
    path.write_bytes("onestill one\n".encode())
    assert LineReader().read_available(path, 0).lines == ["onestill one"]


def test_invalid_utf8_is_replaced(path: Path) -> None:
    path.write_bytes(b"bad \xff byte\n")
    assert LineReader().read_available(path, 0).lines == ["bad � byte"]


def test_truncated_file_restarts_at_zero(path: Path) -> None:
    path.write_bytes(b"new\n")
    result = LineReader().read_available(path, 100)
    assert result.lines == ["new"]
    assert result.offset == 4


def test_missing_file_keeps_the_offset(path: Path) -> None:
    result = LineReader().read_available(path, 42)
    assert result.lines == []
    assert result.offset == 42


def test_reads_across_chunks(path: Path) -> None:
    path.write_bytes(b"ab\ncd\nef\n")
    result = LineReader(max_chunk=4).read_available(path, 0)
    assert result.lines == ["ab", "cd", "ef"]
    assert result.offset == 9


def test_line_larger_than_a_chunk_is_skipped(path: Path) -> None:
    path.write_bytes(b"x" * 20 + b"\nok\n")
    result = LineReader(max_chunk=8).read_available(path, 0)
    assert result.lines == ["xxxx", "ok"]
    assert result.offset == 24


def test_size(path: Path) -> None:
    path.write_bytes(b"12345")
    assert LineReader.size(path) == 5


def test_size_of_a_missing_file_is_zero(path: Path) -> None:
    assert LineReader.size(path) == 0
