import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import iphone_bridge as bridge

class BridgeTests(unittest.TestCase):
    def test_minute_rounding_and_expiry(self):
        with patch('iphone_bridge.time.time', return_value=100):
            self.assertEqual(bridge.alarm_payload(121)['timestamp'], 180)
            with self.assertRaises(ValueError): bridge.alarm_payload(99)
    def test_token_is_persistent_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'token'
            token = bridge.load_token(path)
            self.assertEqual(token, bridge.load_token(path))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
    def test_secret_path_match(self):
        self.assertTrue(bridge.valid_path('/abc/alarm.json', 'abc'))
        self.assertFalse(bridge.valid_path('/other/alarm.json', 'abc'))

class StartupTests(unittest.TestCase):
    def test_existing_matching_service(self):
        with patch('iphone_bridge.load_token', return_value='abc'), patch('iphone_bridge.local_ip', return_value='192.168.1.2'), patch('iphone_bridge.ThreadingHTTPServer', side_effect=OSError(48, 'used')), patch('iphone_bridge.existing_service', return_value=True), patch('builtins.print'):
            self.assertEqual(bridge.main(), 0)
    def test_other_service_is_not_accepted(self):
        with patch('iphone_bridge.load_token', return_value='abc'), patch('iphone_bridge.local_ip', return_value='192.168.1.2'), patch('iphone_bridge.ThreadingHTTPServer', side_effect=OSError(48, 'used')), patch('iphone_bridge.existing_service', return_value=False), patch('builtins.print'):
            self.assertEqual(bridge.main(), 1)

class PhoneTests(unittest.TestCase):
    def test_safe_status(self):
        with patch('iphone_bridge.dashboard.snapshot', return_value={'running':True,'reset':123,'csrf_token':'secret','state':{'secret':1},'limits':{},'credits':{},'error':''}):
            value = bridge.phone_status()
            self.assertTrue(value['phone_mode'])
            self.assertNotIn('csrf_token', value)
            self.assertNotIn('state', value)
    def test_stable_address(self):
        with patch('iphone_bridge.subprocess.run') as run:
            run.return_value.stdout = 'My-Mac\n'
            self.assertEqual(bridge.stable_address(), 'My-Mac.local')

class PrivacyTests(unittest.TestCase):
    def test_invalid_saved_token_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'token'
            path.write_text('')
            with self.assertRaises(RuntimeError):
                bridge.load_token(path)

    def test_quiet_start_does_not_print_access_token(self):
        with patch('iphone_bridge.load_token', return_value='private-test-token'), patch('iphone_bridge.stable_address', return_value='test.local'), patch('iphone_bridge.ThreadingHTTPServer') as server, patch('builtins.print') as output:
            server.return_value.serve_forever.side_effect = KeyboardInterrupt
            self.assertEqual(bridge.main(['--quiet']), 0)
            self.assertNotIn('private-test-token', str(output.call_args_list))

class AddressFallbackTests(unittest.TestCase):
    def test_fallback_never_points_phone_to_loopback(self):
        with patch('iphone_bridge.subprocess.run', side_effect=OSError), patch('iphone_bridge.local_ip', return_value='127.0.0.1'):
            self.assertIsNone(bridge.stable_address())
        with patch('iphone_bridge.subprocess.run', side_effect=OSError), patch('iphone_bridge.local_ip', return_value='192.168.1.9'):
            self.assertEqual(bridge.stable_address(), '192.168.1.9')

class FastAlarmTests(unittest.TestCase):
    def test_fresh_monitor_avoids_rpc(self):
        with patch('iphone_bridge.preferences.enabled', return_value=True), patch('iphone_bridge.time.time', return_value=1000), patch('iphone_bridge.alarm.read_state', return_value={'reset':2000,'last_check':950}), patch('iphone_bridge.alarm.fetch_limits') as fetch:
            code, payload = bridge.phone_alarm_payload()
            self.assertEqual(code, 200)
            self.assertEqual(payload['source'], 'monitor')
            fetch.assert_not_called()
    def test_stale_or_future_check_uses_bounded_live_request(self):
        for checked in (800, 1010):
            with patch('iphone_bridge.preferences.enabled', return_value=True), patch('iphone_bridge.time.time', return_value=1000), patch('iphone_bridge.alarm.read_state', return_value={'reset':2000,'last_check':checked}), patch('iphone_bridge.alarm.fetch_limits', side_effect=RuntimeError('private')) as fetch:
                code, payload = bridge.phone_alarm_payload()
                self.assertEqual(code, 503)
                self.assertNotIn('private', str(payload))
                self.assertEqual(fetch.call_args.kwargs['timeout'], 2)
    def test_paused_never_calls_rpc(self):
        with patch('iphone_bridge.preferences.enabled', return_value=False), patch('iphone_bridge.alarm.fetch_limits') as fetch:
            code, payload = bridge.phone_alarm_payload()
            self.assertEqual(code, 200)
            self.assertFalse(payload['enabled'])
            fetch.assert_not_called()
    def test_expired_cache_refreshes_and_live_expired_is_409(self):
        limits = {'rateLimits': {'primary': {'windowDurationMins': 300, 'resetsAt': 900}}}
        with patch('iphone_bridge.preferences.enabled', return_value=True), patch('iphone_bridge.time.time', return_value=1000), patch('iphone_bridge.alarm.read_state', return_value={'reset':900,'last_check':990}), patch('iphone_bridge.alarm.fetch_limits', return_value=limits) as fetch:
            self.assertEqual(bridge.phone_alarm_payload()[0], 409)
            self.assertEqual(fetch.call_args.kwargs['timeout'], 2)
    def test_live_future_is_compatible(self):
        limits = {'rateLimits': {'primary': {'windowDurationMins': 300, 'resetsAt': 2000}}}
        with patch('iphone_bridge.preferences.enabled', return_value=True), patch('iphone_bridge.time.time', return_value=1000), patch('iphone_bridge.alarm.read_state', return_value={}), patch('iphone_bridge.alarm.fetch_limits', return_value=limits):
            code, payload = bridge.phone_alarm_payload()
            self.assertEqual(code, 200)
            self.assertTrue(payload['enabled'])
            self.assertEqual(payload['source'], 'live')
            self.assertIsInstance(payload['date'], str)
