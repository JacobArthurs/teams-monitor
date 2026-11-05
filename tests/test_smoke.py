"""Confirms the package and its wiring import cleanly."""

from teams_monitor.bootstrap import build_monitor


def test_composition_root_imports() -> None:
    assert callable(build_monitor)
