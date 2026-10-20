import io
import pathlib
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import legacy_maintenance as legacy


class LegacyTests(unittest.TestCase):
    def test_no_cookie_never_calls_omv(self):
        with patch.object(legacy, 'urlopen') as call:
            self.assertFalse(legacy.admin_session({}))
            call.assert_not_called()

    def test_only_admin_rpc_success_authorizes(self):
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(read=Mock(return_value=b'{"response":"read-only quote","error":null}')))
        response.__exit__ = Mock(return_value=False)
        with patch.object(legacy, 'urlopen', return_value=response) as call:
            self.assertTrue(legacy.admin_session({'Cookie': 'PHPSESSID=' + 'a' * 32, 'User-Agent': 'Test browser'}))
            request = call.call_args.args[0]
            self.assertEqual(request.full_url, 'http://127.0.0.1/rpc.php')
            self.assertIn(b'"method": "noop"', request.data)
            self.assertNotIn(b'password', request.data)

    def test_unauthenticated_panel_has_disabled_actions(self):
        with patch.object(legacy, 'admin_session', return_value=False):
            markup = legacy.page({})
        self.assertEqual(markup.count('disabled>'), 4)

    def test_no_auth_cannot_submit(self):
        handler = Mock(headers={})
        with patch.object(legacy, 'respond') as respond, patch.object(legacy.subprocess, 'run') as run:
            legacy.submit(handler)
        self.assertEqual(respond.call_args.args[1], 403)
        run.assert_not_called()

    def test_cross_origin_cannot_submit(self):
        handler = Mock(headers={'Origin': 'http://other.invalid', 'Host': 'nas.invalid:8090'})
        with patch.object(legacy, 'admin_session', return_value=True), \
             patch.object(legacy, 'respond') as respond, patch.object(legacy.subprocess, 'run') as run:
            legacy.submit(handler)
        self.assertEqual(respond.call_args.args[1], 400)
        run.assert_not_called()

    def test_legacy_compose_path_is_used(self):
        import maintenance as m
        config = {'maintenance': {'compose_files': {'plex': '/srv/apps/docker/compose/plex/docker-compose.yml'}}}
        self.assertEqual(str(m.compose_file('update_plex', config)), '/srv/apps/docker/compose/plex/docker-compose.yml')


if __name__ == '__main__':
    unittest.main()
