import pathlib
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import ops


class OperationTests(unittest.TestCase):
    def test_stopped_restores_running_container_on_failure(self):
        with patch.object(ops, 'containers_running', return_value=['plex']), patch.object(ops, 'run') as run:
            with self.assertRaises(RuntimeError):
                with ops.stopped(['plex', 'adguardhome']):
                    raise RuntimeError('Unmount refused')
            self.assertEqual(run.call_args_list[0].args[0], ['docker', 'stop', '-t', '30', 'plex'])
            self.assertEqual(run.call_args_list[-1].args[0], ['docker', 'start', 'plex'])

    def test_wrong_backup_uuid_rejected(self):
        with patch.object(ops.os.path, 'ismount', return_value=True), patch.object(ops, 'run', return_value='wrong-uuid\n'):
            with self.assertRaises(RuntimeError):
                ops.mounted('/srv/backup', 'expected-uuid')

    def test_missing_backup_mount_rejected(self):
        with patch.object(ops.os.path, 'ismount', return_value=False):
            with self.assertRaises(RuntimeError):
                ops.mounted('/srv/backup')


if __name__ == '__main__':
    unittest.main()
