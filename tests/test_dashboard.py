import unittest
import dashboard

class DashboardTests(unittest.TestCase):
    def test_redaction(self):
        self.assertEqual(dashboard.redact({'id': 'secret', 'availableCount': 2, 'nested': {'creditId': 'x'}}), {'availableCount': 2, 'nested': {}})
    def test_boundaries(self):
        self.assertTrue(dashboard.allowed_host('127.0.0.1:8765'))
        self.assertFalse(dashboard.allowed_host('evil.example'))
        self.assertFalse(dashboard.allowed_host('127.0.0.1:8765.evil'))
    def test_auth(self):
        self.assertTrue(dashboard.authorized('http://127.0.0.1:8765', 'abc', 'abc'))
        self.assertFalse(dashboard.authorized(None, 'abc', 'abc'))
        self.assertFalse(dashboard.authorized('https://evil', 'abc', 'abc'))
        self.assertFalse(dashboard.authorized('http://127.0.0.1:8765', 'bad', 'abc'))

class CacheTests(unittest.TestCase):
    def test_cache_and_error_retains_limits(self):
        from unittest.mock import patch
        original = dict(dashboard.CACHE)
        try:
            dashboard.CACHE.update(checked=0, limits={}, error='')
            with patch('dashboard.alarm.fetch_limits', return_value={'rateLimitResetCredits': {'availableCount': 2, 'creditId': 'private'}}) as fetch, patch('dashboard.alarm.read_state', return_value={}):
                first = dashboard.snapshot()
                dashboard.snapshot()
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(first['credits'], {'availableCount': 2})
            dashboard.CACHE['checked'] = 0
            with patch('dashboard.alarm.fetch_limits', side_effect=RuntimeError('offline')), patch('dashboard.alarm.read_state', return_value={}):
                failed = dashboard.snapshot()
                self.assertEqual(failed['credits']['availableCount'], 2)
                self.assertEqual(failed['error'], 'offline')
        finally:
            dashboard.CACHE.update(original)
