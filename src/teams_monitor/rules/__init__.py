"""Alert rules, one module per alert."""

from teams_monitor.rules.base import Rule
from teams_monitor.rules.incoming_call import IncomingCallRule
from teams_monitor.rules.missed_call import MissedCallRule
from teams_monitor.rules.new_activity import NewActivityRule
from teams_monitor.rules.tray_icon import TrayIconRule

__all__ = ["IncomingCallRule", "MissedCallRule", "NewActivityRule", "Rule", "TrayIconRule"]
