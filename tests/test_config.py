import copy
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from configure import validate, compose


def sample():
    c = json.loads((pathlib.Path(__file__).resolve().parents[1] / 'config.example.json').read_text())
    for role, number in [('APPS', 1), ('MEDIA', 2), ('USB', 3), ('BACKUP', 4)]:
        token = f'00000000-0000-4000-8000-{number:012d}'
        c = json.loads(json.dumps(c).replace('REPLACE_' + role + '_UUID', token))
    c['dashboard_token'] = 'fictional-test-token-with-at-least-32-characters'
    return c


class ConfigTests(unittest.TestCase):
    def test_omv_opt_in_cannot_be_a_truthy_string(self):
        c = sample()
        c['maintenance'] = {'allow_omv_updates': 'false'}
        with self.assertRaises(ValueError):
            validate(c)

    def test_apps_and_media_can_share_raid_pool(self):
        c = sample()
        c['media_root'] = c['apps_root']
        validate(c)
        volumes = compose(c)['services']['plex']['volumes']
        self.assertEqual(volumes[1]['source'], c['apps_root'] + '/Media')

    def test_placeholders_rejected(self):
        c = sample()
        c['usb_uuid'] = 'REPLACE_USB_UUID'
        with self.assertRaises(ValueError):
            validate(c)

    def test_duplicate_roots_rejected(self):
        c = sample()
        c['backup_root'] = c['apps_root']
        with self.assertRaises(ValueError):
            validate(c)

    def test_dangerous_root_rejected(self):
        c = sample()
        c['backup_root'] = '/'
        with self.assertRaises(ValueError):
            validate(c)

    def test_no_root_plex(self):
        c = sample()
        c['plex_uid'] = 0
        with self.assertRaises(ValueError):
            validate(c)

    def test_non_nested_binds(self):
        services = compose(validate(sample()))['services']
        volumes = services['plex']['volumes']
        self.assertEqual([v['target'] for v in volumes], ['/config', '/media', '/media-usb'])
        self.assertTrue(all(v['bind']['create_host_path'] is False for v in volumes))

    def test_adguard_first_run_port(self):
        ports = compose(sample())['services']['adguard']['ports']
        self.assertIn('192.0.2.10:3000:3000/tcp', ports)


if __name__ == '__main__':
    unittest.main()
