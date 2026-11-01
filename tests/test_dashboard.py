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
            dashboard.CACHE.update(checked=None, limits={}, error='')
            with patch('dashboard.time.monotonic', return_value=5), patch('dashboard.alarm.fetch_limits', return_value={'rateLimitResetCredits': {'availableCount': 2, 'creditId': 'private'}}) as fetch, patch('dashboard.alarm.read_state', return_value={}):
                first = dashboard.snapshot()
                dashboard.snapshot()
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(first['credits'], {'availableCount': 2})
            dashboard.CACHE['checked'] = None
            with patch('dashboard.alarm.fetch_limits', side_effect=RuntimeError('offline')), patch('dashboard.alarm.read_state', return_value={}):
                failed = dashboard.snapshot()
                self.assertEqual(failed['credits']['availableCount'], 2)
                self.assertEqual(failed['error'], 'offline')
        finally:
            dashboard.CACHE.update(original)

class ConnectionTests(unittest.TestCase):
    def test_no_token_does_not_generate(self):
        from unittest.mock import patch
        import iphone_bridge
        with patch.object(iphone_bridge.TOKEN_PATH.__class__, 'exists', return_value=False), patch('iphone_bridge.load_token') as load:
            value = dashboard.connection_info()
            self.assertFalse(value['available'])
            load.assert_not_called()
    def test_connection_urls(self):
        from unittest.mock import patch
        import iphone_bridge
        with patch.object(iphone_bridge.TOKEN_PATH.__class__, 'exists', return_value=True), patch.object(iphone_bridge.TOKEN_PATH.__class__, 'read_text', return_value='a'*43), patch('iphone_bridge.existing_service', return_value=True), patch('iphone_bridge.stable_address', return_value='Mac.local'), patch('iphone_bridge.local_ip', return_value='192.168.1.3'):
            value = dashboard.connection_info()
            self.assertTrue(value['available'])
            self.assertTrue(value['hostname_url'].startswith('http://Mac.local:8766/'))
            self.assertTrue(value['ip_data_url'].endswith('/alarm.json'))
    def test_invalid_token_not_exposed(self):
        from unittest.mock import patch
        import iphone_bridge
        with patch.object(iphone_bridge.TOKEN_PATH.__class__, 'exists', return_value=True), patch.object(iphone_bridge.TOKEN_PATH.__class__, 'read_text', return_value='../bad'):
            value = dashboard.connection_info()
            self.assertFalse(value['available'])
            self.assertNotIn('../bad', str(value))

class ConnectionHostTests(unittest.TestCase):
    def test_host_rejected_before_connection_lookup(self):
        from unittest.mock import Mock, patch
        for headers in ({}, {'Host': 'evil.example'}):
            handler = object.__new__(dashboard.Handler)
            handler.headers = headers
            handler.path = '/api/connection'
            handler.respond = Mock()
            with patch('dashboard.connection_info') as connection:
                handler.do_GET()
                connection.assert_not_called()
            self.assertEqual(handler.respond.call_args.args[0], 403)

class FreshnessTests(unittest.TestCase):
    def test_failed_refresh_keeps_last_success_time(self):
        from unittest.mock import patch
        with patch.dict(dashboard.CACHE, {'checked': None, 'limits': {}, 'error': '', 'fetched_at': None}, clear=True), patch('dashboard.alarm.read_state', return_value={}):
            with patch('dashboard.alarm.fetch_limits', return_value={}), patch('dashboard.time.time', return_value=1000):
                self.assertEqual(dashboard.snapshot()['fetched_at'], 1000)
            dashboard.CACHE['checked'] = None
            with patch('dashboard.alarm.fetch_limits', side_effect=RuntimeError('offline')), patch('dashboard.time.time', return_value=1100):
                value = dashboard.snapshot()
                self.assertEqual(value['fetched_at'], 1000)
                self.assertEqual(value['error'], 'offline')
