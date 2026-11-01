# Optional removable USB media (exFAT or ext4)

Use this opt-in setup when Plex must keep running on its other disks while a USB media filesystem is connected and disconnected. It does not format disks or replace the existing legacy ext4 setup automatically. The default dashboard stays authenticated and loopback-bound.

## Select and configure

Identify the physical disk by model, serial, size and filesystem UUID. Verify that existing files are backed up. exFAT works for moving a disk between Linux, macOS and Windows, but has no POSIX ACLs or journaling. Keep application databases and the backup on suitable Linux filesystems. The disk label is descriptive; the filesystem UUID selects the device.

In your private config, set `usb_hotplug` to `true`, `usb_parent` to `/srv/family-plex-usb`, `usb_root` to `/srv/family-plex-usb/disk`, and `usb_filesystem` to `exfat` or `ext4`. Set `usb_uuid` to the actual UUID: exFAT uses a short volume ID, whereas ext4 uses a long UUID. Keep the backup on a separate filesystem. Never substitute a discovery-order name such as `/dev/sdc`.

## Isolate the shared parent before mounting the child

Create the empty parent and install its unit before adding the child filesystem:

```sh
sudo mkdir -p /srv/family-plex-usb/disk
sudo install -m 644 systemd/family-plex-usb-parent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now family-plex-usb-parent.service
```

If using a different `usb_parent`, adapt every path and the escaped child mount-unit name in this template first (`systemd-escape --path --suffix=mount YOUR_CHILD_PATH`). This template deliberately makes the bind recursively private **before** making it shared. Inheriting OMV's root peer group can otherwise create duplicate mounts. Do not bind the whole `/srv` tree into Plex.

## Register the child mount through OMV

Do not hand-edit generated fstab. Inspect the installed `FsTab.set` API schema before using this example; it targets OMV 8. Review existing mount records and pending OMV changes first. If the UUID is already registered, review and edit that record rather than adding another.

After reviewing your actual physical disk and private config, the following root-console example registers a new mount without formatting it:

```python
import json
import pathlib
import subprocess
import sys
sys.path.insert(0, '/opt/family-plex')
from configure import load

c = load()
assert c.get('usb_hotplug') is True
assert __import__('os').path.ismount(c['usb_parent'])
new_id = subprocess.check_output(
    ['omv-env', 'get', 'OMV_CONFIGOBJECT_NEW_UUID'], text=True
).strip().split('=', 1)[1]
options = 'defaults,nofail,x-systemd.device-timeout=3s,x-systemd.requires=family-plex-usb-parent.service'
if c['usb_filesystem'] == 'exfat':
    options += ',uid=0,gid=' + str(c['plex_gid']) + ',umask=0022'
entry = dict(uuid=new_id, fsname='/dev/disk/by-uuid/' + c['usb_uuid'],
             dir=c['usb_root'], type=c['usb_filesystem'], opts=options,
             freq=0, passno=0, usagewarnthreshold=0, comment='Removable Plex media')
subprocess.run(['omv-rpc', '-u', 'admin', 'FsTab', 'set', json.dumps(entry)], check=True)
subprocess.run(['omv-rpc', '-u', 'admin', 'Config', 'applyChanges',
                json.dumps(dict(modules=['fstab'], force=False))], check=True)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
```

Review/apply any dependent monitoring or quota changes in OMV separately; do not clear pending flags by hand or apply unrelated changes blindly. The reference does not run this enrollment example automatically. Verify exactly one mount, the expected UUID and filesystem with `findmnt -M YOUR_CHILD_PATH`.

Create `Movies` and `Kids` only **on the verified mounted disk**, preserving existing content. For ext4 grant the configured Plex UID read/traverse access through the existing ACL policy. exFAT mount options above expose files owned by root with read/traverse permissions for non-root Plex; do not expect per-file Linux ACLs. A read-only Docker bind alone is not a guarantee that future propagated submounts are read-only: verify effective Plex-user write denial as well.

## Add the Docker bind and libraries

Generate and validate Compose, then recreate only Plex while idle, using the same pinned image. The generated hotplug bind maps `usb_parent` to `/media-usb` with `rslave` propagation and `create_host_path: false`. The stable parent exists without the USB, so other libraries remain usable. No library path is added automatically.

Add `/media-usb/disk/Movies` and `/media-usb/disk/Kids` yourself in Plex Web. USB absence can leave catalogue entries unavailable; scanning and trash preferences remain yours. This setup does not create an SMB share or promise that Finder repairs stale SMB sessions automatically.

## Daily controls

- **Connect movie USB** mounts the configured UUID and checks the two directories as the configured Plex UID/GID. Normal reconnect should not restart Plex. If visibility fails it reports that a separate confirmed restart needs operator review; it never silently restarts playback.
- **Eject movie USB** checks USB playback sessions, flushes and requests a normal unmount. Busy handles or an unavailable session check block safe removal.
- **Force USB eject** requires the dashboard confirmation checkbox or an explicit root CLI request. It stops only Plex, attempts a normal unmount and restarts Plex even when unmount fails. It interrupts all Plex playback. Unrelated busy processes still block removal. It never uses `umount -f/-l` or kills arbitrary processes.

The fixed CLI actions are `ops.py usb-mount`, `ops.py usb-eject` and `ops.py usb-force-eject`. All share the maintenance lock and respect a compatible media-sync lock. Wait for an explicit safe-ejection success before unplugging. A timeout or connection failure is not permission to remove the cable.

## Acceptance and recovery

On the target host test: boot with USB absent; mount identity; effective Plex read access and write denial; normal eject/reconnect without changing Plex's start time; USB playback refusal; busy handles; confirmed force eject; and unchanged other media binds. Use a controlled directory handle, not a real movie, to test a busy mount. A full restore and boot test on replacement hardware remain separate acceptance tasks.

Back up the private config and mount records, plus this source and the installed parent unit. Reinstall the parent service before starting hotplug Compose on a replacement host. Use the target disk's real UUID and never restore somebody else's identifiers.
