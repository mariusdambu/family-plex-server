import io
import pathlib
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import dashboard


class DashboardTests(unittest.TestCase):
    def handler(self, body):
        handler = object.__new__(dashboard.Handler)
        handler.headers = {'Content-Length': str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.authorized = Mock(return_value=True)
        handler.send_error = Mock()
        return handler

    def test_maintenance_requires_matching_confirmation(self):
        body = f'csrf={dashboard.CSRF}&action=reboot_host&confirm=update_plex'.encode()
        handler = self.handler(body)
        with patch.object(dashboard.maintenance, 'preflight') as preflight:
            handler.do_POST()
        handler.send_error.assert_called_once_with(400)
        preflight.assert_not_called()

    def test_csrf_rejected_before_operations(self):
        handler = self.handler(b'csrf=invalid&action=reboot_host&confirm=reboot_host')
        with patch.object(dashboard.maintenance, 'preflight') as preflight:
            handler.do_POST()
        handler.send_error.assert_called_once_with(400)
        preflight.assert_not_called()

    def test_unauthenticated_request_cannot_execute(self):
        handler = self.handler(b'action=reboot_host')
        handler.authorized.return_value = False
        with patch.object(dashboard.maintenance, 'preflight') as preflight:
            handler.do_POST()
        preflight.assert_not_called()

    def test_backend_refuses_even_with_valid_form(self):
        handler = self.handler(f'csrf={dashboard.CSRF}&action=update_plex&confirm=update_plex'.encode())
        with patch.object(dashboard.maintenance, 'recover'), \
             patch.object(dashboard.maintenance, 'preflight', return_value=(False, 'Playback active')), \
             patch.object(dashboard.subprocess, 'run') as run:
            handler.do_POST()
        handler.send_error.assert_called_once_with(409, 'Playback active')
        run.assert_not_called()

    def test_disabled_buttons_and_history_escape_html(self):
        checks = {key: (False, '<blocked>') for key in dashboard.maintenance.ACTIONS}
        with patch.object(dashboard.maintenance, 'checks', return_value=checks), \
             patch.object(dashboard.maintenance, 'history', return_value=[
                 {'started': 0, 'action': 'update_plex', 'state': 'failed', 'detail': '<script>alert(1)</script>'}]):
            markup = dashboard.maintenance_html()
        self.assertEqual(markup.count('disabled>'), 4)
        self.assertNotIn('<script>', markup)
        self.assertIn('&lt;script&gt;', markup)

    def test_complete_page_keeps_existing_controls_and_adds_maintenance(self):
        handler = object.__new__(dashboard.Handler)
        handler.authorized = Mock(return_value=True)
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = io.BytesIO()
        with patch.object(dashboard, 'load', return_value={'usb_root': '/not-mounted'}), \
             patch.object(dashboard, 'maintenance_html', return_value='<h2>Maintenance</h2>'):
            handler.do_GET()
        page = handler.wfile.getvalue().decode()
        self.assertIn('Connect movie USB', page)
        self.assertIn('Run backup', page)
        self.assertIn('<h2>Maintenance</h2>', page)
        handler.send_response.assert_called_once_with(200)


if __name__ == '__main__':
    unittest.main()
