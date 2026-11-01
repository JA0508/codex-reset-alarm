#!/usr/bin/env python3
"""Generate or explicitly install independent login services."""
import argparse
import os
from pathlib import Path
import plistlib
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
    return {'Label': label, 'ProgramArguments': arguments,
            'WorkingDirectory': str(ROOT), 'RunAtLoad': True,
            'KeepAlive': True, 'ThrottleInterval': 60,
            'StandardOutPath': str(LOGS / (service + '.log')),
            'StandardErrorPath': str(LOGS / (service + '.error.log'))}


def manage(mode, service, output):
    label = SERVICES[service][0]
    domain = f'gui/{os.getuid()}'
    if mode == 'uninstall':
        subprocess.run(['launchctl', 'bootout', domain + '/' + label], check=False)
        (Path.home() / 'Library/LaunchAgents' / (label + '.plist')).unlink(missing_ok=True)
        return
    destination = (Path.home() / 'Library/LaunchAgents') if mode == 'install' else output
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / (label + '.plist')
    path.write_bytes(plistlib.dumps(configuration(service)))
    if mode == 'install':
        LOGS.mkdir(parents=True, exist_ok=True)
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
    for service in args.services:
        manage(args.mode, service, args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
