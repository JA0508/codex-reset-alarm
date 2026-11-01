#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 doctor.py
read -r '?按回车关闭'
