#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 iphone_bridge.py
read -r '?按回车关闭'
