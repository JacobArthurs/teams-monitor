from __future__ import annotations

import pytest
from helpers import CALL_A, event, load_samples, parse, stamp, tray_remove

from teams_monitor.models import SignalName
from teams_monitor.signals import SignalMatcher


@pytest.mark.parametrize(
    ("name", "signal", "groups"),
    [
        (
            "incoming_call",
            SignalName.CALL_INCOMING,
            {"call_id": "5287a96c-657d-4d03-a428-516cae679e0a"},
        ),
        (
            "call_answered",
            SignalName.CALL_ANSWERED,
            {"call_id": "13e25d06-3814-4a7f-afbd-109d3c013a6a"},
        ),
        (
            "call_ended",
            SignalName.CALL_ENDED,
            {"call_id": "5287a96c-657d-4d03-a428-516cae679e0a", "remaining": "0"},
        ),
        (
            "new_message",
            SignalName.UNREAD_BADGE,
            {"unread": "1", "overlay_items": "1", "presence": "Available"},
        ),
        ("app_started", SignalName.APP_STARTED, {}),
        ("unread_count", SignalName.UNREAD_COUNT, {"unread": "0"}),
    ],
)
def test_real_samples_match_their_signal(
    name: str, signal: SignalName, groups: dict[str, str]
) -> None:
    found = event(load_samples()[name])
    assert found.signal is signal
    assert dict(found.groups) == groups


@pytest.mark.parametrize("name", ["notification_popup", "app_quit"])
def test_samples_the_monitor_deliberately_ignores(name: str) -> None:
    # Clean quits are detected from the tray icon, and popups are not used at all.
    assert SignalMatcher().match(parse(load_samples()[name])) is None


def test_tray_removal_matches_app_exited() -> None:
    # Uses a synthetic line, see helpers.tray_remove.
    assert event(tray_remove()).signal is SignalName.APP_EXITED


def _info(msg: str) -> str:
    return f"{stamp()} 0x1 <INFO> {msg}"


def test_right_message_at_the_wrong_level_does_not_match() -> None:
    msg = f"HfpVoipCallCoordinatorImpl: reportIncomingCall for callId: {CALL_A}"
    assert SignalMatcher().match(parse(f"{stamp()} 0x1 <DBG> {msg}")) is None


@pytest.mark.parametrize(
    "msg",
    [
        f"HfpVoipCallCoordinatorImpl: reportIncomingCall for callId: {CALL_A.upper()}",
        f"HfpVoipCallCoordinatorImpl: reportIncomingCall for callId: {CALL_A} and more",
        f"prefix HfpVoipCallCoordinatorImpl: reportIncomingCall for callId: {CALL_A}",
        "HfpVoipCallCoordinatorImpl: reportIncomingCall for callId: not-a-guid",
        f"TeamsCallTracker: Call ended: {CALL_A}",
        "NotificationIcon: (id={abc}; fallback_id=1) Shell_NotifyIconW(NIM_ADD, id={abc})",
    ],
)
def test_near_misses_do_not_match(msg: str) -> None:
    assert SignalMatcher().match(parse(_info(msg))) is None


def test_trailing_whitespace_after_a_call_id_is_allowed() -> None:
    msg = f"HfpVoipCallCoordinatorImpl: reportIncomingCall for callId: {CALL_A}   "
    assert event(_info(msg)).signal is SignalName.CALL_INCOMING


def test_presence_with_spaces_is_captured_whole() -> None:
    raw = (
        f"{stamp()} 0x1 <DBG>  TaskbarBadgeServiceLegacy:Work: SetBadge Setting badge: "
        "NumericBadge{12}, overlay: 3 items, status Do Not Disturb  "
    )
    groups = event(raw).groups
    assert groups["unread"] == "12"
    assert groups["presence"] == "Do Not Disturb"


def test_remaining_count_is_captured() -> None:
    assert (
        event(_info(f"TeamsCallTracker: Call ended: {CALL_A} (remaining: 2)")).groups["remaining"]
        == "2"
    )


def test_matcher_with_no_signals_matches_nothing() -> None:
    assert SignalMatcher(()).match(parse(load_samples()["incoming_call"])) is None
