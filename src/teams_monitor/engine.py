"""Routes raw log lines through parsing, signal matching and alert rules."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from teams_monitor.models import Alert, LogLine, SignalName
from teams_monitor.parsing import LineParser
from teams_monitor.rules.base import Rule
from teams_monitor.signals import SignalMatcher


class Engine:
    def __init__(
        self,
        parser: LineParser,
        matcher: SignalMatcher,
        rules: Sequence[Rule],
    ) -> None:
        self._parser = parser
        self._matcher = matcher
        self._rules = rules
        self._routes: dict[SignalName, list[Rule]] = defaultdict(list)
        for rule in rules:
            for name in rule.handles:
                self._routes[name].append(rule)

    def parse(self, raw_line: str) -> LogLine | None:
        """Parse a raw line. None means it is not in the expected Teams log format."""
        return self._parser.parse(raw_line)

    def route(self, line: LogLine) -> list[Alert]:
        """Match a parsed line against the signals and run the rules that handle it."""
        event = self._matcher.match(line)
        if event is None:
            return []
        alerts: list[Alert] = []
        for rule in self._routes.get(event.signal, ()):
            alerts.extend(rule.on_event(event))
        return alerts

    def restore(self, raw_lines: Iterable[str]) -> None:
        """Bring rules up to date from lines written before the monitor started, without alerts."""
        for raw in raw_lines:
            line = self._parser.parse(raw)
            event = self._matcher.match(line) if line is not None else None
            if event is None:
                continue
            for rule in self._routes.get(event.signal, ()):
                rule.on_history(event)

    def tick(self) -> list[Alert]:
        """Collect alerts from rules that were waiting for time to pass."""
        return [alert for rule in self._rules for alert in rule.on_tick()]
