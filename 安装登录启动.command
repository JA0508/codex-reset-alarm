#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 launchd_setup.py install
read -r "?按回车关闭"
