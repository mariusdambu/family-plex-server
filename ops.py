#!/usr/bin/env python3
"""Explicit administrative operations; no disk formatting or forced unmounts."""
import argparse
import contextlib
import datetime
import fcntl
import json
import os
import pathlib
import subprocess
import sys
from configure import load, COMPOSE
import maintenance


def run(args, timeout=120, capture=False):
    return subprocess.run(args, check=True, text=True, timeout=timeout,
                          stdout=subprocess.PIPE if capture else None).stdout


def mounted(path, uuid=None):
    if not os.path.ismount(path):
        raise RuntimeError('Expected a mounted filesystem: ' + path)
    if uuid:
        actual = run(['findmnt', '-n', '-o', 'UUID', '--target', path], capture=True).strip()
        if actual != uuid:
            raise RuntimeError('Wrong filesystem at ' + path)


def compose(*args):
    run(['docker', 'compose', '-f', str(COMPOSE), *args], timeout=1800)


def containers_running():
    return run(['docker', 'ps', '--format', '{{.Names}}'], capture=True).splitlines()


@contextlib.contextmanager
def stopped(names):
    running = [n for n in names if n in containers_running()]
    try:
        for name in running:
            run(['docker', 'stop', '-t', '30', name])
        yield
    finally:
        for name in running:
            run(['docker', 'start', name])


def usb(c, action):
    root = c['usb_root']
    device = '/dev/disk/by-uuid/' + c['usb_uuid']
    if action == 'mount':
        if not os.path.exists(device):
            raise RuntimeError('Connect the movie USB disk first')
        with stopped(['plex']):
            if not os.path.ismount(root):
                run(['mount', root])
            mounted(root, c['usb_uuid'])
        print('Movie USB ready. Reopen the SMB share if Finder kept an old connection.')
    else:
        if not os.path.ismount(root):
            print('Movie USB is already unmounted')
            return
        mounted(root, c['usb_uuid'])
        with stopped(['plex']):
            run(['smbcontrol', 'smbd', 'close-share', c['usb_share']])
            run(['sync', '-f', root])
            run(['umount', root])
        print('Movie USB safely unmounted. You can unplug it.')


def backup(c):
    mounted(c['apps_root'])
    mounted(c['backup_root'], c['backup_uuid'])
    apps = pathlib.Path(c['apps_root'])
    destination = pathlib.Path(c['backup_root']) / 'family-plex-backup'
    destination.mkdir(mode=0o700, exist_ok=True)
    destination.chmod(0o700)
    sources = [(apps / 'Family', 'family/Family'), (apps / 'Archive', 'family/Archive'),
               (apps / 'docker/appdata', 'server/appdata'),
               (pathlib.Path('/etc/family-plex'), 'server/config'),
               (pathlib.Path('/opt/family-plex'), 'server/source'),
               (pathlib.Path('/etc/openmediavault'), 'server/openmediavault')]
    for source, _ in sources:
        if not source.is_dir():
            raise RuntimeError('Missing source; refusing mirror deletion: ' + str(source))
    (destination / 'last-success.json').unlink(missing_ok=True)
    # Stop database writers for a consistent offline appdata copy.
    with stopped(['plex', 'adguardhome']):
        for source, relative in sources:
            target = destination / relative
            target.mkdir(parents=True, exist_ok=True)
            run(['rsync', '-aHAX', '--numeric-ids', '--delete',
                 str(source) + '/', str(target) + '/'], timeout=7200)
    status = {'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'media_included': False, 'kind': 'mirror'}
    (destination / 'last-success.json').write_text(json.dumps(status, indent=2) + '\n')
    run(['sync', '-f', str(destination)])
    print('Backup completed:', destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'usb-mount', 'usb-eject', *maintenance.ACTIONS])
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('Run as root on the Linux server')
    c = load()
    maintenance.recover()
    with open(maintenance.LOCK, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action in maintenance.ACTIONS:
            if not maintenance.execute(args.action, lock.fileno()):
                raise RuntimeError('Maintenance blocked or failed; inspect dashboard history')
        elif args.action == 'backup':
            backup(c)
        else:
            usb(c, 'mount' if args.action == 'usb-mount' else 'eject')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as error:
        sys.exit(str(error))
