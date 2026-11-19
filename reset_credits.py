"""Read-only banked reset metadata; never redeems or persists credentials."""
import json
import math
import os
import ssl
from datetime import datetime
from pathlib import Path
import threading
import time
import urllib.request

ENDPOINT = 'https://chatgpt.com/backend-api/wham/rate-limit-reset-credits'
LOCK = threading.Lock()
CACHE = {'checked': None, 'credits': None, 'fetched_at': None, 'error': ''}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def timestamp(value):
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                return None
            value = parsed.timestamp()
        except (ValueError, OverflowError):
            return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and 0 < value < 253402300800 else None


def normalize(payload):
    if not isinstance(payload, dict):
        raise ValueError('Invalid response')
    count = payload.get('available_count')
    rows = payload.get('credits', [])
    if type(count) is not int or count < 0 or not isinstance(rows, list) or len(rows) > 100:
        raise ValueError('Invalid response')
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError('Invalid response')
    return {'availableCount': count, 'credits': [
        {'grantedAt': timestamp(row.get('granted_at')),
         'expiresAt': timestamp(row.get('expires_at')),
         'status': row.get('status', '')[:64] if isinstance(row.get('status', ''), str) else '',
         'title': row.get('title', '')[:200] if isinstance(row.get('title', ''), str) else ''}
        for row in rows]}


def fetch():
    auth_path = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'auth.json'
    auth = json.loads(auth_path.read_text())
    tokens = auth.get('tokens') or {}
    token, account = tokens.get('access_token'), tokens.get('account_id')
    if not isinstance(token, str) or not token or '\n' in token or '\r' in token:
        raise ValueError('Missing login')
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json',
               'User-Agent': 'codex-reset-alarm', 'OpenAI-Beta': 'codex-1',
               'originator': 'codex_reset_alarm'}
    if isinstance(account, str) and account:
        headers['ChatGPT-Account-Id'] = account
    request = urllib.request.Request(ENDPOINT, headers=headers, method='GET')
    context = ssl.create_default_context()
    # Python.org macOS installs may lack bundled roots; retain verification with OS roots.
    if Path("/etc/ssl/cert.pem").is_file():
        context.load_verify_locations(cafile="/etc/ssl/cert.pem")
    with urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context)).open(request, timeout=5) as response:
        body = response.read(1024 * 1024 + 1)
    if len(body) > 1024 * 1024:
        raise ValueError('Response too large')
    return normalize(json.loads(body))


def snapshot():
    with LOCK:
        if CACHE['checked'] is None or time.monotonic() - CACHE['checked'] >= 180:
            try:
                result = fetch()
                CACHE.update(credits=result, fetched_at=time.time(), error='')
            except Exception:
                # Never expose credential paths, upstream bodies or authentication headers.
                CACHE['error'] = '重置券详情暂时无法读取，请检查 Codex 登录后稍后重试'
            CACHE['checked'] = time.monotonic()
        return {'credits': CACHE['credits'], 'fetched_at': CACHE['fetched_at'],
                'error': CACHE['error']}
