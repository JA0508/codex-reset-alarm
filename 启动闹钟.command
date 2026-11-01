#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 alarm.py run
printf '\n程序已结束，按回车关闭。'
read -r
