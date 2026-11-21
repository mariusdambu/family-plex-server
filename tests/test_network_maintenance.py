import io
import json
import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch
import network_maintenance as n


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.policy = pathlib.Path(self.tmp.name) / 'policy.json'
        self.policy.write_text(json.dumps({'networks': ['192.0.2.0/24', '100.64.0.0/10'],
                                          'hosts': ['192.0.2.10:8090']}))
        self.patch = patch.object(n, 'POLICY', self.policy)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def handler(self, peer='192.0.2.20', host='192.0.2.10:8090'):
        return Mock(client_address=(peer, 1234), headers={'Host': host})

    def test_networks_without_omv_session(self):
        self.assertTrue(n.trusted(self.handler()))
        self.assertTrue(n.trusted(self.handler(peer='100.80.1.2')))

    def test_public_peer_and_untrusted_host_denied(self):
        self.assertFalse(n.trusted(self.handler(peer='203.0.113.2')))
        self.assertFalse(n.trusted(self.handler(host='attacker.invalid:8090')))

    def test_forwarded_address_is_not_trusted(self):
        h = self.handler(peer='203.0.113.2')
        h.headers['X-Forwarded-For'] = '192.0.2.20'
        self.assertFalse(n.trusted(h))

    def test_missing_policy_fails_closed(self):
        self.policy.unlink()
        self.assertFalse(n.trusted(self.handler()))

    def test_cross_origin_cannot_dispatch(self):
        h = self.handler()
        h.headers['Origin'] = 'http://attacker.invalid'
        with patch.object(n, 'respond') as respond, patch.object(n.subprocess, 'run') as run:
            n.submit(h)
        self.assertEqual(respond.call_args.args[1], 400)
        run.assert_not_called()

    def test_missing_csrf_cannot_dispatch(self):
        h = self.handler()
        body = b'action=reboot_host&confirm=reboot_host'
        h.headers.update({'Origin': 'http://192.0.2.10:8090', 'Content-Length': str(len(body))})
        h.rfile = io.BytesIO(body)
        with patch.object(n, 'respond') as respond, patch.object(n.subprocess, 'run') as run:
            n.submit(h)
        self.assertEqual(respond.call_args.args[1], 400)
        run.assert_not_called()

    def test_page_polls_without_reload(self):
        markup = n.page({'Host': '192.0.2.10:8090'})
        self.assertIn('setInterval(refresh,5000)', markup)
        self.assertNotIn('location.reload', markup)
        self.assertEqual(markup.count('<form data-action='), 4)
        self.assertIn('Local network · 192.0.2.10', markup)
        self.assertIn('Tailscale · nas.example.ts.net', n.page({'Host': 'nas.example.ts.net:8443'}))

    def test_backup_failure_is_warning_not_check_override(self):
        with patch.object(n.m, 'backup_ready', side_effect=RuntimeError('No backup')), \
             patch.object(n, 'load', return_value={}), patch.object(n.m, 'checks', return_value={'update_plex': (True, 'Ready')}), \
             patch.object(n.m, 'history', return_value=[]):
            result = n.status()
        self.assertEqual(result['backup_warning'], 'No backup')
        self.assertTrue(result['checks']['update_plex'][0])
