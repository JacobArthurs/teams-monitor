from __future__ import annotations

from datetime import UTC, datetime

import pytest
from helpers import load_samples, stamp

from teams_monitor.parsing import MAX_LINE_LENGTH, parse_line, parse_timestamp

# Teams writes UTC clock time and labels it with the local offset, so each label is ignored.
EXPECTED = {
    "incoming_call": (datetime(2026, 11, 3, 17, 53, 45, 38815, UTC), "INFO"),
    "call_answered": (datetime(2026, 10, 13, 17, 41, 22, 201226, UTC), "INFO"),
    "call_ended": (datetime(2026, 11, 3, 17, 54, 6, 973853, UTC), "INFO"),
    "new_message": (datetime(2026, 10, 23, 14, 5, 44, 309669, UTC), "DBG"),
    "unread_count": (datetime(2026, 11, 5, 18, 6, 50, 596199, UTC), "INFO"),
    "notification_popup": (datetime(2026, 11, 3, 17, 53, 45, 56458, UTC), "INFO"),
    "app_started": (datetime(2026, 10, 6, 12, 47, 39, 30894, UTC), "INFO"),
    "app_quit": (datetime(2026, 10, 21, 17, 16, 24, 952252, UTC), "INFO"),
}


def test_every_sample_has_an_expectation() -> None:
    assert set(load_samples()) == set(EXPECTED)


@pytest.mark.parametrize("name", EXPECTED)
def test_real_samples_parse(name: str) -> None:
    line = parse_line(load_samples()[name])
    ts, level = EXPECTED[name]
    assert line is not None
    assert line.ts == ts
    assert line.level == level


@pytest.mark.parametrize("name", EXPECTED)
def test_log_ts_is_the_same_instant_as_ts(name: str) -> None:
    # The text of log_ts depends on the machine's timezone, so only the instant is compared.
    line = parse_line(load_samples()[name])
    assert line is not None
    assert datetime.fromisoformat(line.log_ts) == line.ts


def test_message_is_captured_without_the_extra_space_after_dbg() -> None:
    line = parse_line(load_samples()["new_message"])
    assert line is not None
    assert line.msg.startswith("TaskbarBadgeServiceLegacy:Work:")


def test_offset_label_is_ignored() -> None:
    assert parse_timestamp("2026-11-03T17:00:00-05:00") == parse_timestamp(
        "2026-11-03T17:00:00+09:00"
    )


def test_timestamp_with_excess_fraction_digits_is_accepted() -> None:
    ts = parse_timestamp("2026-11-03T17:53:45.0388151234-05:00")
    assert ts == datetime(2026, 11, 3, 17, 53, 45, 38815, UTC)


def test_impossible_date_keeps_the_original_text() -> None:
    line = parse_line("2026-13-45T00:00:00.000000-05:00 0x1 <INFO> hello")
    assert line is not None
    assert line.ts is None
    assert line.log_ts == "2026-13-45T00:00:00.000000-05:00"
    assert line.msg == "hello"


@pytest.mark.parametrize("year", ["0001", "9999"])
def test_year_the_os_cannot_convert_keeps_the_original_text(year: str) -> None:
    ts = f"{year}-06-15T00:00:00.000000+00:00"
    line = parse_line(f"{ts} 0x1 <INFO> hello")
    assert line is not None
    assert line.log_ts == ts
    assert line.msg == "hello"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "    at some.continuation.line()",
        "not a log line",
        f"{stamp()} <INFO> missing thread",
        f"{stamp()} 0xZZ <INFO> bad thread",
        f"{stamp()} 0x00AB <INFO> uppercase hex thread",
        f"{stamp()} 0x1 <info> lowercase level",
        f"{stamp()} 0x1 INFO no brackets",
        "2026-11-03T17:53:45.000000 0x1 <INFO> no offset",
        f"prefix {stamp()} 0x1 <INFO> leading text",
    ],
)
def test_lines_not_in_the_expected_format_are_rejected(raw: str) -> None:
    assert parse_line(raw) is None


def test_long_lines_are_truncated_before_matching() -> None:
    prefix = f"{stamp()} 0x1 <INFO> "
    line = parse_line(prefix + "x" * (MAX_LINE_LENGTH * 2))
    assert line is not None
    assert len(prefix) + len(line.msg) == MAX_LINE_LENGTH
