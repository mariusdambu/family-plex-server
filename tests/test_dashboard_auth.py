import io
import json
import pathlib
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import dashboard_auth as a


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.patches = [patch.object(a, 'ROOT', root), patch.object(a, 'PASSWORD', root / 'password.json'),
                        patch.object(a, 'STATE', root / 'sessions.sqlite3')]
        for p in self.patches:
            p.start()
        a.set_password('test-only-password-123')

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def handler(self, path='/', body='', nonce='a' * 64):
        return Mock(path=path, command='GET', client_address=('192.0.2.10', 1234),
                    headers={'Host': 'nas.example:8443', 'Origin': 'https://nas.example:8443',
                             'Content-Length': str(len(body.encode())), 'Cookie': a.NONCE + '=' + nonce},
                    rfile=io.BytesIO(body.encode()))

    def sign_in(self):
        handler = self.handler('/login', 'nonce=' + 'a' * 64 + '&password=test-only-password-123')
        with patch.object(a, 'send') as send:
            a.login(handler)
        self.assertEqual(send.call_args.args[1], 303)
        value = send.call_args.kwargs['cookie'].split(';')[0]
        handler.headers['Cookie'] = value
        return handler

    def test_password_is_hashed_and_private(self):
        saved = a.PASSWORD.read_text()
        self.assertNotIn('test-only-password', saved)
        self.assertEqual(a.PASSWORD.stat().st_mode & 0o777, 0o600)

    def test_login_and_revocation_on_reset(self):
        handler = self.sign_in()
        self.assertTrue(a.session(handler))
        a.set_password('another-test-password-456')
        self.assertIsNone(a.session(handler))

    def test_expired_session_is_denied(self):
        handler = self.sign_in()
        with a.connection() as db:
            db.execute('UPDATE sessions SET expires=?', (time.time() - 1,))
        self.assertIsNone(a.session(handler))

    def test_all_work_assets_and_operations_require_login(self):
        for path, method, status in [('/work/', 'GET', 303), ('/work/Project/app.js', 'GET', 303),
                                     ('/maintenance/status', 'GET', 401), ('/api/live', 'GET', 401),
                                     ('/maintenance/run', 'POST', 401), ('/api/backup/run', 'POST', 401)]:
            handler = self.handler(path)
            handler.command = method
            with patch.object(a, 'send') as send:
                self.assertFalse(a.gate(handler))
            self.assertEqual(send.call_args.args[1], status)

    def test_http_login_origin_is_rejected(self):
        handler = self.handler('/login', 'nonce=' + 'a' * 64 + '&password=test-only-password-123')
        handler.headers['Origin'] = 'http://nas.example:8443'
        with patch.object(a, 'send') as send:
            a.login(handler)
        self.assertEqual(send.call_args.args[1], 400)

    def test_cookie_security_flags(self):
        value = a.cookie(a.COOKIE, 'sample', a.LIFETIME)
        for flag in ['Secure', 'HttpOnly', 'SameSite=Strict', 'Path=/', 'Max-Age=604800']:
            self.assertIn(flag, value)
        self.assertNotIn('Domain=', value)

    def test_brute_force_is_limited(self):
        with a.connection() as db:
            db.execute('INSERT INTO attempts VALUES(?,?,?)', ('192.0.2.10', 5, time.time() + 900))
        handler = self.handler('/login', 'nonce=' + 'a' * 64 + '&password=invalid')
        with patch.object(a, 'send') as send, patch.object(a, 'derive') as derive:
            a.login(handler)
        self.assertEqual(send.call_args.args[1], 429)
        derive.assert_not_called()

    def test_missing_password_fails_closed(self):
        a.PASSWORD.unlink()
        with patch.object(a, 'send') as send:
            a.login_page(self.handler('/login'))
        self.assertEqual(send.call_args.args[1], 503)

    def test_short_password_is_rejected(self):
        with self.assertRaises(ValueError):
            a.set_password('short')

    def test_login_page_reuses_cookie_across_tabs(self):
        handler = self.handler('/login')
        with patch.object(a, 'send') as send:
            a.login_page(handler)
        self.assertIn('value="' + 'a' * 64 + '"', send.call_args.args[2])
        self.assertIn(a.NONCE + '=' + 'a' * 64, send.call_args.kwargs['cookie'])

    def test_cookie_diagnostic_does_not_expose_nonce(self):
        handler = self.handler('/login/check')
        with patch.object(a, 'send') as send:
            self.assertFalse(a.gate(handler))
        result = json.loads(send.call_args.args[2])
        self.assertEqual(result, {'cookie_ready': True})
        self.assertNotIn('a' * 64, send.call_args.args[2])

    def test_stale_form_is_recovered_without_password_verification(self):
        handler = self.handler('/login', 'nonce=' + 'b' * 64 + '&password=irrelevant')
        with patch.object(a, 'login_page') as page, patch.object(a, 'derive') as derive:
            a.login(handler)
        self.assertIn('expired', page.call_args.args[1])
        derive.assert_not_called()

    def test_missing_cookie_has_actionable_error(self):
        handler = self.handler('/login', 'nonce=' + 'a' * 64 + '&password=irrelevant')
        handler.headers.pop('Cookie')
        with patch.object(a, 'login_page') as page, patch.object(a, 'derive') as derive:
            a.login(handler)
        self.assertIn('cookie', page.call_args.args[1])
        derive.assert_not_called()

    def test_origin_normalizes_case_and_default_port_only(self):
        for origin, host in [('https://NAS.EXAMPLE:8443', 'nas.example:8443'),
                             ('https://nas.example', 'NAS.EXAMPLE:443')]:
            handler = self.handler('/login', 'example=value')
            handler.headers.update({'Origin': origin, 'Host': host})
            self.assertEqual(a.form(handler), {'example': ['value']})

    def test_origin_rejects_distinct_nondefault_ports_and_forwarded_spoofing(self):
        for origin in ['https://nas.example', 'https://nas.example:9443',
                       'https://other.example:8443', 'null', 'https://nas.example:8443/path']:
            handler = self.handler('/login', 'example=value')
            handler.headers['Origin'] = origin
            handler.headers['X-Forwarded-Host'] = 'other.example:8443'
            with self.assertRaises(ValueError):
                a.form(handler)
