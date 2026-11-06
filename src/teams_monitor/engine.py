"""Routes raw log lines through parsing, signal matching and alert rules."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from teams_monitor.models import Alert, Event, LogLine, SignalName
from teams_monitor.parsing import parse_line
from teams_monitor.rules.base import Rule
from teams_monitor.signals import match_signal

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BatchResult:
    """What a batch of raw lines produced. Blank lines count as neither kind."""

    alerts: list[Alert]
    recognized: int
    unrecognized: int


class Engine:
    def __init__(self, rules: Sequence[Rule]) -> None:
        self._rules = rules
        self._routes: dict[SignalName, list[Rule]] = defaultdict(list)
        for rule in rules:
            for name in rule.handles:
                self._routes[name].append(rule)

    def process(self, raw_lines: Iterable[str]) -> BatchResult:
        """Run new lines through the rules. A line that fails never stops the ones after it."""
        alerts: list[Alert] = []
        recognized = 0
        unrecognized = 0
        for raw in raw_lines:
            if not raw.strip():
                continue
            try:
                line = parse_line(raw)
                if line is None:
                    unrecognized += 1
                    continue
                recognized += 1
                for event, rule in self._deliveries(line):
                    alerts.extend(rule.on_event(event))
            except Exception:
                log.exception("failed to process a log line, continuing with the next one")
        return BatchResult(alerts, recognized, unrecognized)

    def restore(self, raw_lines: Iterable[str]) -> None:
        """Bring rules up to date from lines written before the monitor started, without alerts."""
        for raw in raw_lines:
            line = parse_line(raw)
            if line is not None:
                for event, rule in self._deliveries(line):
                    rule.on_history(event)

    def tick(self) -> list[Alert]:
        """Collect alerts from rules that were waiting for time to pass."""
        return [alert for rule in self._rules for alert in rule.on_tick()]

    def _deliveries(self, line: LogLine) -> Iterator[tuple[Event, Rule]]:
        event = match_signal(line)
        if event is not None:
            for rule in self._routes.get(event.signal, ()):
                yield event, rule
