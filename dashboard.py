#!/usr/bin/env python3
"""Loopback-only dashboard; does not start a monitor."""
import hmac
import re
import ipaddress
import preferences
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
import time
import alarm

ROOT = Path(__file__).resolve().parent
TOKEN = secrets.token_urlsafe(32)
CACHE = {'checked': None, 'limits': {}, 'error': '', 'fetched_at': None}
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
        if CACHE['checked'] is None or time.monotonic() - CACHE['checked'] >= 60:
            try:
                CACHE['limits'] = alarm.validate_limits(alarm.fetch_limits(alarm.default_codex()))
                CACHE['error'] = ''
                CACHE['fetched_at'] = time.time()
            except (OSError, RuntimeError, ValueError, KeyError) as error:
                CACHE['error'] = str(error)
            CACHE['checked'] = time.monotonic()
        limits, error, fetched_at = CACHE['limits'], CACHE['error'], CACHE.get('fetched_at')
    state = alarm.read_state(alarm.DEFAULT_STATE)
    return {'fetched_at': fetched_at, 'notifications_enabled': preferences.enabled(), 'running': alarm.monitor_running(),
            'reset': alarm.five_hour_reset(limits) or state.get('reset'),
            'credits': redact(limits.get('rateLimitResetCredits') or state.get('reset_credits', {})),
            'last_check': state.get('last_check'), 'last_alarm': state.get('last_alarm'),
            'error': error or state.get('last_error', ''), 'csrf_token': TOKEN,
            'test_alarm_active': ALARM_LOCK.locked(), 'state': redact(state),
            'limits': redact(limits),
            'iphone': {'status': '未确认', 'configured': False,
                       'instructions': '在电脑运行启动iPhone同步.command，然后按iPhone设置.md在手机创建快捷指令；手机需亲自运行，网页无法确认闹钟已创建。'}}


def connection_info():
    # Lazy import avoids the dashboard/bridge module initialization cycle.
    import iphone_bridge
    unavailable = {'available': False, 'action': '请先安装或启动 iPhone 同步服务，然后刷新。'}
    try:
        if not iphone_bridge.TOKEN_PATH.exists():
            return unavailable
        token = iphone_bridge.TOKEN_PATH.read_text().strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', token):
            return {'available': False, 'action': '连接配置无效，请重新配置 iPhone 同步服务。'}
        if not iphone_bridge.existing_service('127.0.0.1', token):
            return unavailable
        hostname = iphone_bridge.stable_address()
        valid_hostname = isinstance(hostname, str) and re.fullmatch(r'[A-Za-z0-9-]+\.local', hostname)
        if not valid_hostname:
            try:
                parsed = ipaddress.IPv4Address(hostname)
                valid_hostname = not parsed.is_loopback and not parsed.is_unspecified
            except (ValueError, TypeError):
                pass
        if not valid_hostname:
            return {'available': False, 'action': '未找到稳定主机名，请检查系统共享设置。'}
        base = f'http://{hostname}:8766/{token}/'
        result = {'available': True, 'hostname_url': base, 'data_url': base + 'alarm.json',
                  'ip_url': None, 'ip_data_url': None}
        try:
            address = str(ipaddress.IPv4Address(iphone_bridge.local_ip()))
            if ipaddress.IPv4Address(address).is_loopback or ipaddress.IPv4Address(address).is_unspecified:
                raise ValueError('No LAN address')
            ip_base = f'http://{address}:8766/{token}/'
            result.update(ip_url=ip_base, ip_data_url=ip_base + 'alarm.json')
        except (OSError, ValueError):
            pass
        return result
    except (OSError, ValueError):
        return {'available': False, 'action': '暂时无法读取连接配置，请检查同步服务后刷新。'}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, content, content_type='application/json; charset=utf-8'):
        body = content if isinstance(content, bytes) else json.dumps(content, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not allowed_host(self.headers.get('Host')):
            return self.respond(403, {'error': 'Invalid Host'})
        if self.path == '/api/connection':
            return self.respond(200, connection_info())
        if self.path == '/api/status':
            return self.respond(200, snapshot())
        if self.path == '/iphone-setup':
            return self.respond(200, (ROOT / 'web/iphone-setup.html').read_bytes(), 'text/html; charset=utf-8')
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
        if self.path == '/api/settings':
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 1024:
                    return self.respond(400, {'error': 'Invalid size'})
                value = preferences.parse(self.rfile.read(size))
                preferences.save(value)
                return self.respond(200, {'notifications_enabled': value})
            except (ValueError, OSError):
                return self.respond(400, {'error': 'Invalid settings'})
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
