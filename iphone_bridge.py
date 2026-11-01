#!/usr/bin/env python3
"""Explicitly started, read-only LAN bridge for an iPhone Shortcut."""
import datetime
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
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
        return path.read_text().strip()
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


def handler_for(token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never write the secret URL to access logs.

        def reply(self, code, payload):
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not valid_path(self.path, token):
                return self.reply(404, {'error': 'Not found'})
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
                payload = alarm_payload(reset)
            except ValueError:
                return self.reply(409, {'error': '重置时间已过期，请稍后刷新'})
            return self.reply(200, payload)
    return Handler


def main():
    token = load_token()
    address = local_ip()
    if address.startswith('127.') or address == '0.0.0.0':
        raise RuntimeError('未找到局域网地址，请连接 Wi-Fi 后重试')
    server = ThreadingHTTPServer((address, 8766), handler_for(token))
    print('仅在你信任的同一 Wi-Fi 中使用。请勿分享以下专属链接：', flush=True)
    print(f'http://{address}:8766/{token}/alarm.json', flush=True)
    print('将链接填入 iPhone 快捷指令；按 Control+C 停止。', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
