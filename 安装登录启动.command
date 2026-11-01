#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 launchd_setup.py || exit 1
mkdir -p "$HOME/Library/LaunchAgents"
cp local.codex-reset-alarm.plist "$HOME/Library/LaunchAgents/"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.codex-reset-alarm.plist"
read -r '?按回车关闭'
