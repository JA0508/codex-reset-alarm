#!/usr/bin/env python3
"""Read-only checks; deliberately omit account data and filesystem paths."""
import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import alarm
import preferences

SERVICES = ('alarm', 'dashboard', 'iphone')
LABELS = {'alarm': 'local.codex-reset-alarm', 'dashboard': 'local.codex-reset-dashboard',
          'iphone': 'local.codex-reset-iphone'}


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            return True
    except OSError:
        return False


def launchd_loaded(service):
    try:
        result = subprocess.run(['launchctl', 'print', f'gui/{os.getuid()}/{LABELS[service]}'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def diagnose():
    macos = platform.system() == 'Darwin'
    python_ok = sys.version_info >= (3, 10)
    codex = alarm.default_codex()
    codex_ok = os.path.isfile(codex) and os.access(codex, os.X_OK)
    runtime = alarm.DEFAULT_STATE.parent
    # Inspect nearest existing ancestor without creating files or directories.
    while not runtime.exists() and runtime != runtime.parent:
        runtime = runtime.parent
    runtime_ok = os.access(runtime, os.R_OK | os.W_OK | os.X_OK)
    def check(ok, suggestion):
        return {'ok': bool(ok), 'next_step': '' if ok else suggestion}
    checks = {
        'macos': check(macos, '请在 macOS 上运行，其他系统只能执行单元测试。'),
        'python': {**check(python_ok, '请安装 Python 3.10 或更新版本。'),
                   'version': '.'.join(map(str, sys.version_info[:3]))},
        'codex': check(codex_ok, '请安装 Codex CLI，或检查 PATH 中的 codex 是否可执行。'),
        'runtime_access': check(runtime_ok, '请检查当前用户对 Application Support 目录的读写权限。'),
        'notifications_enabled': check(preferences.enabled(), '可在网页打开提醒开关。'),
    }
    for service in SERVICES:
        checks['service_' + service] = check(macos and launchd_loaded(service),
                                            '如需后台运行，请执行 python3 launchd_setup.py install。')
    for name, port in (('dashboard', 8765), ('iphone', 8766)):
        checks['port_' + name] = check(port_open(port),
                                      '请启动对应服务；若已安装登录服务，可查看本地服务日志。')
    return {'ok': all(checks[key]['ok'] for key in ('macos', 'python', 'codex', 'runtime_access')),
            'checks': checks,
            'note': '端口连通仅代表存在监听程序；服务未安装或提醒关闭不视为环境致命错误。诊断不会修改设置。'}


def main(argv=None):
    parser = argparse.ArgumentParser(description='只读检查 Codex 闹钟运行环境')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    report = diagnose()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for key, item in report['checks'].items():
            print(f'{key}: ' + ('正常' if item['ok'] else '需检查'))
            if item['next_step']:
                print('  ' + item['next_step'])
        print(report['note'])
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
