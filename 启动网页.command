#!/bin/zsh
cd -- "${0:A:h}" || exit 1
url='http://127.0.0.1:8765'
if ! /usr/bin/curl --silent --fail --max-time 2 "$url/" >/dev/null; then
  mkdir -p "$HOME/Library/Application Support/CodexResetAlarm/logs"
  nohup python3 dashboard.py >>"$HOME/Library/Application Support/CodexResetAlarm/logs/dashboard.log" 2>&1 </dev/null &
  for attempt in {1..30}; do
    if /usr/bin/curl --silent --fail --max-time 1 "$url/" >/dev/null; then
      open "$url"
      exit 0
    fi
    sleep 1
  done
  printf '网页未就绪，请查看 Application Support/CodexResetAlarm/logs/dashboard.log\n'
  read -r '?按回车关闭'
  exit 1
fi
open "$url"
