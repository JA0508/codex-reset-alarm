#!/bin/zsh
cd -- "${0:A:h}" || exit 1
open 'http://127.0.0.1:8765'
python3 dashboard.py
