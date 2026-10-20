#!/usr/bin/env python3
"""Generate Docker Compose JSON from the private host configuration."""
import ipaddress
import json
import os
import pathlib
import re
import sys

CONFIG = pathlib.Path(os.environ.get('FAMILY_PLEX_CONFIG', '/etc/family-plex/config.json'))
COMPOSE = pathlib.Path('/etc/family-plex/compose.json')


def validate(c):
    for key, value in c.items():
        if 'REPLACE' in str(value):
            raise ValueError('Unconfigured placeholder: ' + key)
    if ipaddress.ip_address(c['server_address']).version != 4:
        raise ValueError('This Compose template requires a LAN IPv4 address')
    roots = [c[k] for k in ('apps_root', 'media_root', 'usb_root', 'backup_root')]
    if len(set(roots)) != 4:
        raise ValueError('Use four distinct filesystem roots')
    for root in roots:
        p = pathlib.Path(root)
        if not p.is_absolute() or len(p.parts) < 3 or '..' in p.parts:
            raise ValueError('Use an explicit absolute disk mount path: ' + root)
        for other in roots:
            if root != other and p in pathlib.Path(other).parents:
                raise ValueError('Disk roots must not be nested')
    for key in ('usb_uuid', 'backup_uuid'):
        if not re.fullmatch(r'[0-9a-fA-F-]{36}', c[key]):
            raise ValueError('Expected an ext4 UUID: ' + key)
    if len(c['dashboard_token']) < 32:
        raise ValueError('Dashboard token must have at least 32 characters')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', c['usb_share']):
        raise ValueError('Invalid SMB share name')
    for key in ('plex_uid', 'plex_gid'):
        if not isinstance(c[key], int) or c[key] <= 0:
            raise ValueError('Set a non-root numeric identity: ' + key)
    return c


def load():
    return validate(json.loads(CONFIG.read_text()))


def compose(c):
    def bind(source, target):
        return {'type': 'bind', 'source': source, 'target': target,
                'bind': {'create_host_path': False}}
    return {'name': 'family-plex', 'services': {
        'plex': {'image': c['plex_image'], 'container_name': 'plex',
                 'network_mode': 'host', 'restart': 'unless-stopped',
                 'environment': {'PUID': str(c['plex_uid']), 'PGID': str(c['plex_gid']),
                                 'TZ': c['timezone'], 'VERSION': 'docker'},
                 'volumes': [bind(c['apps_root'] + '/docker/appdata/plex', '/config'),
                             bind(c['media_root'] + '/Media', '/media'),
                             bind(c['usb_root'] + '/Media', '/media-usb')]},
        'adguard': {'image': c['adguard_image'], 'container_name': 'adguardhome',
                    'restart': 'unless-stopped',
                    'ports': [c['server_address'] + ':53:53/tcp',
                              c['server_address'] + ':53:53/udp',
                              c['server_address'] + ':8080:80/tcp',
                              c['server_address'] + ':3000:3000/tcp'],
                    'volumes': [bind(c['apps_root'] + '/docker/appdata/adguard/work', '/opt/adguardhome/work'),
                                bind(c['apps_root'] + '/docker/appdata/adguard/conf', '/opt/adguardhome/conf')]}
    }}


if __name__ == '__main__':
    try:
        config = load()
        COMPOSE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        COMPOSE.write_text(json.dumps(compose(config), indent=2) + '\n')
        COMPOSE.chmod(0o600)
        print('Generated', COMPOSE, '- review before starting Docker')
    except (ValueError, KeyError, OSError) as error:
        sys.exit(str(error))
