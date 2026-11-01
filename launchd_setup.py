#!/usr/bin/env python3
"""Generate or explicitly install independent login services."""
import argparse
import os
from pathlib import Path
import plistlib
import platform
import subprocess
import sys
import alarm

ROOT = Path(__file__).resolve().parent
SERVICES = {'alarm': ('local.codex-reset-alarm', 'alarm.py'),
            'dashboard': ('local.codex-reset-dashboard', 'dashboard.py'),
            'iphone': ('local.codex-reset-iphone', 'iphone_bridge.py')}
LOGS = alarm.DEFAULT_STATE.parent / 'logs'


def configuration(service):
    if service not in SERVICES:
        raise ValueError('Unknown service')
    label, script = SERVICES[service]
    arguments = [str(Path(sys.executable).resolve()), str(ROOT / script)]
    if service == 'alarm':
        arguments += ['run', '--codex', alarm.default_codex()]
    if service == 'iphone':
        arguments += ['--quiet']
    return {'Umask': 0o077, 'Label': label, 'ProgramArguments': arguments,
            'WorkingDirectory': str(ROOT), 'RunAtLoad': True,
            'KeepAlive': True, 'ThrottleInterval': 60,
            'StandardOutPath': str(LOGS / (service + '.log')),
            'StandardErrorPath': str(LOGS / (service + '.error.log'))}


def preflight(services):
    errors = []
    if platform.system() != 'Darwin':
        errors.append('登录服务需要 macOS；其他系统可使用 generate 生成配置。')
    if sys.version_info < (3, 10):
        errors.append('需要 Python 3.10 或更新版本。')
    for service in services:
        if not (ROOT / SERVICES[service][1]).is_file():
            errors.append(f'{service} 服务脚本缺失，请恢复完整项目文件。')
    if 'alarm' in services:
        codex = alarm.default_codex()
        if not os.path.isfile(codex) or not os.access(codex, os.X_OK):
            errors.append('未找到可执行 Codex CLI，请先安装并配置 PATH。')
    return errors


def secure_logs(service):
    LOGS.mkdir(parents=True, exist_ok=True, mode=0o700)
    LOGS.chmod(0o700)
    for suffix in ('.log', '.error.log'):
        path = LOGS / (service + suffix)
        if path.exists() and not path.is_symlink():
            path.chmod(0o600)


def manage(mode, service, output):
    label = SERVICES[service][0]
    domain = f'gui/{os.getuid()}'
    if mode == 'uninstall':
        subprocess.run(['launchctl', 'bootout', domain + '/' + label], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (Path.home() / 'Library/LaunchAgents' / (label + '.plist')).unlink(missing_ok=True)
        return
    destination = (Path.home() / 'Library/LaunchAgents') if mode == 'install' else output
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / (label + '.plist')
    path.write_bytes(plistlib.dumps(configuration(service)))
    if mode == 'install':
        secure_logs(service)
        subprocess.run(['launchctl', 'bootout', domain + '/' + label], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['launchctl', 'bootstrap', domain, str(path)], check=True)
    print(f'{mode}: {path}')


def main(argv=None):
    parser = argparse.ArgumentParser(description='独立管理闹钟、网页和可选 iPhone 登录服务')
    parser.add_argument('mode', nargs='?', default='generate', choices=['generate', 'install', 'uninstall'])
    parser.add_argument('--services', nargs='+', choices=list(SERVICES), default=['alarm', 'dashboard', 'iphone'])
    parser.add_argument('--output', type=Path, default=Path('/tmp/codex-reset-launchd'))
    args = parser.parse_args(argv)
    if args.mode == 'install':
        errors = preflight(args.services)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            print('运行 python3 doctor.py 查看环境诊断。', file=sys.stderr)
            return 1
    for service in args.services:
        try:
            manage(args.mode, service, args.output)
        except (OSError, subprocess.SubprocessError):
            print(f'{service} 服务{args.mode}失败。请运行 python3 doctor.py 查看诊断，并检查服务日志。', file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
