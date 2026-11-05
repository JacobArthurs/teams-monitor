# teams-monitor

[![python version](https://img.shields.io/badge/python-3.11%2B-blue)](./pyproject.toml)
[![platform](https://img.shields.io/badge/platform-Windows-lightgrey)](#requirements)
[![License](https://img.shields.io/github/license/JacobArthurs/teams-monitor)](LICENSE)

A lightweight Windows background tool that tails the Microsoft Teams log and sends webhook alerts for incoming calls, missed calls, new messages, and Teams outages.

## Features

- **Call Alerts** - Get notified when a call starts ringing and when it ends unanswered
- **Message Alerts** - Get notified when the taskbar unread count rises
- **Outage Detection** - Catch Teams exits, crashes, and hangs using the tray icon, the process list, and log activity
- **Webhook Delivery** - Send JSON that works with Slack-style and Discord incoming webhooks, with automatic retries
- **Read-Only Monitoring** - Never writes to or locks the Teams log
- **No Dependencies** - Uses only the Python standard library, with no admin rights or compiled executable needed

## Requirements

- Windows
- Python 3.11 or later
- The new Microsoft Teams client (`ms-teams.exe`)

## Installation

The package isn't published to PyPI, so install it from a clone of the repository:

```bat
git clone https://github.com/JacobArthurs/teams-monitor.git
cd teams-monitor
python -m pip install --user .
```

If you plan to edit the code, use `python -m pip install --user -e .` so changes apply without reinstalling.

## Quick Start

Create a folder for your settings and copy the example config into it:

```bat
mkdir %USERPROFILE%\teams-monitor-config
copy config.example.toml %USERPROFILE%\teams-monitor-config\config.toml
cd %USERPROFILE%\teams-monitor-config
```

Edit `config.toml` to set `[webhook] url`, then start the monitor from that folder:

```bat
python -m teams_monitor
```

Stop it with Ctrl+C.

To try it without sending anything, leave `url` empty. It then runs in dry-run mode and only logs alerts. Set `from_start = true` under `[debug]` to replay the current log file while testing.

## Usage

### `python -m teams_monitor`

Runs the monitor until it is stopped. `teams-monitor` also works, but `--user` installs often leave its folder off `PATH`, so `python -m teams_monitor` is more reliable.

**Flags:**

| Flag | Description |
| ---- | ----------- |
| `--config` | Path to the config file (default: `config.toml` in the current folder) |
| `--version` | Print the version and exit |
| `-h, --help` | Show help and exit |

**Example:**

```bat
python -m teams_monitor --config C:\path\to\config.toml
```

## Alerts

| Alert | Priority | Fires when |
| ----- | -------- | ---------- |
| Incoming call | 1 | A call starts ringing |
| Missed call | 2 | A ringing call ends without being answered |
| New message | 3 | The taskbar unread count rises and is still up 2 seconds later |
| Teams down | 4 | The tray icon is removed and not re-added within 5 seconds, `ms-teams.exe` isn't running, or the log has no line in the expected format for `stale_minutes` |

### Limitations

These come from what Teams writes to its log:

- Missed, declined, and caller-cancelled calls look identical.
- New message alerts have no sender, content, or type, only the unread count. They require DBG level logging in Teams.
- A rise in the unread count soon after a missed call is suppressed (3 seconds by default). That rule rests on a single observation.
- After a restart, the first unread count sets a new baseline, so messages that arrived while Teams was closed don't alert.
- A change to the overall log line format is detected: a warning is logged after 100 unrecognized lines in a row, and a Teams down alert follows after `stale_minutes`. A change to the wording of a single message isn't detected, because it looks the same as the event never happening.
- Signals were validated on commercial tenant logs only. GCC High logs had no calls or unread items, so call and message alerts are unconfirmed there.

## Configuration

All settings live in `config.toml` and are optional. [`config.example.toml`](config.example.toml) documents each one. Unknown sections and keys are rejected, so a typo fails at startup instead of being ignored.

| Section | Key | Default | Description |
| ------- | --- | ------- | ----------- |
| `[teams]` | `log_dir` | `%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\Logs` | Folder containing the `MSTeams_*.log` files |
| `[teams]` | `process` | `ms-teams.exe` | Process checked for outage detection. Empty disables the check. |
| `[webhook]` | `url` | empty | `http` or `https` address for alerts. Empty means dry run. |
| `[monitoring]` | `poll_seconds` | `0.5` | How often the log is polled for new lines |
| `[monitoring]` | `check_interval_seconds` | `30` | How often the outage check runs |
| `[monitoring]` | `stale_minutes` | `10` | Alert after this long with no line in the expected format |
| `[monitoring]` | `active_hours` | empty | Local time window for Teams down alerts, such as `08:00-18:00`. Empty means always. If Teams is still down when the window opens, the alert fires then. |
| `[monitoring]` | `suppress_after_missed_seconds` | `3` | Ignore an unread count rise this soon after a missed call |
| `[logging]` | `file` | empty | Write monitor logs to this rotating file. Empty prints to the console. |
| `[logging]` | `verbose` | `false` | Enable debug logging |
| `[debug]` | `from_start` | `false` | Read the current log file from the beginning |

The four time settings must be finite and no greater than 1,000,000. All must be above 0, except `suppress_after_missed_seconds`, which can be 0.

## Webhook Delivery

### Payload

Alerts are sent as JSON. Slack-style webhooks read `text`, and Discord reads `content`:

```json
{
  "alert": "incoming_call",
  "priority": 1,
  "text": "[Teams] Incoming call",
  "content": "[Teams] Incoming call",
  "host": "MY-PC",
  "sent_at": "2026-10-13T13:41:20-04:00",
  "call_id": "13e25d06-3814-4a7f-afbd-109d3c013a6a",
  "log_ts": "2026-10-13T13:41:20.566372-04:00"
}
```

Each alert type adds its own fields:

| Alert | Additional fields |
| ----- | ----------------- |
| `incoming_call`, `missed_call` | `call_id`, `log_ts` |
| `new_message` | `unread`, `presence`, `log_ts` |
| `teams_down` | `reason` |

### Retries and Failures

| Response | Behavior |
| -------- | -------- |
| Network error, malformed response, 5xx, 429 | Retried after 1, 2, and 4 seconds. A `Retry-After` header can lengthen a wait, up to 30 seconds. |
| Other 4xx | Fails without retrying |
| Redirect (3xx) | Fails without retrying, because following one would lose the alert body. Set `url` to the final address. |

Each attempt times out after 5 seconds.

Call alerts have their own delivery thread, so they never wait behind message or outage alerts. On a dead endpoint, one alert can still take up to 27 seconds to give up, and a second call alert would wait behind the first.

At shutdown, queued alerts get up to 15 seconds to send. Any that don't are named in the log.

## Running at Logon

No admin rights are needed. Create a shortcut in the Startup folder (`shell:startup`):

- **Target:** `pythonw.exe -m teams_monitor`
- **Start in:** the folder that holds `config.toml`

`pythonw.exe` runs without a console window, so set `[logging] file` to see what the monitor is doing. If a config error or crash happens with no console, it shows a dialog and saves the error to `%LOCALAPPDATA%\teams-monitor\startup-error.log`.

A Task Scheduler "At log on" task also works where your policy allows creating one.

## Security

- `config.toml` holds the webhook URL, which works like a password. It is gitignored, and you should keep it in a folder only your user can read.
- The URL is excluded from `Settings.__repr__` and never logged.
- Only `http` and `https` URLs are accepted. A warning is logged for plain `http`, because alerts would be sent unencrypted.
- Each log line is truncated to 4096 characters before regex matching, and patterns are anchored, which limits worst-case matching cost.
- The log is opened, read, and closed on every poll, so the monitor never holds a lock Teams could trip over.

## Project Structure

```text
pyproject.toml       project metadata and the teams-monitor command
config.example.toml  documented template for config.toml
src/teams_monitor/
  models.py          data types: LogLine, Event, Alert, enums
  parsing.py         LineParser: raw text to LogLine
  signals.py         Signal definitions S1-S6, SignalMatcher
  engine.py          Engine: parse, match, route events to rules
  rules/             one module per alert (A1 to A4) plus factory
  alerts.py          alert constructors, owns priorities and wording
  health.py          shared up/down state so outages alert once
  tailing/           LogLocator, LineReader, LogTailer (rotation aware)
  watchdog/          ProcessProbe, ActivityTracker, Watchdog
  window.py          ActiveWindow: daily time window for outage checks
  notifiers/         Notifier ABC, webhook + retry, HTTP transport,
                     background threads, composite, log sink
  monitor.py         run loop: poll, process, dispatch, watchdog
  bootstrap.py       composition root, the only place concrete classes meet
  config.py          Settings and validation
  config_loader.py   reads and validates config.toml
  cli.py             entry point
  fatal.py           reports fatal errors when there is no console
  clock.py           Clock protocol for testable time
  logging_setup.py   rotating file or console logging
  lifecycle.py       Ctrl+C / SIGTERM / Ctrl+Break handling
```

Dependencies point inward: rules know nothing about files or HTTP, notifiers know nothing about Teams, and every collaborator is injected.

### Extending

- **Add a signal:** add a `Signal` to `signals.py` and a `SignalName` to `models.py`.
- **Add an alert:** add a `Rule` under `rules/` and register it in `rules/factory.py`.
- **Add a destination:** implement `Notifier` and add it to `build_notifier` in `bootstrap.py`.

## Contributing

Contributions are welcome! To get started:

1. Fork the repository
2. Create a feature branch (`git checkout -b my-new-feature`)
3. Open a pull request

To run the tests:

```bat
python -m pip install -e ".[dev]"
python -m pytest
```

Test coverage is minimal and there is no CI at the moment, so please also check your change in dry-run mode before opening a pull request.

## License

This project is licensed under the [MIT License](LICENSE).
