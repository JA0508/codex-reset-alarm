import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import alarm


class AlarmTests(unittest.TestCase):
    def test_select_five_hour_window(self):
        data = {'rateLimits': {'primary': {'windowDurationMins': 300, 'resetsAt': 123}, 'secondary': {'windowDurationMins': 10080, 'resetsAt': 999}}}
        self.assertEqual(alarm.five_hour_reset(data), 123)
        self.assertIsNone(alarm.five_hour_reset({'rateLimits': None}))

    def test_new_buckets_and_multiple_resets(self):
        data = {'rateLimitsByLimitId': {'a': {'primary': {'windowDurationMins': 300, 'resetsAt': 120}}, 'b': {'primary': {'windowDurationMins': 300, 'resetsAt': 130}}}}
        self.assertEqual(alarm.five_hour_reset(data), 120)

    def test_first_expired_is_not_reported(self):
        state, due = alarm.advance({}, 90, 100)
        self.assertFalse(due)
        self.assertEqual(state['notified_reset'], 90)

    def test_wake_reports_once_even_if_api_moved_window(self):
        state, due = alarm.advance({}, 120, 100)
        self.assertFalse(due)
        state, due = alarm.advance(state, 500, 130)
        self.assertEqual(due, 120)
        state, due = alarm.advance(state, 500, 140)
        self.assertFalse(due)
        state, due = alarm.advance(state, 500, 501)
        self.assertEqual(due, 500)

    def test_api_failure_still_reports_saved_deadline(self):
        state, due = alarm.advance({'reset': 120}, None, 130)
        self.assertEqual(due, 120)
        self.assertEqual(state['reset'], 120)

    def test_state_io_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            self.assertEqual(alarm.read_state(path), {})
            alarm.write_state(path, {'reset': 120})
            self.assertEqual(alarm.read_state(path), {'reset': 120})
            path.write_text('bad')
            self.assertEqual(alarm.read_state(path), {})

    def test_rpc_notifications_and_errors(self):
        class FakeProcess:
            stdin = io.StringIO()
            stdout = io.StringIO('\n'.join([json.dumps({'method': 'notice'}), json.dumps({'id': 1, 'result': {}}), json.dumps({'id': 2, 'result': {'rateLimits': None}})]) + '\n')
            def terminate(self): pass
            def wait(self, timeout): pass
        with patch('alarm.subprocess.Popen', return_value=FakeProcess()):
            self.assertEqual(alarm.fetch_limits('codex'), {'rateLimits': None})

    def test_rpc_error_and_eof(self):
        with self.assertRaises(RuntimeError):
            alarm.read_response(io.StringIO('{"id":1,"error":{"message":"no"}}\n'), 1)
        with self.assertRaises(RuntimeError):
            alarm.read_response(io.StringIO(''), 1)

    def test_invalid_timestamps_ignored(self):
        for value in [None, True, '120', -1]:
            self.assertIsNone(alarm.five_hour_reset({'rateLimits': {'primary': {'windowDurationMins': 300, 'resetsAt': value}}}))

class CommandTests(unittest.TestCase):
    def test_status(self):
        with patch('alarm.fetch_limits', return_value={'rateLimits': {'primary': {'windowDurationMins': 300, 'resetsAt': 120}}}), patch('builtins.print'):
            self.assertEqual(alarm.main(['status']), 0)
        with patch('alarm.fetch_limits', side_effect=RuntimeError('offline')), patch('builtins.print'):
            self.assertEqual(alarm.main(['status']), 1)

    def test_alert_cli(self):
        with patch('alarm.alert') as notify:
            self.assertEqual(alarm.main(['test-alarm']), 0)
            notify.assert_called_once()

    def test_automatic_alert_disabled_initially(self):
        with patch('alarm.preferences.enabled', return_value=False), patch('alarm.subprocess.Popen') as process:
            self.assertFalse(alarm.alert(respect_preference=True))
            process.assert_not_called()

    def test_disable_stops_active_dialog_and_sound(self):
        from unittest.mock import MagicMock
        dialog, sound = MagicMock(), MagicMock()
        dialog.poll.return_value = None
        sound.poll.return_value = None
        with patch('alarm.preferences.enabled', side_effect=[True, True, False]), patch('alarm.subprocess.Popen', side_effect=[dialog, sound]), patch('alarm.time.sleep'):
            self.assertTrue(alarm.alert(respect_preference=True))
        dialog.terminate.assert_called_once()
        sound.terminate.assert_called_once()

    def test_manual_alert_times_out_even_when_preferences_disabled(self):
        from unittest.mock import MagicMock
        dialog, sound = MagicMock(), MagicMock()
        dialog.poll.return_value = None
        sound.poll.return_value = None
        with patch('alarm.preferences.enabled', return_value=False), patch('alarm.subprocess.Popen', side_effect=[dialog, sound]), patch('alarm.time.monotonic', side_effect=[0, 0, 301]), patch('alarm.time.sleep'):
            self.assertTrue(alarm.alert())
        dialog.terminate.assert_called_once()

    def test_run_saved_due_and_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            alarm.write_state(path, {'reset': 1})
            with patch('alarm.fetch_limits', side_effect=RuntimeError('offline')), patch('alarm.alert') as notify, patch('alarm.time.sleep', side_effect=KeyboardInterrupt), patch('builtins.print'):
                self.assertEqual(alarm.main(['run', '--state', str(path)]), 0)
                notify.assert_called_once()
            self.assertEqual(alarm.read_state(path)['notified_reset'], 1)

    def test_run_new_window(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            with patch('alarm.fetch_limits', return_value={'rateLimits': {'primary': {'windowDurationMins': 300, 'resetsAt': 9999999999}}}), patch('alarm.time.sleep', side_effect=KeyboardInterrupt), patch('builtins.print'):
                alarm.main(['run', '--state', str(path)])
            self.assertEqual(alarm.read_state(path)['reset'], 9999999999)

    def test_no_window_and_invalid_interval(self):
        with patch('alarm.fetch_limits', return_value={}), patch('builtins.print'):
            self.assertEqual(alarm.main(['status']), 0)
        with self.assertRaises(SystemExit), patch('sys.stderr', new=io.StringIO()):
            alarm.main(['run', '--interval', '0'])


    def test_codex_bucket_preferred(self):
        data = {'rateLimitsByLimitId': {'other': {'primary': {'windowDurationMins': 300, 'resetsAt': 20}}, 'codex': {'primary': {'windowDurationMins': 300, 'resetsAt': 120}}}, 'rateLimits': {'primary': {'windowDurationMins': 300, 'resetsAt': 30}}}
        self.assertEqual(alarm.five_hour_reset(data), 120)

    def test_due_delivered_and_saved_before_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            alarm.write_state(path, {'reset': 1})
            with patch('alarm.alert') as notify, patch('builtins.print'):
                def fetch(codex):
                    notify.assert_called_once()
                    self.assertEqual(alarm.read_state(path)['notified_reset'], 1)
                    raise KeyboardInterrupt
                with patch('alarm.fetch_limits', side_effect=fetch):
                    self.assertEqual(alarm.main(['run', '--state', str(path)]), 0)

    def test_credit_increase_only(self):
        self.assertFalse(alarm.credits_increased({}, {'availableCount': 2}))
        self.assertTrue(alarm.credits_increased({'availableCount': 1}, {'availableCount': 2}))
        self.assertFalse(alarm.credits_increased({'availableCount': 2}, {'availableCount': 1}))


if __name__ == '__main__':
    unittest.main()

class MonitorTests(unittest.TestCase):
    def test_lock_controls_running_status(self):
        import fcntl
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            lock_path = path.with_suffix('.lock')
            self.assertFalse(alarm.monitor_running(path))
            self.assertFalse(lock_path.exists())
            with lock_path.open('w') as held:
                self.assertFalse(alarm.monitor_running(path))
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertTrue(alarm.monitor_running(path))
                fcntl.flock(held, fcntl.LOCK_UN)
                self.assertFalse(alarm.monitor_running(path))
