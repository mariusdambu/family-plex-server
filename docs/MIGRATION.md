# Move to another PC or a RAID-based server

Portability is a primary project goal. Reinstall the operating system on the replacement host; restore or move the data, then regenerate services from private configuration. Do not depend on booting a cloned OS disk on different hardware.

## What can change

CPU, motherboard, RAM, network adapter, OS disk, data disk count and filesystem UUIDs may all change. The reference targets Linux hosts supported by Debian/OMV, Docker and the selected images. Check image architecture support before choosing ARM hardware or moving between CPU architectures. GPU transcoding and hardware-specific devices require separate Plex configuration; this template does not promise automatic GPU migration.

The existing applications use ordinary bind-mounted directories. Their destination paths are configuration values, not embedded machine identities. Recreate the same internal container paths (`/config`, `/media`, `/media-usb`) so Plex library definitions remain meaningful. The source installation used `/media/USB` instead of `/media-usb`; either keep that original bind destination on migration or deliberately edit and rescan its USB library.

## Prepare before hardware fails

Keep these **outside the server**, privately and with a recent verification date:

1. A consistent appdata backup and family files, plus separate media backups if the movies matter.
2. Private config, immutable image digests, CPU architecture, UID/GID list, shares and ACL policy.
3. Disk role/UUID map, router reservation/DNS settings and credentials needed for Plex/OMV/VPN.
4. A checkout of this repository and an offline copy of essential dependencies if Internet access might be unavailable.

The reference mirror excludes movie files. If the old media disks fail with no other copy, the repository cannot recover those movies. A flash backup device is one failure domain, not the only copy of irreplaceable files. The production installation audit also flags that its current appdata backup is live rather than quiesced; fix that separately before treating it as a guaranteed recovery source.

## Scenario A: old PC fails, data disks survive

1. Install Debian/OMV and Docker on the new OS disk with the data disks disconnected.
2. Attach surviving data disks. Identify them by UUID/model/serial; import/mount without formatting.
3. Recreate users/groups with the recorded IDs and verify ACL access.
4. Install source and private config, changing LAN address and paths only where required.
5. Generate Compose, review binds, then start the pinned images. Do not run a second copy of the same Plex identity while the old host is active.
6. Restore appdata only if needed. Validate playback, DNS, family permissions, backup and USB eject/reconnect before changing the router reservation/DNS.

## Scenario B: new PC with more disks and RAID

Use a dedicated OS disk. Build and mount the chosen array/pool using OMV's supported storage tools for the selected release. Choosing RAID level, disks and failure tolerance is a separate hardware decision. RAID is not a backup and does not protect against deletion, ransomware or controller mistakes.

Do not assume an existing single-disk filesystem can be converted safely to your chosen RAID layout in place. Prefer a new array, copy into it, verify and keep the old disks untouched until acceptance. Importing an existing array requires compatible metadata and tools; do not create a new array over disks containing the only copy of data.

Applications and main media may share the same mounted RAID filesystem: set `apps_root` and `media_root` to its mountpoint. Their subdirectories are different (`docker/appdata`, `Family`, `Archive`, and `Media`). Alternatively use separate mounted filesystems for each role. The removable movie disk and backup must remain separate mounted filesystems. Do not put the only backup on another folder of the same RAID pool.

1. With old services available, perform an initial copy of family files and media to the new array, preserving ownership, ACLs and extended attributes (`rsync -aHAX --numeric-ids`).
2. At cutover, stop writers, take a consistent final appdata backup and synchronize remaining changes. Use explicit source/destination paths and check mounts before copying; do not add `--delete` casually.
3. Stop the old services before starting restored Plex/AdGuard on the new host.
4. Update private root paths/UUIDs, generate Compose and recreate OMV shares against the new storage.
5. Validate file counts and checksum important data; validate Plex playback and metadata, DNS and every family role. Check array health and create a new independent backup.
6. Change the router reservation/DNS and reconnect SMB clients using the chosen server name. Keep old disks and the pre-migration backup until the new server has passed a restore rehearsal.

## Rollback

Do not erase the old host/disks during cutover. If acceptance fails, stop the new services, restore the old network identity and restart the old host. Data written on the new host after cutover must be reconciled explicitly before rollback; avoid concurrent writes to two active copies.

## Automation boundary

`configure.py` regenerates application configuration; it does not install the OS, choose/format RAID disks, recreate all OMV users/shares or restore passwords. Those steps remain manual by design to prevent destructive guesses. Once storage and identities are prepared, the same source and private configuration reconstruct the applications and optional services. Test this workflow on spare hardware; no complete hardware migration has yet been certified by this project.
