"""Exercise request handlers without network listeners or an installed Codex."""
import io
import json
from email.message import Message
from unittest import TestCase
from unittest.mock import patch
import dashboard
import iphone_bridge


def request(handler_type, method, path, headers=None, payload=b''):
    handler = handler_type.__new__(handler_type)
    handler.path, handler.command = path, method
    handler.request_version = 'HTTP/1.1'
    handler.requestline = method + ' ' + path + ' HTTP/1.1'
    handler.headers = Message()
    for key, value in (headers or {}).items():
        handler.headers[key] = value
    handler.rfile, handler.wfile = io.BytesIO(payload), io.BytesIO()
    handler.client_address = ('127.0.0.1', 1)
    handler.log_request = lambda *args: None
    getattr(handler, 'do_' + method)()
    raw_headers, body = handler.wfile.getvalue().split(b'\r\n\r\n', 1)
    return int(raw_headers.split()[1]), raw_headers.decode(), body


class HTTPTests(TestCase):
    def test_desktop_settings_reject_foreign_origin_without_writing(self):
        with patch('dashboard.preferences.save') as save:
            code, _, _ = request(dashboard.Handler, 'POST', '/api/settings',
                                 {'Host': '127.0.0.1:8765', 'Origin': 'http://evil'})
            self.assertEqual(code, 403)
            save.assert_not_called()

    def test_desktop_settings_reject_string_boolean(self):
        headers = {'Host': '127.0.0.1:8765', 'Origin': 'http://127.0.0.1:8765',
                   'X-CSRF-Token': dashboard.TOKEN, 'Content-Length': '19'}
        with patch('dashboard.preferences.save') as save:
            code, _, _ = request(dashboard.Handler, 'POST', '/api/settings', headers,
                                 b'{"enabled":"false"}')
            self.assertEqual(code, 400)
            save.assert_not_called()

    def test_phone_settings_require_secret_path_and_csrf(self):
        with patch('iphone_bridge.stable_address', return_value='test.local'), patch('iphone_bridge.local_ip', return_value='192.168.1.2'):
            handler = iphone_bridge.handler_for('test-secret')
        with patch('iphone_bridge.preferences.save') as save:
            code, _, _ = request(handler, 'POST', '/wrong/api/settings',
                                 {'Host': 'test.local:8766', 'Origin': 'http://test.local:8766'})
            self.assertEqual(code, 403)
            save.assert_not_called()

    def test_paused_phone_has_no_date_and_never_fetches_quota(self):
        with patch('iphone_bridge.stable_address', return_value='test.local'), patch('iphone_bridge.local_ip', return_value='192.168.1.2'):
            handler = iphone_bridge.handler_for('test-secret')
        with patch('iphone_bridge.preferences.enabled', return_value=False), patch('iphone_bridge.alarm.fetch_limits') as fetch:
            code, _, body = request(handler, 'GET', '/test-secret/alarm.json')
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(body)['enabled'], False)
            self.assertIsNone(json.loads(body)['date'])
            fetch.assert_not_called()

    def test_setup_is_readable_html(self):
        code, headers, body = request(dashboard.Handler, 'GET', '/iphone-setup', {'Host': '127.0.0.1:8765'})
        self.assertEqual(code, 200)
        self.assertIn('text/html', headers)
        self.assertIn(b'<!doctype html>', body.lower())

    def test_phone_switch_roundtrip_and_referrer_privacy(self):
        with patch('iphone_bridge.stable_address', return_value='test.local'), patch('iphone_bridge.local_ip', return_value='192.168.1.2'):
            handler = iphone_bridge.handler_for('test-secret')
        with patch('iphone_bridge.phone_status', return_value={'running': True}):
            code, headers, body = request(handler, 'GET', '/test-secret/api/status')
        self.assertEqual(code, 200)
        self.assertIn('Referrer-Policy: no-referrer', headers)
        token = json.loads(body)['csrf_token']
        payload = b'{"enabled":false}'
        headers = {'Host': 'test.local:8766', 'Origin': 'http://test.local:8766',
                   'X-CSRF-Token': token, 'Content-Length': str(len(payload))}
        with patch('iphone_bridge.preferences.save') as save:
            code, _, body = request(handler, 'POST', '/test-secret/api/settings', headers, payload)
            self.assertEqual(code, 200)
            self.assertFalse(json.loads(body)['notifications_enabled'])
            save.assert_called_once_with(False)

    def test_phone_rejects_wrong_origin_with_correct_token(self):
        with patch('iphone_bridge.stable_address', return_value='test.local'), patch('iphone_bridge.local_ip', return_value='192.168.1.2'):
            handler = iphone_bridge.handler_for('test-secret')
        with patch('iphone_bridge.phone_status', return_value={}):
            _, _, body = request(handler, 'GET', '/test-secret/api/status')
        token = json.loads(body)['csrf_token']
        with patch('iphone_bridge.preferences.save') as save:
            code, _, _ = request(handler, 'POST', '/test-secret/api/settings',
                                 {'Host': 'test.local:8766', 'Origin': 'http://evil', 'X-CSRF-Token': token})
            self.assertEqual(code, 403)
            save.assert_not_called()
