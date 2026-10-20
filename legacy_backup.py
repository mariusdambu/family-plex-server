#!/usr/bin/env python3
"""Quiesce applications around the existing production backup script.

Installed only for an explicitly reviewed legacy migration, not on new installs.
"""
import datetime as dt
import fcntl
import json
import os
import pathlib
import subprocess
import sys
import time
import maintenance as m
from configure import load
from ops import mounted, stopped


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Root required')
    config = load()
    with open(m.LOCK, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if m.plex_sessions():
            raise RuntimeError('Backup blocked while Plex sessions are active')
        root = config['backup_root']
        if not os.path.ismount(root):
            subprocess.run(['mount', '-t', 'ext4', '/dev/disk/by-uuid/' + config['backup_uuid'], root], check=True)
        mounted(root, config['backup_uuid'])
        mounted(config['apps_root'])
        destination = pathlib.Path(root) / 'plexserver-backup'
        destination.mkdir(exist_ok=True)
        marker = destination / 'last-success.json'
        marker.unlink(missing_ok=True)
        started = time.time()
        with stopped(['plex', 'adguardhome']):
            subprocess.run(['/usr/local/sbin/plexserver-backup.sh'], check=True, timeout=18000, pass_fds=(lock.fileno(),))
            for source, relative in [('/etc/family-plex', 'private-config'),
                                     ('/opt/family-plex', 'source'),
                                     ('/etc/systemd/system/plexserver-backup.service.d', 'backup-service-dropin')]:
                target = destination / 'server-config/maintenance' / relative
                target.mkdir(parents=True, exist_ok=True)
                subprocess.run(['rsync', '-aHAX', '--numeric-ids', '--delete', source + '/', str(target) + '/'],
                               check=True, timeout=300, pass_fds=(lock.fileno(),))
        status = pathlib.Path('/var/lib/plexserver-backup/status.env').read_text()
        if 'state=ok\n' not in status or pathlib.Path('/var/lib/plexserver-backup/status.env').stat().st_mtime < started:
            raise RuntimeError('Legacy backup did not report a new successful copy')
        temporary = destination / '.last-success.tmp'
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump({'completed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                       'kind': 'mirror', 'media_included': False, 'appdata_copy': 'offline'}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(marker)
        subprocess.run(['sync', '-f', str(destination)], check=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        status_dir = pathlib.Path('/var/lib/plexserver-backup')
        status_dir.mkdir(exist_ok=True)
        (status_dir / 'status.env').write_text('state=error\nlabel=Revisar\ndetail=Backup consistente no completado; consulta el registro del servicio.\n')
        sys.exit(str(error))
