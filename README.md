# teams-monitor

[![ci](https://img.shields.io/github/actions/workflow/status/JacobArthurs/teams-monitor/ci.yml?branch=main)](https://github.com/JacobArthurs/teams-monitor/actions/workflows/ci.yml)
[![pypi](https://img.shields.io/pypi/v/teams-monitor)](https://pypi.org/project/teams-monitor/)
[![python version](https://img.shields.io/badge/python-3.11%2B-blue)](https://github.com/JacobArthurs/teams-monitor/blob/main/pyproject.toml)
[![platform](https://img.shields.io/badge/platform-Windows-lightgrey)](#requirements)
[![License](https://img.shields.io/github/license/JacobArthurs/teams-monitor)](https://github.com/JacobArthurs/teams-monitor/blob/main/LICENSE)

A lightweight Windows background tool that tails the Microsoft Teams log and sends webhook alerts for incoming calls, missed calls, new activity, and Teams outages.

Use it to get Teams alerts on your phone or in another chat tool when you're away from your desk. It only reads the local log, so it needs no credentials or admin consent.

> [!NOTE]
> This project isn't affiliated with or endorsed by Microsoft. It relies on an undocumented log format that a Teams update could change at any time.

## Features

- **Call Alerts** - Get notified when a call starts ringing and when it ends unanswered
- **Activity Alerts** - Get notified when the taskbar unread count rises (see [Limitations](#limitations))
- **Outage Detection** - Catch Teams exits, crashes, and hangs using the tray icon, the process list, and log activity
- **Webhook Delivery** - Send JSON that works with Slack-style and Discord incoming webhooks, with automatic retries
- **Read-Only Monitoring** - Never writes to the Teams log, and only holds it open while reading
- **No Dependencies** - Uses only the Python standard library, with no admin rights or compiled executable needed

## Requirements

- Windows
- Python 3.11 or later
- The new Microsoft Teams client (`ms-teams.exe`)

## Installation

Commands in this README are for PowerShell.

### From PyPI

```powershell
pip install teams-monitor
```

To upgrade later, run `pip install --upgrade teams-monitor`, then restart the monitor.

### From Source

Clone the repository to run it locally or edit the code:

```powershell
git clone https://github.com/JacobArthurs/teams-monitor.git
cd teams-monitor
$env:PYTHONPATH = "src"
```

`PYTHONPATH` only lasts for the current terminal, and this relative path only works from the repository folder. To avoid setting it each time, run `pip install -e .` once instead. To upgrade later, run `git pull`, then restart the monitor.

## Quick Start

Create your config file. If you installed from PyPI, create a settings folder for it first:

```powershell
mkdir $env:USERPROFILE\teams-monitor-config
cd $env:USERPROFILE\teams-monitor-config
```

If you cloned the repository, stay in the repository folder instead. Your config is gitignored there. Then create the file:

```powershell
python -m teams_monitor --init-config
```

This never overwrites an existing file. Edit `config.toml` to set `[webhook] url`, then check that alerts reach you:

```powershell
python -m teams_monitor --test-webhook
```

Start the monitor from the folder that holds `config.toml`:

```powershell
python -m teams_monitor
```

Stop it with Ctrl+C.

To try it without sending anything, leave `url` empty. It then runs in dry-run mode and only logs alerts. Set `from_start = true` under `[debug]` to replay the current log file while testing. The output looks like this:

```text
2026-11-05 11:44:26,087 WARNING teams_monitor.bootstrap: no webhook configured, running in dry-run mode (alerts are only logged)
2026-11-05 11:44:26,088 INFO teams_monitor.monitor: monitor started
2026-11-05 11:44:26,088 INFO teams_monitor.tailing.tailer: tailing MSTeams_sample.log from offset 0
2026-11-05 11:44:26,093 INFO teams_monitor.monitor: ALERT incoming_call p1: Incoming call
2026-11-05 11:44:26,093 INFO teams_monitor.monitor: ALERT missed_call p2: Missed call
```

## Usage

```powershell
python -m teams_monitor [--config PATH] [--init-config] [--test-webhook]
```

The monitor runs until it is stopped. Once installed with pip, `teams-monitor` also works if Python's `Scripts` folder is on your `PATH`, so `python -m teams_monitor` is more reliable.

| Flag | Description |
| ---- | ----------- |
| `--config` | Path to the config file (default: `config.toml` in the current folder) |
| `--init-config` | Create a starter config file at the `--config` path and exit. Never overwrites an existing file. |
| `--test-webhook` | Send one test alert to `[webhook] url` and exit. Exits with 1 if delivery fails. |
| `--version` | Print the version and exit |
| `-h, --help` | Show help and exit |

## Alerts

Priority 1 is the most urgent.

| Alert | Priority | Fires when |
| ----- | -------- | ---------- |
| Incoming call | 1 | A call starts ringing |
| Missed call | 2 | A ringing call ends without being answered |
| New activity | 3 | The taskbar unread count rises and is still up 2 seconds later |
| Teams down | 4 | The tray icon is removed and not re-added within 5 seconds, `ms-teams.exe` isn't running, or the log has no line in the expected format for `stale_minutes` |
| Monitor error | 4 | The monitor's own loop fails 5 times in a row, so other alerts may be missed |

After a failure the loop waits longer before each retry, up to 30 seconds, so a monitor error fires about 15 seconds into a lasting problem. It fires again only if the loop recovers and then fails 5 more times in a row. `active_hours` doesn't affect it.

Teams down fires once per outage. No alert is sent when Teams recovers, so a later outage is the next thing you'd hear about.

### Limitations

These come from what Teams writes to its log:

- Missed, declined, and caller-cancelled calls look identical.
- New activity alerts have no sender, content, or type, only the unread count. They depend on a DBG level line in the Teams log. See [Troubleshooting](#troubleshooting) to check whether your log has it.
- A rise in the unread count soon after a missed call is suppressed (3 seconds by default). That default is based on limited testing.
- After a restart, the first unread count sets a new baseline, so activity that arrived while Teams was closed doesn't alert.
- A change to the overall log line format is detected: a warning is logged after 100 unrecognized lines in a row, and a Teams down alert follows after `stale_minutes`. A change to the wording of a single message isn't detected, because it looks the same as the event never happening.

## Configuration

Settings live in `config.toml`. The file must exist, but every setting in it is optional. The file that `--init-config` creates documents each one. Unknown sections and keys are rejected, so a typo fails at startup instead of being ignored.

| Section | Key | Default | Description |
| ------- | --- | ------- | ----------- |
| `[teams]` | `log_dir` | See below | Folder containing the `MSTeams_*.log` files |
| `[teams]` | `process` | `ms-teams.exe` | Process checked for outage detection. Empty disables the check. |
| `[webhook]` | `url` | empty | `http` or `https` address for alerts. Empty means dry run. |
| `[monitoring]` | `poll_seconds` | `0.5` | How often the log is polled for new lines |
| `[monitoring]` | `check_interval_seconds` | `30` | How often the outage check runs |
| `[monitoring]` | `stale_minutes` | `10` | Alert after this long with no line in the expected format |
| `[monitoring]` | `active_hours` | empty | Local time window for Teams down alerts. Empty means always. See below. |
| `[monitoring]` | `suppress_after_missed_seconds` | `3` | Ignore an unread count rise this soon after a missed call |
| `[logging]` | `file` | empty | Write monitor logs to this rotating file. Empty prints to the console. |
| `[logging]` | `verbose` | `false` | Enable debug logging |
| `[debug]` | `from_start` | `false` | Read the current log file from the beginning |

The default `log_dir` is:

```text
%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\Logs
```

`active_hours` looks like `08:00-18:00`. Start and end must differ, and the window can wrap past midnight, such as `22:00-06:00`. If Teams is still down when the window opens, the alert fires then. It only affects Teams down alerts, so call and activity alerts are sent at any hour.

`poll_seconds`, `check_interval_seconds`, `stale_minutes`, and `suppress_after_missed_seconds` must be finite and no greater than 1,000,000. All must be above 0, except `suppress_after_missed_seconds`, which can be 0.

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
| `new_message` (New activity) | `unread`, `presence`, `log_ts` |
| `teams_down` | `reason` |
| `monitor_error` | `failures` |
| `test` (from `--test-webhook`) | None |

The `reason` field on `teams_down` tells you what triggered the alert:

| Reason | Meaning |
| ------ | ------- |
| `tray icon removed` | Teams removed its tray icon and didn't add it back within 5 seconds |
| `Teams process is not running` | The process set in `[teams] process` wasn't found |
| `no log activity for N min` | The log has had no new lines, which can mean Teams has hung |
| `log lines not recognized for N min (the log format may have changed)` | The log is being written, but its lines no longer match the expected format |

### Retries and Failures

| Response | Behavior |
| -------- | -------- |
| Network error, malformed response, 5xx, 429 | Retried after 1, 2, and 4 seconds. A `Retry-After` header can lengthen a wait, up to 30 seconds. |
| Other 4xx | Fails without retrying |
| Redirect (3xx) | Fails without retrying, because following one would lose the alert body. Set `url` to the final address. |

Each attempt times out after 5 seconds.

Call alerts have their own delivery thread, so they never wait behind activity or outage alerts. On a dead endpoint, one alert can still take up to 27 seconds to give up, and a second call alert would wait behind the first. If the endpoint also sends the longest `Retry-After`, that rises to 110 seconds: 4 attempts at 5 seconds plus 3 waits at 30 seconds.

At shutdown, queued alerts get up to 15 seconds to send. Any that don't are named in the log.

## Troubleshooting

| Problem | What to check |
| ------- | ------------- |
| `config file not found` | Run the monitor from the folder that holds `config.toml`, pass `--config`, or create the file with `--init-config` |
| `Teams log folder not found` | Set `[teams] log_dir` to the folder containing the `MSTeams_*.log` files |
| Not sure alerts reach you | Run `python -m teams_monitor --test-webhook` |
| No activity alerts | Check that your log contains unread count lines, using the command below |
| `delivery of ... failed: HTTP 4xx` | Check `[webhook] url`. The endpoint rejected the alert, so it isn't retried. |
| The webhook URL redirects | Set `[webhook] url` to the final address |
| Nothing happens at logon | Check `%LOCALAPPDATA%\teams-monitor\startup-error.log` and your `[logging] file` |

To check for unread count lines, run this after a new message arrives in Teams. If it prints nothing, activity alerts can't fire on your machine:

```powershell
Select-String -Path "$env:LOCALAPPDATA\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\Logs\MSTeams_*.log" -Pattern "TaskbarBadgeServiceLegacy" -List
```

## Contributing

Contributions are welcome! To get started:

1. Fork the repository
2. Create a feature branch (`git checkout -b my-new-feature`)
3. Open a pull request

CI will automatically run tests and linting on your PR.

## License

This project is licensed under the [MIT License](https://github.com/JacobArthurs/teams-monitor/blob/main/LICENSE).
