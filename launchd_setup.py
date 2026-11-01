#!/usr/bin/env python3
"""Generate login agent configuration; never install automatically."""
import plistlib
import sys
from pathlib import Path
import alarm

root = Path(__file__).resolve().parent
output = root / 'local.codex-reset-alarm.plist'
output.write_bytes(plistlib.dumps({
    'Label': 'local.codex-reset-alarm',
    'ProgramArguments': [sys.executable, str(root / 'alarm.py'), 'run', '--codex', alarm.default_codex()],
    'WorkingDirectory': str(root), 'RunAtLoad': True, 'KeepAlive': True,
    'StandardOutPath': '/tmp/codex-reset-alarm.log',
    'StandardErrorPath': '/tmp/codex-reset-alarm.error.log',
}))
print('已生成：' + str(output) + '（尚未安装）')
