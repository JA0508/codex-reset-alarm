#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 alarm.py status
printf '\n按回车关闭。'
read -r
