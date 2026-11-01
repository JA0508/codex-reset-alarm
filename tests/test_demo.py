import unittest
from unittest.mock import Mock, patch
import demo

class DemoTests(unittest.TestCase):
    def test_snapshot_is_simulated(self):
        value = demo.snapshot()
        self.assertTrue(value['demo_mode'])
        self.assertTrue(value['running'])
        self.assertEqual(value['credits']['availableCount'], 2)
    def test_wrong_host_rejected(self):
        handler = object.__new__(demo.Handler)
        handler.headers = {'Host': 'evil.example'}
        handler.path = '/api/status'
        handler.reply = Mock()
        handler.do_GET()
        self.assertEqual(handler.reply.call_args.args[0], 403)
    def test_settings_only_boolean(self):
        import io
        handler = object.__new__(demo.Handler)
        handler.path = '/api/settings'
        handler.headers = {'Host': demo.HOST, 'Origin': 'http://' + demo.HOST, 'X-CSRF-Token': demo.TOKEN, 'Content-Length': '17'}
        handler.rfile = io.BytesIO(b'{"enabled":false}')
        handler.reply = Mock()
        original = demo.ENABLED
        try:
            handler.do_POST()
            self.assertFalse(demo.ENABLED)
        finally:
            demo.ENABLED = original
    def test_demo_import_is_independent_of_live_services(self):
        import subprocess
        import sys
        script = "import runpy,sys;runpy.run_path(sys.argv[1],run_name='demo_test');assert not {'alarm','dashboard','preferences','iphone_bridge'} & set(sys.modules)"
        result = subprocess.run([sys.executable, '-I', '-c', script, str(demo.ROOT / 'demo.py')], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
