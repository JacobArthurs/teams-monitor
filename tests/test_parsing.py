from __future__ import annotations

from datetime import UTC, datetime

import pytest
from helpers import load_samples, stamp

from teams_monitor.parsing import MAX_LINE_LENGTH, LineParser, parse_timestamp

# Teams writes UTC clock time and labels it with the local offset, so each label is ignored.
EXPECTED = {
    "incoming_call": (datetime(2026, 11, 3, 17, 53, 45, 38815, UTC), "0x00003e44", "INFO"),
    "call_answered": (datetime(2026, 10, 13, 17, 41, 22, 201226, UTC), "0x000048d8", "INFO"),
    "call_ended": (datetime(2026, 11, 3, 17, 54, 6, 973853, UTC), "0x00003e44", "INFO"),
    "new_message": (datetime(2026, 10, 23, 14, 5, 44, 309669, UTC), "0x00009494", "DBG"),
    "notification_popup": (datetime(2026, 11, 3, 17, 53, 45, 56458, UTC), "0x000040ec", "INFO"),
    "app_started": (datetime(2026, 10, 6, 12, 47, 39, 30894, UTC), "0x00004ac8", "INFO"),
    "app_quit": (datetime(2026, 10, 21, 17, 16, 24, 952252, UTC), "0x000009b4", "INFO"),
}


def test_every_sample_has_an_expectation() -> None:
    assert set(load_samples()) == set(EXPECTED)


@pytest.mark.parametrize("name", EXPECTED)
def test_real_samples_parse(name: str) -> None:
    line = LineParser().parse(load_samples()[name])
    ts, thread, level = EXPECTED[name]
    assert line is not None
    assert line.ts == ts
    assert line.thread == thread
    assert line.level == level


@pytest.mark.parametrize("name", EXPECTED)
def test_log_ts_is_the_same_instant_as_ts(name: str) -> None:
    # The text of log_ts depends on the machine's timezone, so only the instant is compared.
    line = LineParser().parse(load_samples()[name])
    assert line is not None
    assert datetime.fromisoformat(line.log_ts) == line.ts


def test_message_is_captured_without_the_extra_space_after_dbg() -> None:
    line = LineParser().parse(load_samples()["new_message"])
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
    line = LineParser().parse("2026-13-45T00:00:00.000000-05:00 0x1 <INFO> hello")
    assert line is not None
    assert line.ts is None
    assert line.log_ts == "2026-13-45T00:00:00.000000-05:00"
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
    assert LineParser().parse(raw) is None


def test_long_lines_are_truncated_before_matching() -> None:
    prefix = f"{stamp()} 0x1 <INFO> "
    line = LineParser().parse(prefix + "x" * (MAX_LINE_LENGTH * 2))
    assert line is not None
    assert len(prefix) + len(line.msg) == MAX_LINE_LENGTH


def test_custom_max_length_is_honored() -> None:
    prefix = f"{stamp()} 0x1 <INFO> "
    line = LineParser(max_length=len(prefix) + 3).parse(prefix + "abcdef")
    assert line is not None
    assert line.msg == "abc"
