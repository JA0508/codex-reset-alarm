# Platform setup

## Windows

The watcher automatically uses the npm-installed `codex.cmd` shim. If Codex was installed elsewhere, pass its real executable:

```powershell
codex-quota-watcher --codex-bin "C:\path\to\codex.exe"
```

For a background login-time task, open Task Scheduler and create a task with:

- Trigger: At log on.
- Program: the full path returned by `Get-Command codex-quota-watcher`.
- Arguments: `--interval 60 --notify desktop`.
- Run only when the user is logged on, so toast notifications can appear.
- Do not store a password in the task.

## macOS

Install Codex and the watcher, then record their absolute locations:

```bash
command -v node
command -v codex
command -v codex-quota-watcher
```

First run in Terminal to establish the baseline and allow notifications if macOS asks:

```bash
codex-quota-watcher --once --lang zh
```

For a login-time background process, copy `examples/com.codex-quota-watcher.plist` to `~/Library/LaunchAgents/`, replace all three placeholder paths with the values from `command -v`, then load it:

```bash
mkdir -p ~/Library/LaunchAgents
cp examples/com.codex-quota-watcher.plist ~/Library/LaunchAgents/com.codex-quota-watcher.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.codex-quota-watcher.plist
```

Unload it with:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.codex-quota-watcher.plist
```

Why absolute paths? `launchd` does not inherit the same interactive shell `PATH` as Terminal. The absolute Node path is especially important for Homebrew installations under `/opt/homebrew/bin` or `/usr/local/bin`. The watcher uses `osascript` for Notification Center delivery and does not require a third-party notification package.

If Codex authentication is stored in a user session unavailable to a background agent, run the watcher from Terminal instead. Do not copy authentication files or tokens into the plist.

## Linux

Make sure both commands are on `PATH`:

```bash
command -v codex
command -v codex-quota-watcher
```

Desktop notifications use `notify-send`, normally supplied by `libnotify`:

```bash
codex-quota-watcher --once
codex-quota-watcher --interval 60
```

For a headless server, use `--notify console` or an explicitly configured webhook. A user-level `systemd` service can run the watcher, but it must inherit the same authenticated user environment as Codex. Never copy credential files into the service definition.

## State locations

- Windows: `%LOCALAPPDATA%\codex-quota-watcher\state.json`
- macOS: `~/Library/Application Support/codex-quota-watcher/state.json`
- Linux: `$XDG_STATE_HOME/codex-quota-watcher/state.json`, or `~/.local/state/...`

The stored file contains only redacted quota state, the reset-credit count, generic official-signal metadata, and deduplication data.
