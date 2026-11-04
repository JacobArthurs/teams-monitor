"""Alert rules, one module per alert."""

from teams_monitor.rules.base import Rule
from teams_monitor.rules.factory import build_default_rules

__all__ = ["Rule", "build_default_rules"]
