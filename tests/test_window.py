from __future__ import annotations

from datetime import time

import pytest

from teams_monitor.window import ActiveWindow


def test_parse() -> None:
    assert ActiveWindow.parse("08:00-18:30") == ActiveWindow(time(8), time(18, 30))


def test_parse_allows_spaces() -> None:
    assert ActiveWindow.parse(" 08:00 - 18:00 ") == ActiveWindow(time(8), time(18))


@pytest.mark.parametrize(
    "text",
    ["", "08:00", "08:00-", "-18:00", "8am-6pm", "25:00-26:00", "08:00-18:00-20:00", "08:60-09:00"],
)
def test_parse_rejects_bad_text(text: str) -> None:
    with pytest.raises(ValueError, match="expected HH:MM-HH:MM"):
        ActiveWindow.parse(text)


def test_parse_rejects_equal_start_and_end() -> None:
    with pytest.raises(ValueError, match="start and end must differ"):
        ActiveWindow.parse("08:00-08:00")


@pytest.mark.parametrize(
    ("moment", "inside"),
    [
        (time(7, 59, 59), False),
        (time(8, 0), True),
        (time(12, 0), True),
        (time(18, 0), True),
        (time(18, 0, 1), False),
    ],
)
def test_same_day_window(moment: time, inside: bool) -> None:
    assert ActiveWindow(time(8), time(18)).contains(moment) is inside


@pytest.mark.parametrize(
    ("moment", "inside"),
    [
        (time(21, 59, 59), False),
        (time(22, 0), True),
        (time(23, 59, 59), True),
        (time(0, 0), True),
        (time(6, 0), True),
        (time(6, 0, 1), False),
        (time(12, 0), False),
    ],
)
def test_window_past_midnight(moment: time, inside: bool) -> None:
    assert ActiveWindow(time(22), time(6)).contains(moment) is inside
