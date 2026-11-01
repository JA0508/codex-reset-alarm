#!/usr/bin/env python3
"""Offline UI demonstration. No account, alarm or persistence integration."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import time

HOST = '127.0.0.1:8768'
TOKEN = secrets.token_urlsafe(32)
STARTED = time.time()
ENABLED = True
ROOT = Path(__file__).resolve().parent


def snapshot():
    return {'demo_mode': True, 'phone_mode': False, 'notifications_enabled': ENABLED,
            'running': True, 'reset': STARTED + 8100, 'credits': {'availableCount': 2},
            'last_check': STARTED, 'last_alarm': None, 'fetched_at': STARTED,
            'error': '', 'csrf_token': TOKEN, 'test_alarm_active': False,
            'iphone': {'status': '离线演示，未连接手机', 'configured': False}}


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload, content_type='application/json; charset=utf-8'):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        for name, value in [('Content-Type', content_type), ('Content-Length', str(len(body))),
                            ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
                            ('Referrer-Policy', 'no-referrer'), ('X-Frame-Options', 'DENY')]:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get('Host') != HOST:
            return self.reply(403, {'error': 'Forbidden'})
        if self.path == '/api/status':
            return self.reply(200, snapshot())
        if self.path == '/api/connection':
            return self.reply(200, {'available': False, 'action': '离线演示不提供真实手机连接地址。'})
        if self.path == '/iphone-setup':
            return self.reply(200, '<!doctype html><meta charset="utf-8"><h1>离线演示</h1><p>此模式不会连接手机或创建闹钟。真实使用请退出演示并运行本地服务，按 iPhone 设置指南配置快捷指令。</p>'.encode(), 'text/html; charset=utf-8')
        if self.path == '/':
            try:
                return self.reply(200, (ROOT / 'web/index.html').read_bytes(), 'text/html; charset=utf-8')
            except OSError:
                return self.reply(503, {'error': '演示页面缺失，请恢复 web/index.html。'})
        return self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        global ENABLED
        if (self.headers.get('Host') != HOST or self.headers.get('Origin') != 'http://' + HOST
                or not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), TOKEN)):
            return self.reply(403, {'error': 'Forbidden'})
        if self.path == '/api/test-alarm':
            return self.reply(409, {'error': '离线演示不会播放真实闹铃。'})
        if self.path != '/api/settings':
            return self.reply(404, {'error': 'Not found'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 1024:
                raise ValueError
            value = json.loads(self.rfile.read(size))
            if not isinstance(value, dict) or set(value) != {'enabled'} or type(value['enabled']) is not bool:
                raise ValueError
            ENABLED = value['enabled']
            return self.reply(200, {'notifications_enabled': ENABLED})
        except (ValueError, OSError):
            return self.reply(400, {'error': '需要 enabled 布尔值，且请求不超过 1024 字节。'})


def main():
    try:
        server = ThreadingHTTPServer(('127.0.0.1', 8768), Handler)
    except OSError:
        print('无法启动离线演示，端口 8768 可能已被占用。')
        return 1
    print('离线演示：http://127.0.0.1:8768 （不会读取账号或播放真实闹铃）', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
