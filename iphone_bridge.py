#!/usr/bin/env python3
"""Explicitly started, read-only LAN bridge for an iPhone Shortcut."""
import argparse
import sys
import datetime
import errno
import http.client
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import re
import dashboard
import preferences
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
import alarm

TOKEN_PATH = alarm.DEFAULT_STATE.parent / 'iphone-token'


def load_token(path=TOKEN_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        path.chmod(0o600)
        token = path.read_text().strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', token):
            raise RuntimeError('手机访问令牌文件损坏，请停止服务并重新配置手机链接。')
        return token
    with os.fdopen(descriptor, 'w') as output:
        token = secrets.token_urlsafe(32)
        output.write(token)
    return token


def valid_path(path, token):
    return hmac.compare_digest(path, '/' + token + '/alarm.json')


def alarm_payload(reset):
    if not alarm.valid_reset(reset) or reset <= time.time():
        raise ValueError('expired')
    rounded = math.ceil(reset / 60) * 60
    return {'date': datetime.datetime.fromtimestamp(rounded).astimezone().isoformat(),
            'timestamp': rounded, 'label': 'Codex 额度重置'}


def local_ip():
    for interface in ('en0', 'en1'):
        result = subprocess.run(['/usr/sbin/ipconfig', 'getifaddr', interface],
                                capture_output=True, text=True)
        address = result.stdout.strip()
        if result.returncode == 0 and address:
            return address
    return socket.gethostbyname(socket.gethostname())


def stable_address():
    try:
        value = subprocess.run(['/usr/sbin/scutil', '--get', 'LocalHostName'],
                               capture_output=True, text=True, timeout=3).stdout.strip()
        if re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', value):
            return value + '.local'
    except (OSError, subprocess.SubprocessError):
        pass
    return 'localhost'


def phone_status():
    snapshot = dashboard.snapshot()
    safe = {key: snapshot.get(key) for key in
            ('running', 'reset', 'credits', 'last_check', 'last_alarm', 'error')}
    return {**safe, 'test_alarm_active': False, 'phone_mode': True,
            'alarm_url': 'alarm.json', 'notifications_enabled': preferences.enabled()}


def handler_for(token):
    csrf = secrets.token_urlsafe(32)
    hosts = {'localhost:8766', '127.0.0.1:8766', stable_address().lower() + ':8766'}
    try:
        hosts.add(local_ip() + ':8766')
    except OSError:
        pass
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never write the secret URL to access logs.

        def reply(self, code, payload, content_type='application/json; charset=utf-8'):
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            prefix = '/' + token + '/'
            paths = [prefix + suffix for suffix in ('', 'health', 'api/status', 'alarm.json', 'iphone-setup')]
            if not any(hmac.compare_digest(self.path, path) for path in paths):
                return self.reply(404, {'error': 'Not found'})
            if self.path == prefix + 'health':
                return self.reply(200, {'service': 'codex-reset-alarm-iphone-v1'})
            if self.path == prefix + 'api/status':
                return self.reply(200, {**phone_status(), 'csrf_token': csrf})
            if self.path in (prefix, prefix + 'iphone-setup'):
                document = dashboard.ROOT / ('web/index.html' if self.path == prefix else 'web/iphone-setup.html')
                return self.reply(200, document.read_bytes(),
                                  'text/html; charset=utf-8')
            if not preferences.enabled():
                return self.reply(200, {'enabled': False, 'date': None, 'label': 'Codex 额度重置'})
            reset = None
            try:
                reset = alarm.five_hour_reset(alarm.fetch_limits(alarm.default_codex()))
            except (OSError, RuntimeError, ValueError, KeyError):
                pass
            if reset is None:
                try:
                    reset = alarm.read_state(alarm.DEFAULT_STATE).get('reset')
                except OSError:
                    pass
            if reset is None:
                return self.reply(503, {'error': '暂时无法读取重置时间'})
            try:
                payload = {**alarm_payload(reset), 'enabled': True}
            except ValueError:
                return self.reply(409, {'error': '重置时间已过期，请稍后刷新'})
            return self.reply(200, payload)
        def do_POST(self):
            host = self.headers.get('Host', '')
            if (host.lower() not in hosts or self.headers.get('Origin') != 'http://' + host
                    or not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), csrf)
                    or not hmac.compare_digest(self.path, '/' + token + '/api/settings')):
                return self.reply(403, {'error': 'Forbidden'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 1024:
                    return self.reply(400, {'error': 'Invalid size'})
                value = preferences.parse(self.rfile.read(size))
                preferences.save(value)
                return self.reply(200, {'notifications_enabled': value})
            except (ValueError, OSError):
                return self.reply(400, {'error': 'Invalid settings'})
    return Handler


def existing_service(address, token):
    connection = http.client.HTTPConnection(address, 8766, timeout=2)
    try:
        connection.request('GET', '/' + token + '/health')
        response = connection.getresponse()
        return response.status == 200 and json.loads(response.read(1024)) == {
            'service': 'codex-reset-alarm-iphone-v1'}
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def main(argv=()):
    parser = argparse.ArgumentParser(description='iPhone 局域网同步与网页服务')
    parser.add_argument('--quiet', action='store_true', help='后台运行时不打印专属链接')
    args = parser.parse_args(argv)
    try:
        token = load_token()
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    address = stable_address()
    try:
        server = ThreadingHTTPServer(('0.0.0.0', 8766), handler_for(token))
    except OSError as error:
        if error.errno in (errno.EADDRINUSE, 48, 98) and existing_service('127.0.0.1', token):
            print('iPhone 同步服务已在运行，无需重复启动。', flush=True)
            if not args.quiet:
                print(f'稳定网页：http://{address}:8766/{token}/', flush=True)
                print(f'专属 URL（请勿分享）：http://{address}:8766/{token}/alarm.json', flush=True)
            return 0
        print('无法启动：端口 8766 已被其他服务或旧版本占用。请关闭对应服务后重试。'
              if error.errno in (errno.EADDRINUSE, 48, 98) else
              '无法绑定局域网地址，请检查网络连接和系统权限。', flush=True)
        return 1
    if not args.quiet:
        print('仅在你信任的同一 Wi-Fi 中使用。请勿分享以下专属链接：', flush=True)
        print(f'稳定网页：http://{address}:8766/{token}/', flush=True)
        print(f'http://{address}:8766/{token}/alarm.json', flush=True)
        print('将链接填入 iPhone 快捷指令；按 Control+C 停止。', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
