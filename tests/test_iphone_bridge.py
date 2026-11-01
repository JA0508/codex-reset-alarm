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
