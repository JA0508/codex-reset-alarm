#!/usr/bin/env python3
"""Local macOS alarm for Codex's five-hour usage window."""
import argparse
import preferences
import datetime
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

DEFAULT_STATE = Path.home() / 'Library/Application Support/CodexResetAlarm/state.json'


def valid_reset(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value < 10**12


def five_hour_reset(data):
    """Prefer the Codex bucket, then the legacy/default usage bucket."""
    by_id = data.get('rateLimitsByLimitId') or {}
    if isinstance(by_id.get('codex'), dict):
        buckets = [by_id['codex']]
    elif isinstance(data.get('rateLimits'), dict):
        buckets = [data['rateLimits']]
    else:
        buckets = list(by_id.values())
    resets = [window['resetsAt'] for bucket in buckets if isinstance(bucket, dict)
              for window in bucket.values() if isinstance(window, dict)
              and window.get('windowDurationMins') == 300
              and valid_reset(window.get('resetsAt'))]
    return min(resets) if resets else None


def advance(state, observed_reset, now):
    """Pure deadline transition: catch saved deadlines before adopting new ones."""
    result = dict(state)
    previous = state.get('reset')
    due = previous if (valid_reset(previous) and previous <= now
                       and state.get('notified_reset', 0) < previous) else None
    if due:
        result['notified_reset'] = due
    if valid_reset(observed_reset):
        result['reset'] = observed_reset
        # Never infer a missed alarm from an already-expired initial observation.
        if not valid_reset(previous) and observed_reset <= now:
            result['notified_reset'] = observed_reset
    return result, due


def read_state(path):
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            return {}
        return {key: value for key, value in data.items()
                if ((key in ('reset', 'notified_reset', 'heartbeat', 'last_check', 'last_alarm') and valid_reset(value))
                    or (key == 'last_error' and isinstance(value, str))
                    or (key == 'reset_credits' and isinstance(value, dict)))}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state))
    temporary.chmod(0o600)
    os.replace(temporary, path)


def read_response(stream, request_id):
    for line in stream:
        message = json.loads(line)
        if message.get('id') == request_id:
            if 'error' in message:
                raise RuntimeError('Codex RPC: ' + str(message['error']))
            return message['result']
    raise RuntimeError('Codex app-server 已退出或请求超时')


def fetch_limits(codex):
    process = subprocess.Popen([codex, 'app-server'], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True)
    timer = threading.Timer(20, process.terminate)
    timer.daemon = True
    timer.start()
    try:
        def send(message):
            process.stdin.write(json.dumps(message) + '\n')
            process.stdin.flush()
        send({'id': 1, 'method': 'initialize', 'params': {
            'clientInfo': {'name': 'codex_reset_alarm', 'version': '1.0.0'}}})
        read_response(process.stdout, 1)
        send({'method': 'initialized', 'params': {}})
        send({'id': 2, 'method': 'account/rateLimits/read', 'params': {}})
        return read_response(process.stdout, 2)
    finally:
        timer.cancel()
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def stop_process(process):
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def alert(message='Codex 的 5 小时额度窗口已到重置时间。', respect_preference=False):
    if respect_preference and not preferences.enabled():
        return False
    dialog = sound = None
    sounded = False
    deadline = time.monotonic() + 300
    try:
        dialog = subprocess.Popen(['/usr/bin/osascript', '-e',
            'on run argv\n display dialog (item 1 of argv) with title "Codex 额度闹钟" '
            'buttons {"停止闹铃"} default button 1 giving up after 300\nend run', message],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while True:
            if respect_preference and not preferences.enabled():
                break
            if time.monotonic() >= deadline:
                break
            status = dialog.poll()
            if status is not None:
                if status != 0:
                    raise subprocess.CalledProcessError(status, 'osascript')
                break
            if sound is None or sound.poll() is not None:
                if sound is not None:
                    if sound.returncode != 0:
                        raise subprocess.CalledProcessError(sound.returncode, 'afplay')
                    sound.wait(timeout=2)
                sound = subprocess.Popen(['/usr/bin/afplay', '/System/Library/Sounds/Glass.aiff'],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                sounded = True
            time.sleep(0.1)
        return sounded
    finally:
        try:
            stop_process(sound)
        finally:
            stop_process(dialog)


def credits_increased(previous, current):
    old, new = previous.get('availableCount'), current.get('availableCount')
    return (type(old) in (int, float) and type(new) in (int, float) and new > old)


def format_time(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')


def deliver_transition(state, reset, path):
    updated, due = advance(state, reset, time.time())
    try:
        if due:
            if preferences.enabled():
                if alert(respect_preference=True):
                    updated = {**updated, 'last_alarm': time.time()}
                    print('已提醒：' + format_time(due), flush=True)
        if updated != state:
            write_state(path, updated)
            if updated.get('reset') != state.get('reset'):
                print('下一次重置：' + format_time(updated['reset']), flush=True)
        return updated
    except (OSError, subprocess.SubprocessError) as error:
        print(f'提醒或保存失败，将重试：{error}', file=sys.stderr, flush=True)
        return state


def default_codex():
    local = Path.home() / '.local/bin/codex'
    return shutil.which('codex') or (str(local) if local.is_file() else
                                    '/Applications/Codex.app/Contents/Resources/codex')


def run(codex, path, interval):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('闹钟已在运行，请勿重复启动') from None
        state = read_state(path)
        while True:
            state = {**state, 'heartbeat': time.time()}
            write_state(path, state)
            state = deliver_transition(state, None, path)
            reset = None
            try:
                payload = fetch_limits(codex)
                reset = five_hour_reset(payload)
                credits = payload.get('rateLimitResetCredits') or {}
                if preferences.enabled() and credits_increased(state.get('reset_credits', {}), credits):
                    if alert('Codex 赠送的额度重置次数增加了，请前往 Codex 查看。', respect_preference=True):
                        state = {**state, 'last_alarm': time.time()}
                state = {**state, 'last_check': time.time(), 'last_error': '',
                         **({'reset_credits': credits} if credits else {})}
                write_state(path, state)
                if reset is None:
                    print('未找到 5 小时额度窗口；稍后重试。', flush=True)
            except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
                state = {**state, 'last_error': str(error)}
                write_state(path, state)
                print(f'读取额度失败，稍后重试：{error}', file=sys.stderr, flush=True)
            state = deliver_transition(state, reset, path)
            remaining = state.get('reset', 0) - time.time()
            time.sleep(min(interval, max(1, remaining)) if remaining > 0 else interval)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Codex 5 小时额度重置闹钟（macOS）')
    parser.add_argument('command', choices=['status', 'run', 'test-alarm'])
    parser.add_argument('--codex', default=default_codex())
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--interval', type=int, default=60)
    args = parser.parse_args(argv)
    if args.interval < 1:
        parser.error('--interval 必须大于 0')
    try:
        if args.command == 'test-alarm':
            alert()
        elif args.command == 'status':
            saved = read_state(args.state)
            heartbeat = saved.get('heartbeat', 0)
            print('监测状态：' + ('运行中（最近心跳）' if time.time() - heartbeat < 120 else '未运行或心跳过期'))
            for key in ('last_check', 'last_alarm'):
                if saved.get(key):
                    print(key + '：' + format_time(saved[key]))
            if saved.get('last_error'):
                print('最近错误：' + saved['last_error'])
            payload = fetch_limits(args.codex)
            credits = payload.get('rateLimitResetCredits')
            print('赠送重置次数/到期信息：' + json.dumps(credits, ensure_ascii=False) if credits else '赠送重置信息：接口未提供')
            print('未来赠送时间：接口未提供，无法预测')
            reset = five_hour_reset(payload)
            print('下一次 5 小时额度重置：' + format_time(reset) if reset else '未找到 5 小时额度窗口，请确认 Codex 已登录 ChatGPT 账号。')
        else:
            print('闹钟已启动；保持此终端打开，按 Control+C 停止。', flush=True)
            run(args.codex, args.state, args.interval)
    except KeyboardInterrupt:
        print('\n闹钟已停止。')
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
