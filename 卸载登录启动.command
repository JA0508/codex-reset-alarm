#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 launchd_setup.py uninstall
read -r "?按回车关闭"
