import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import usage_history as h

class HistoryTests(unittest.TestCase):
    def test_dedup_and_scope(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(h, 'PATH', Path(directory)/'history.json'), patch.object(h, 'account_scope', return_value='a'):
            w=[{'kind':'weekly','remaining_percent':20,'reset':2000}]
            self.assertEqual(len(h.observe(w,1000)['samples']),1)
            self.assertEqual(len(h.observe(w,1060)['samples']),1)
            self.assertEqual(len(h.observe(w,1900)['samples']),2)
            with patch.object(h,'account_scope',return_value='b'):
                self.assertEqual(len(h.observe(w,2000)['samples']),1)
    def test_recovery_and_corrupt(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(h, 'PATH', Path(directory)/'history.json'), patch.object(h, 'account_scope', return_value='a'):
            h.PATH.write_text('bad')
            h.observe([{'kind':'weekly','remaining_percent':0,'reset':1100}],1000)
            result=h.observe([{'kind':'weekly','remaining_percent':100,'reset':2000}],1200)
            self.assertIn('恢复',result['events'][0]['message'])
            self.assertEqual(h.PATH.stat().st_mode & 0o777,0o600)
    def test_older_observation_preserves_newer_sample(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(h, 'PATH', Path(directory)/'history.json'), patch.object(h, 'account_scope', return_value='a'):
            w = [{'kind':'weekly','remaining_percent':20,'reset':2000}]
            h.observe(w, 1000)
            before = h.PATH.read_bytes()
            self.assertEqual(h.observe(w, 900)['samples'][0]['at'], 1000)
            h.observe(w, 1000)
            self.assertEqual(h.PATH.read_bytes(), before)

    def test_changed_account_rejects_bound_observation(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(h, 'PATH', Path(directory)/'history.json'), patch.object(h, 'account_scope', return_value='b'):
            result = h.observe([{'kind':'weekly','remaining_percent':20,'reset':2000}], 1000, expected_scope='a')
            self.assertEqual(result['samples'], [])
            self.assertIn('账号已切换', result['error'])
            self.assertFalse(h.PATH.exists())

    def test_missing_scope_and_invalid(self):
        with patch.object(h,'account_scope',return_value=None):
            self.assertEqual(h.observe([],1000)['samples'],[])
        self.assertEqual(h.clean_windows([{'kind':'weekly','remaining_percent':True,'reset':2}]),[])
