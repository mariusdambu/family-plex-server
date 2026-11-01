"""Configured hotplug controls; no formatting, lazy unmount or arbitrary commands."""
import contextlib
import fcntl
import os
import pathlib
import subprocess
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
import maintenance
from configure import load

CONTAINER_PATH = '/media-usb/disk'
ANCHOR_SERVICE = 'family-plex-usb-parent.service'


def mount_path():
    return load()['usb_root']


def device():
    return '/dev/disk/by-uuid/' + load()['usb_uuid']


def command(args, timeout=40):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or 'Operation did not complete').strip()[:700])
    return result.stdout.strip()


def mounted():
    result = subprocess.run(['findmnt', '-rn', '-M', mount_path(), '-o', 'UUID,FSTYPE'], capture_output=True, text=True, timeout=4)
    return result.returncode == 0 and result.stdout.split() == [load()['usb_uuid'], load().get('usb_filesystem', 'ext4')]


def plex_running():
    return command(['docker', 'inspect', '-f', '{{.State.Running}}', 'plex'], timeout=5) == 'true'


def container_mounted():
    return subprocess.run(['docker', 'exec', 'plex', 'sh', '-c',
        'grep -q " /media-usb/disk .* - ' + load().get('usb_filesystem', 'ext4') + ' " /proc/self/mountinfo'],
        capture_output=True, timeout=5).returncode == 0


def visible():
    if not container_mounted():
        return False
    return subprocess.run(['docker', 'exec', '-u', str(load()['plex_uid']) + ':' + str(load()['plex_gid']), 'plex', 'sh', '-c',
        'test -r /media-usb/disk/Kids && test -x /media-usb/disk/Kids && test -r /media-usb/disk/Movies && test -x /media-usb/disk/Movies'],
        capture_output=True, timeout=5).returncode == 0


def status():
    try:
        connected = os.path.exists(device())
        is_mounted = mounted()
        if not connected:
            label, detail, state = 'Disconnected', 'Connect the USB disk, then choose Connect.', 'parked'
        elif not is_mounted:
            label, detail, state = 'Unmounted', 'Choose Connect to make the disk available to Plex.', 'warning'
        elif visible():
            label, detail, state = 'Connected and mounted', 'Media directories are available to Plex.', 'online'
        else:
            label, detail, state = 'Mounted; Plex unavailable', 'The disk is mounted; check Plex access.', 'warning'
        return dict(connected=connected, mounted=is_mounted, label=label, detail=detail, state=state)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return dict(connected=False, mounted=False, label='Status unavailable', detail='Could not check the USB disk.', state='warning')


def usb_sessions():
    request = Request('http://127.0.0.1:32400/status/sessions',
                      headers={'X-Plex-Token': maintenance.token(), 'Accept': 'application/xml'})
    with urlopen(request, timeout=4) as response:
        root = ET.fromstring(response.read(2_000_000))
    if root.tag != 'MediaContainer' or 'size' not in root.attrib:
        raise RuntimeError('Cannot check Plex playback sessions')
    return any(part.get('file', '').startswith(CONTAINER_PATH + '/') for part in root.findall('.//Part'))


@contextlib.contextmanager
def operation_lock(locked=False):
    with contextlib.ExitStack() as stack:
        for name in (('family-plex-media-sync.lock',) if locked else ('family-plex.lock', 'family-plex-media-sync.lock')):
            handle = stack.enter_context(open('/run/lock/' + name, 'a'))
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Backup, sync or maintenance is in progress; try again later.')
        yield


def operate(action, confirmed=False, locked=False):
    if action not in ('connect', 'eject', 'force-eject', 'connect-restart'):
        raise ValueError('Invalid USB action')
    if action in ('force-eject', 'connect-restart') and not confirmed:
        raise ValueError('Confirm the Plex interruption first')
    if not load().get('usb_hotplug', False):
        raise RuntimeError('Enable usb_hotplug after completing the OMV mount setup')
    with operation_lock(locked):
        if action in ('connect', 'connect-restart'):
            if not os.path.exists(device()):
                raise RuntimeError('Connect the configured USB disk before mounting it')
            command(['systemctl', 'start', ANCHOR_SERVICE])
            if not mounted():
                # A foreign mount must never be accepted as MEDIAUsb.
                if os.path.ismount(mount_path()):
                    raise RuntimeError('Another filesystem occupies the configured mount path')
                command(['mount', mount_path()])
            if not mounted():
                raise RuntimeError('The mounted filesystem UUID could not be verified')
            if action == 'connect-restart':
                command(['docker', 'restart', '--time', '30', 'plex'], timeout=60)
            if not visible():
                return dict(message='USB mounted but not visible to Plex; request a separate confirmed Plex restart.', needs_restart=True, safe_to_remove=False)
            return dict(message='USB connected. Add /media-usb/disk/Movies and /media-usb/disk/Kids in Plex.', safe_to_remove=False)
        if not mounted():
            if os.path.ismount(mount_path()):
                raise RuntimeError('The path contains another filesystem; nothing was unmounted')
            if plex_running() and container_mounted():
                if action != 'force-eject':
                    raise RuntimeError('Plex still holds the mount. Do not unplug; request confirmed force eject.')
                command(['docker', 'stop', '--time', '30', 'plex'], timeout=60)
                command(['docker', 'start', 'plex'], timeout=40)
                if container_mounted():
                    raise RuntimeError('Plex still holds the mount; do not unplug.')
            return dict(message='USB is already unmounted. You may unplug it.', safe_to_remove=True)
        was_running = plex_running()
        if action == 'eject' and was_running and usb_sessions():
            raise RuntimeError('Plex is playing from the USB. Stop that playback or request confirmed force eject.')
        stopped = False
        try:
            if action == 'force-eject' and was_running:
                command(['docker', 'stop', '--time', '30', 'plex'], timeout=60)
                stopped = True
            command(['sync', '-f', mount_path()])
            command(['umount', mount_path()])  # Never lazy/forced: success is required.
            if os.path.ismount(mount_path()):
                raise RuntimeError('The disk is still mounted. Do not unplug.')
            if not stopped and was_running and container_mounted():
                raise RuntimeError('Plex still holds the mount. Do not unplug; request confirmed force eject.')
        finally:
            if stopped:
                command(['docker', 'start', 'plex'], timeout=40)
        return dict(message='USB safely ejected. You may unplug it; Plex retains its other disks.', safe_to_remove=True)

