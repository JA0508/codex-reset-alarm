import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import preferences
class PreferencesTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory, patch('preferences.PATH', Path(directory)/'p.json'):
            self.assertTrue(preferences.enabled())
            preferences.save(False)
            self.assertFalse(preferences.enabled())
            self.assertEqual(preferences.PATH.stat().st_mode & 0o777, 0o600)
    def test_validation(self):
        for value in ('{}', '{"enabled":1}', '{"enabled":true,"extra":1}'):
            with self.assertRaises(ValueError): preferences.parse(value)
    def test_disabled_deadline_is_skipped_without_alarm_timestamp(self):
        import alarm
        with tempfile.TemporaryDirectory() as directory, patch('preferences.enabled', return_value=False), patch('alarm.alert') as alert:
            state = alarm.deliver_transition({'reset': 1}, None, Path(directory)/'state.json')
            self.assertEqual(state['notified_reset'], 1)
            self.assertNotIn('last_alarm', state)
            alert.assert_not_called()
