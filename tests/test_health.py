from __future__ import annotations

from teams_monitor.health import HealthState


def test_starts_up(clock) -> None:
    assert HealthState(clock).is_down is False


def test_mark_down_is_true_only_on_the_transition(clock) -> None:
    health = HealthState(clock)
    assert health.mark_down() is True
    assert health.mark_down() is False
    assert health.is_down is True


def test_mark_up_allows_the_next_outage_to_transition(clock) -> None:
    health = HealthState(clock)
    health.mark_down()
    health.mark_up()
    assert health.is_down is False
    assert health.mark_down() is True


def test_tray_removal_waits_for_the_grace(clock) -> None:
    health = HealthState(clock, tray_restart_grace=5.0)
    health.note_tray_removed()
    assert health.take_tray_removed() is False
    clock.advance(4.5)
    assert health.take_tray_removed() is False
    clock.advance(0.5)
    assert health.take_tray_removed() is True


def test_tray_removal_is_taken_once(clock) -> None:
    health = HealthState(clock, tray_restart_grace=5.0)
    health.note_tray_removed()
    clock.advance(5)
    assert health.take_tray_removed() is True
    assert health.take_tray_removed() is False


def test_second_removal_does_not_extend_the_grace(clock) -> None:
    health = HealthState(clock, tray_restart_grace=5.0)
    health.note_tray_removed()
    clock.advance(4)
    health.note_tray_removed()
    clock.advance(1)
    assert health.take_tray_removed() is True


def test_mark_up_cancels_a_tray_removal(clock) -> None:
    health = HealthState(clock, tray_restart_grace=5.0)
    health.note_tray_removed()
    health.mark_up()
    clock.advance(10)
    assert health.take_tray_removed() is False


def test_no_tray_removal_means_nothing_to_take(clock) -> None:
    assert HealthState(clock).take_tray_removed() is False


def test_recovery_needs_activity_after_the_grace(clock) -> None:
    health = HealthState(clock, recovery_grace=60.0)
    health.mark_down()
    down_at = clock.monotonic()
    assert health.has_recovered(down_at + 30) is False
    assert health.has_recovered(down_at + 60) is False
    assert health.has_recovered(down_at + 60.5) is True


def test_not_down_means_not_recovered(clock) -> None:
    assert HealthState(clock).has_recovered(clock.monotonic() + 1000) is False
