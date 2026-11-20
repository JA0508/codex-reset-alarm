"""Private account-scoped numeric observations, without credentials or conversations."""
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import threading

PATH = Path.home() / 'Library/Application Support/CodexResetAlarm/usage-history.json'
LOCK = threading.Lock()


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value < 10**12


def account_scope():
    try:
        root = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
        account = json.loads((root / 'auth.json').read_text()).get('tokens', {}).get('account_id')
        return hashlib.sha256(account.encode()).hexdigest() if isinstance(account, str) and account else None
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def clean_windows(windows):
    if not isinstance(windows, list):
        return []
    return [{'kind': w['kind'], 'remaining_percent': w['remaining_percent'], 'reset': w['reset']}
            for w in windows[:10] if isinstance(w, dict) and w.get('kind') in ('five_hour', 'weekly')
            and number(w.get('remaining_percent')) and w['remaining_percent'] <= 100
            and number(w.get('reset')) and w['reset'] > 0]


def events(samples):
    result = []
    for previous, current in zip(samples, samples[1:]):
        old = {w['kind']: w for w in previous['windows']}
        for w in current['windows']:
            before = old.get(w['kind'])
            if before and before['reset'] != w['reset']:
                recovered = before['reset'] <= current['at'] and w['reset'] > before['reset'] and w['remaining_percent'] > before['remaining_percent']
                result.append({'at': current['at'], 'kind': w['kind'], 'message': '观察到新周期，额度恢复' if recovered else '刷新计划已变化'})
    return result[-20:]


def observe(windows, observed_at, expected_scope=None):
    empty = {'samples': [], 'events': [], 'error': ''}
    scope = account_scope()
    if expected_scope is not None and scope != expected_scope:
        return {**empty, 'error': '账号已切换，等待新读数'}
    if not scope:
        return {**empty, 'error': '无法确认账号，暂不记录额度历史'}
    if not number(observed_at) or observed_at <= 0:
        return empty
    try:
        with LOCK:
            PATH.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(str(PATH) + '.lock', os.O_CREAT | os.O_RDWR, 0o600)
            with os.fdopen(descriptor, 'w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    saved = json.loads(PATH.read_text()) if PATH.stat().st_size <= 1024 * 1024 else {}
                except (OSError, ValueError):
                    saved = {}
                raw = saved.get('samples', []) if isinstance(saved, dict) and saved.get('scope') == scope else []
                latest = max([observed_at, *[row['at'] for row in raw[-2000:] if isinstance(row, dict) and number(row.get('at'))]]) if isinstance(raw, list) else observed_at
                samples = [{'at': row['at'], 'windows': clean_windows(row.get('windows'))}
                           for row in raw[-2000:] if isinstance(row, dict) and number(row.get('at'))
                           and latest - 604800 <= row['at'] <= latest] if isinstance(raw, list) else []
                clean = clean_windows(windows)
                last = samples[-1] if samples else None
                if clean and (not last or observed_at > last['at'] and observed_at - last['at'] >= 60 and
                              (clean != last['windows'] or observed_at - last['at'] >= 900)):
                    samples = [*samples, {'at': observed_at, 'windows': clean}][-2000:]
                    fd, name = tempfile.mkstemp(prefix='.usage-history-', dir=PATH.parent)
                    try:
                        with os.fdopen(fd, 'w') as output:
                            json.dump({'scope': scope, 'samples': samples}, output)
                        os.replace(name, PATH)
                    finally:
                        Path(name).unlink(missing_ok=True)
                return {'samples': samples, 'events': events(samples), 'error': ''}
    except (OSError, ValueError, TypeError):
        return {**empty, 'error': '本地观察记录暂不可用'}
