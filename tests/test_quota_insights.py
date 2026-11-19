import unittest
import quota_insights


class QuotaInsightsTests(unittest.TestCase):
    def test_missing_and_invalid_values(self):
        self.assertEqual(quota_insights.summarize({}, {}, 100)['windows'], [])
        for value in (True, float('nan'), -1, 101):
            result = quota_insights.summarize({'rateLimits': {'primary': {'windowDurationMins': 300, 'usedPercent': value}}}, {}, 100)
            self.assertIsNone(result['windows'][0]['remaining_percent'])

    def test_codex_bucket_and_exhaustion(self):
        limits = {'rateLimits': {'primary': {'windowDurationMins': 300, 'usedPercent': 0}}, 'rateLimitsByLimitId': {'codex': {'primary': {'windowDurationMins': 300, 'usedPercent': 100, 'resetsAt': 200}, 'secondary': {'windowDurationMins': 10080, 'usedPercent': 25, 'resetsAt': 300}}}}
        result = quota_insights.summarize(limits, {}, 100)
        self.assertEqual(result['exhausted'], ['five_hour'])
        self.assertEqual(result['windows'][1]['remaining_percent'], 75)
        self.assertEqual(result['resume_at'], 200)

    def test_expiring_only_available_future(self):
        credits = {'credits': [{'status': 'available', 'expiresAt': 101}, {'status': 'available', 'expiresAt': 99}, {'status': 'consumed', 'expiresAt': 102}, {'status': 'available', 'expiresAt': 999999}]}
        result = quota_insights.summarize({}, credits, 100)
        self.assertEqual(result['expiring_count'], 1)
        self.assertEqual(result['next_expiry'], 101)
