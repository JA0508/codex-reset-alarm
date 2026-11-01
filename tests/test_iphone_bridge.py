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
