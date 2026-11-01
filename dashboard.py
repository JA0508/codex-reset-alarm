#!/usr/bin/env python3
"""Loopback-only dashboard; does not start a monitor."""
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
import time
import alarm

ROOT = Path(__file__).resolve().parent
TOKEN = secrets.token_urlsafe(32)
CACHE = {'checked': 0, 'limits': {}, 'error': ''}
LOCK = threading.Lock()
ALARM_LOCK = threading.Lock()


def allowed_host(host):
    return host == '127.0.0.1:8765'


def authorized(origin, supplied, expected):
    return origin == 'http://127.0.0.1:8765' and hmac.compare_digest(supplied or '', expected)


def redact(value):
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()
                if 'id' not in key.lower() or key == 'rateLimitsByLimitId'}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def snapshot():
    with LOCK:
        if time.monotonic() - CACHE['checked'] >= 60:
            try:
                CACHE['limits'] = alarm.fetch_limits(alarm.default_codex())
                CACHE['error'] = ''
            except (OSError, RuntimeError, ValueError, KeyError) as error:
                CACHE['error'] = str(error)
            CACHE['checked'] = time.monotonic()
        limits, error = CACHE['limits'], CACHE['error']
    state = alarm.read_state(alarm.DEFAULT_STATE)
    return {'running': time.time() - state.get('heartbeat', 0) < 120,
            'reset': alarm.five_hour_reset(limits) or state.get('reset'),
            'credits': redact(limits.get('rateLimitResetCredits') or state.get('reset_credits', {})),
            'last_check': state.get('last_check'), 'last_alarm': state.get('last_alarm'),
            'error': error or state.get('last_error', ''), 'csrf_token': TOKEN,
            'test_alarm_active': ALARM_LOCK.locked(), 'state': redact(state),
            'limits': redact(limits),
            'iphone': {'status': '未确认', 'configured': False,
                       'instructions': '在电脑运行启动iPhone同步.command，然后按iPhone设置.md在手机创建快捷指令；手机需亲自运行，网页无法确认闹钟已创建。'}}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, content, content_type='application/json; charset=utf-8'):
        body = content if isinstance(content, bytes) else json.dumps(content, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not allowed_host(self.headers.get('Host')):
            return self.respond(403, {'error': 'Invalid Host'})
        if self.path == '/api/status':
            return self.respond(200, snapshot())
        if self.path == '/iphone-setup':
            return self.respond(200, (ROOT / 'iPhone设置.md').read_bytes(), 'text/plain; charset=utf-8')
        if self.path == '/':
            try:
                return self.respond(200, (ROOT / 'web/index.html').read_bytes(), 'text/html; charset=utf-8')
            except FileNotFoundError:
                return self.respond(503, {'error': '页面尚未生成'})
        return self.respond(404, {'error': 'Not found'})

    def do_POST(self):
        if not allowed_host(self.headers.get('Host')) or not authorized(
                self.headers.get('Origin'), self.headers.get('X-CSRF-Token'), TOKEN):
            return self.respond(403, {'error': 'Forbidden'})
        if self.path != '/api/test-alarm':
            return self.respond(404, {'error': 'Not found'})
        if not ALARM_LOCK.acquire(blocking=False):
            return self.respond(409, {'error': '闹铃已在播放'})
        def play():
            try:
                alarm.alert('这是 Codex 闹钟试听。点击停止闹铃结束。')
            except (OSError, alarm.subprocess.SubprocessError) as error:
                print('试听失败：', error, flush=True)
            finally:
                ALARM_LOCK.release()
        threading.Thread(target=play, daemon=True).start()
        self.respond(202, {'ok': True})


def main():
    try:
        server = ThreadingHTTPServer(('127.0.0.1', 8765), Handler)
    except OSError:
        print('端口 8765 已被占用，请检查已有网页服务。')
        return 1
    print('网页：http://127.0.0.1:8765', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
