import unittest
from unittest.mock import patch
import reset_credits as rc


class CreditTests(unittest.TestCase):
    def test_normalize_dates_and_whitelist(self):
        result = rc.normalize({'available_count': 1, 'credits': [{'granted_at': '2026-01-01T00:00:00Z', 'expires_at': 1795095106, 'id': 'secret', 'title': 'Full reset'}]})
        self.assertEqual(result['credits'][0]['grantedAt'], 1767225600)
        self.assertNotIn('id', result['credits'][0])

    def test_invalid_dates(self):
        for value in [True, float('inf'), -1, 'invalid', '2026-01-01']:
            self.assertIsNone(rc.timestamp(value))

    def test_bad_payload(self):
        for value in [None, {}, {'available_count': True}, {'available_count': 1, 'credits': [None]}]:
            with self.assertRaises(ValueError):
                rc.normalize(value)

    def test_no_redirect(self):
        self.assertIsNone(rc.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example'))

    def test_cache_and_safe_failure(self):
        empty = {'checked': None, 'credits': None, 'fetched_at': None, 'error': ''}
        with patch.object(rc, 'CACHE', empty), patch.object(rc, 'fetch', side_effect=ValueError('secret')) as fetch:
            self.assertNotIn('secret', rc.snapshot()['error'])
            rc.snapshot()
            self.assertEqual(fetch.call_count, 1)
