import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import dashboard_certificate as certificate


class OmvCertificateTests(unittest.TestCase):
    def test_unenrolled_host_does_not_call_omv(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(certificate, 'TLS', pathlib.Path(directory)), patch.object(certificate.subprocess, 'run') as run:
            certificate.sync_omv_certificate()
            run.assert_not_called()

    def test_certificate_sync_passes_key_only_on_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            identifier = '00000000-0000-4000-8000-000000000099'
            (root / 'omv-certificate-uuid').write_text(identifier)
            (root / 'dashboard.crt').write_text('new certificate')
            (root / 'dashboard.key').write_text('private key')
            records = [dict(uuid=identifier, certificate='old', privatekey='old', comment='managed')]
            with patch.object(certificate, 'TLS', root), patch.object(certificate.subprocess, 'check_output', return_value=json.dumps(records).encode()), patch.object(certificate.subprocess, 'run') as run:
                certificate.sync_omv_certificate()
                rpc, deploy = run.call_args_list
                self.assertNotIn('private key', str(rpc.args))
                self.assertEqual(json.loads(rpc.kwargs['input'])['privatekey'], 'private key')
                self.assertEqual(deploy.args[0], ['omv-salt', 'deploy', 'run', 'certificates', 'nginx'])
                records[0].update(certificate='new certificate', privatekey='private key')
            with patch.object(certificate, 'TLS', root), patch.object(certificate.subprocess, 'check_output', return_value=json.dumps(records).encode()), patch.object(certificate.subprocess, 'run') as run:
                certificate.sync_omv_certificate()
                run.assert_not_called()
