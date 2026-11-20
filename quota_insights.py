"""Pure, conservative summaries of reported usage windows and reset expiry."""
import math


def number(value, minimum=0, maximum=10**12):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and minimum <= value <= maximum)


def pace_reference(used, reset, duration, now):
    empty = {'elapsed_percent': None, 'pace_delta': None, 'pace_message': ''}
    if used is None or not number(reset, minimum=1) or not number(now):
        return empty
    remaining = reset - now
    if not 0 < remaining <= duration * 60:
        return empty
    elapsed = 100 * (1 - remaining / (duration * 60))
    if elapsed < 3:
        return empty
    elapsed = round(elapsed, 1)
    return {'elapsed_percent': elapsed, 'pace_delta': round(used - elapsed, 1),
            'pace_message': f'已用 {used:g}% · 时间已过 {elapsed:g}%（均匀进度参考）'}


def summarize(limits, credits, now):
    limits = limits if isinstance(limits, dict) else {}
    by_id = limits.get('rateLimitsByLimitId')
    by_id = by_id if isinstance(by_id, dict) else {}
    preferred = by_id.get('codex', limits.get('rateLimits'))
    buckets = [preferred] if isinstance(preferred, dict) else list(by_id.values())
    windows = []
    for duration, kind in ((300, 'five_hour'), (10080, 'weekly')):
        matches = [item for bucket in buckets if isinstance(bucket, dict)
                   for item in bucket.values() if isinstance(item, dict)
                   and item.get('windowDurationMins') == duration]
        if not matches:
            continue
        window = matches[0]
        used = window.get('usedPercent')
        used = used if number(used, maximum=100) else None
        reset = window.get('resetsAt')
        windows.append({'kind': kind, 'used_percent': used,
                        'remaining_percent': 100 - used if used is not None else None,
                        'reset': reset if number(reset, minimum=1) else None,
                        **pace_reference(used, reset, duration, now)})
    exhausted = [window['kind'] for window in windows if window['remaining_percent'] == 0]
    deadlines = [window['reset'] for window in windows if window['kind'] in exhausted
                 and window['reset'] is not None and window['reset'] > now]
    rows = credits.get('credits', []) if isinstance(credits, dict) else []
    rows = rows if isinstance(rows, list) else []
    expiries = [row['expiresAt'] for row in rows if isinstance(row, dict)
                and row.get('status') == 'available' and number(row.get('expiresAt'), minimum=1)
                and now < row['expiresAt'] <= now + 72 * 3600]
    if exhausted:
        names = '、'.join('每周额度' if kind == 'weekly' else '5 小时额度' for kind in exhausted)
        message = names + '已用尽，等待刷新后再试'
    elif any(window['remaining_percent'] is not None for window in windows):
        message = '额度尚有剩余（以 Codex 实际请求为准）'
    else:
        message = '等待额度数据'
    return {'windows': windows, 'exhausted': exhausted,
            'resume_at': max(deadlines) if len(deadlines) == len(exhausted) and deadlines else None,
            'expiring_count': len(expiries), 'next_expiry': min(expiries) if expiries else None,
            'message': message}
