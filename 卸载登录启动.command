#!/bin/zsh
launchctl bootout "gui/$(id -u)/local.codex-reset-alarm"
rm -f "$HOME/Library/LaunchAgents/local.codex-reset-alarm.plist"
read -r '?按回车关闭'
