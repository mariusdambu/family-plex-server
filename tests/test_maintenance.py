import json
import os
import pathlib
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import maintenance as m


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.patches = [patch.object(m, 'STATE', self.root / 'state'),
                        patch.object(m, 'LOCK', self.root / 'lock'),
                        patch.object(m, 'boot_id', return_value='boot-current')]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def insert(self, state='running', boot='boot-current', start='123', age=300):
        with m.db() as connection:
            return connection.execute('''INSERT INTO operations
                (started,action,state,detail,boot,pid,process_start) VALUES(?,?,?,?,?,?,?)''',
                (time.time() - age, 'reboot_host' if state == 'reboot_requested' else 'update_plex',
                 state, 'test', boot, 12345, start)).lastrowid

    def test_dead_executor_is_interrupted(self):
        self.insert()
        with patch.object(m, 'process_identity', return_value=''):
            m.recover()
        self.assertEqual(m.history()[0]['state'], 'interrupted')

    def test_live_executor_survives_dashboard_restart(self):
        self.insert()
        with patch.object(m, 'process_identity', return_value='123'):
            m.recover()
        self.assertEqual(m.history()[0]['state'], 'running')

    def test_reused_pid_is_not_live_executor(self):
        self.insert()
        with patch.object(m, 'process_identity', return_value='999'):
            m.recover()
        self.assertEqual(m.history()[0]['state'], 'interrupted')

    def test_new_boot_confirms_requested_restart(self):
        self.insert(state='reboot_requested', boot='boot-old')
        m.recover()
        self.assertEqual(m.history()[0]['state'], 'success')

    def test_same_boot_does_not_confirm_restart(self):
        self.insert(state='reboot_requested', age=1)
        with patch.object(m, 'process_identity', return_value=''):
            m.recover()
        self.assertEqual(m.history()[0]['state'], 'reboot_requested')

    def test_restart_never_happened_is_interrupted(self):
        self.insert(state='reboot_requested')
        with patch.object(m, 'process_identity', return_value=''):
            m.recover()
        self.assertEqual(m.history()[0]['state'], 'interrupted')

    def test_recovery_respects_global_lock(self):
        import fcntl
        self.insert()
        with open(m.LOCK, 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            m.recover()
        self.assertEqual(m.history()[0]['state'], 'running')

    def test_unknown_action_rejected(self):
        with self.assertRaises(ValueError):
            m.execute('anything_from_browser', -1)

    def test_reboot_command_failure_is_not_requested_or_successful(self):
        with patch.object(m, 'load', return_value={}), patch.object(m, 'process_identity', return_value='123'), \
             patch.object(m, 'preflight', return_value=(True, '')), patch.object(m, 'command', side_effect=RuntimeError):
            self.assertFalse(m.execute('reboot_host', 1))
        self.assertEqual(m.history()[0]['state'], 'needs_review')

    def test_secure_log_and_database_permissions(self):
        self.insert()
        self.assertEqual((m.STATE / 'maintenance.sqlite3').stat().st_mode & 0o777, 0o600)

    def test_private_token_rejects_group_read_access(self):
        info = Mock(st_mode=0o100640, st_uid=0)
        with patch.object(m, 'TOKEN') as token:
            token.lstat.return_value = info
            with self.assertRaises(RuntimeError):
                m.token()
            token.read_text.assert_not_called()

    def test_command_timeout_does_not_kill_package_transaction(self):
        import subprocess
        with patch.object(m.subprocess, 'Popen') as popen:
            process = popen.return_value
            process.wait.side_effect = subprocess.TimeoutExpired('test', 1)
            with self.assertRaises(RuntimeError):
                m.command(['fixed-command'], Mock(), 42, timeout=1)
            self.assertEqual(popen.call_args.kwargs['pass_fds'], (42,))
            process.kill.assert_not_called()
            process.terminate.assert_not_called()

    def test_omv_updates_need_explicit_opt_in(self):
        with patch.object(m.os.path, 'ismount', return_value=True), patch.object(m, 'backup_ready'), \
             patch.object(pathlib.Path, 'is_file', return_value=True):
            allowed, reason = m.preflight('update_OMV', locked=True, config={'apps_root': '/apps'}, sessions=0)
        self.assertFalse(allowed)
        self.assertIn('allow_omv_updates', reason)

    def test_omv_uses_restricted_official_command_and_checks_services(self):
        with patch.object(m, 'load', return_value={}), patch.object(m, 'process_identity', return_value='123'), \
             patch.object(m, 'preflight', return_value=(True, '')), patch.object(m, 'command') as command, \
             patch.object(m, 'wait_ready') as ready:
            self.assertTrue(m.execute('update_OMV', 1))
        self.assertEqual(command.call_args.args[0], ['/usr/sbin/omv-upgrade'])
        flags = command.call_args.kwargs['env']['OMV_UPGRADE_APT_ARGS']
        self.assertIn('--no-remove', flags)
        self.assertNotIn('--allow-unauthenticated', flags)
        self.assertEqual(ready.call_count, 2)

    def test_unavailable_plex_fails_closed(self):
        with patch.object(m, 'load', return_value={}), patch.object(m, 'plex_sessions', side_effect=OSError):
            self.assertFalse(any(value[0] for value in m.checks().values()))

    def test_active_session_blocks_execution(self):
        allowed, _ = m.preflight('update_plex', locked=True, config={'apps_root': '/irrelevant'}, sessions=1)
        self.assertFalse(allowed)

    def test_missing_backup_blocks_updates(self):
        with patch.object(m.os.path, 'ismount', return_value=True), patch.object(m, 'backup_ready', side_effect=OSError):
            self.assertFalse(m.preflight('update_adguard', locked=True, config={'apps_root': '/apps'}, sessions=0)[0])

    def test_sessions_starting_during_pull_prevent_recreation(self):
        with patch.object(m, 'load', return_value={}), patch.object(m, 'process_identity', return_value='123'), \
             patch.object(m, 'preflight', side_effect=[(True, ''), (False, 'Playback started')]), \
             patch.object(m, 'command') as command, patch.object(m, 'wait_ready') as ready:
            self.assertFalse(m.execute('update_plex', 1))
        self.assertEqual(command.call_count, 2)
        ready.assert_not_called()
        self.assertEqual(m.history()[0]['state'], 'blocked')

    def test_readiness_failure_never_marks_success(self):
        with patch.object(m, 'load', return_value={}), patch.object(m, 'process_identity', return_value='123'), \
             patch.object(m, 'preflight', return_value=(True, '')), patch.object(m, 'command'), \
             patch.object(m, 'wait_ready', side_effect=RuntimeError):
            self.assertFalse(m.execute('update_adguard', 1))
        self.assertEqual(m.history()[0]['state'], 'needs_review')

    def test_restart_is_persisted_before_command(self):
        def inspect(*args, **kwargs):
            self.assertEqual(m.history()[0]['state'], 'reboot_requested')
        with patch.object(m, 'load', return_value={}), patch.object(m, 'process_identity', return_value='123'), \
             patch.object(m, 'preflight', return_value=(True, '')), patch.object(m, 'command', side_effect=inspect):
            self.assertTrue(m.execute('reboot_host', 1))
        self.assertEqual(m.history()[0]['state'], 'reboot_requested')

    def test_adguard_readiness_requires_dns(self):
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(status=200))
        response.__exit__ = Mock(return_value=False)
        with patch.object(m.subprocess, 'check_output', return_value=json.dumps([{'State': {'Running': True}}])), \
             patch.object(m, 'urlopen', return_value=response), patch.object(m, 'dns_ready', side_effect=RuntimeError) as dns:
            with self.assertRaises(RuntimeError):
                m.readiness('update_adguard', {'server_address': '192.0.2.10'})
            dns.assert_called_once()

    def test_dns_packets(self):
        question = b'\x07example\x03org\0\0\1\0\1'
        answer = b'\xc0\x0c' + struct.pack('!HHIH', 1, 1, 60, 4) + bytes([93, 184, 216, 34])
        packet = struct.pack('!6H', 42, 0x8180, 1, 1, 0, 0) + question + answer
        self.assertTrue(m.dns_answer_valid(packet, 42, question))
        self.assertFalse(m.dns_answer_valid(packet, 43, question))
        self.assertFalse(m.dns_answer_valid(packet[:15], 42, question))
        self.assertFalse(m.dns_answer_valid(packet[:-4] + b'\0\0\0\0', 42, question))
        nxdomain = struct.pack('!6H', 42, 0x8183, 1, 0, 0, 0) + question
        self.assertFalse(m.dns_answer_valid(nxdomain, 42, question))


if __name__ == '__main__':
    unittest.main()
