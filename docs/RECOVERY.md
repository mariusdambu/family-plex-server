# Recovery and rehearsal

For replacement hardware and RAID upgrades, follow [Migration](MIGRATION.md) alongside this guide.

The public repository reconstructs the service architecture, not your personal data, Plex account, passwords or router configuration. To recover these you need a private backup plus your own offline credential and UID/GID records. Regenerate SSH keys on the replacement host.

## Replace the host

1. Disconnect data disks during OS installation. Install OMV/Debian and Docker using INSTALL.md.
2. Reconnect existing data disks. Identify by model/serial/UUID and mount them without formatting.
3. Recreate users and groups with the original numeric IDs where restoring ownership. If IDs differ, map ownership deliberately; never recursively chown all disks blindly.
4. Install this repository. Recover the private config to `/etc/family-plex`, mode 600. Update paths for the target host and regenerate Compose.
5. Stop Plex and AdGuard before restoring appdata. Restore the matching versions/digests first, then upgrade separately.
6. Recreate OMV shares and ACLs following USERS.md. Use the saved OMV config as a reference; do not overwrite a different installation's complete config blindly.
7. Run the acceptance checklist, including restore and unplug/reconnect tests.

## Restore from the reference backup

The mirror layout is `family-plex-backup/family/{Family,Archive}` and `family-plex-backup/server/{appdata,config,source,openmediavault}`. Inspect source and destination before every rsync. Start with a dry run; restore without `--delete` unless you have explicitly decided to remove extra destination files.

```sh
# Replace these example paths locally; both must refer to mounted filesystems.
sudo rsync -aHAXn --numeric-ids /MOUNTED_BACKUP/family-plex-backup/family/Family/ /MOUNTED_APPS/Family/
# Review output, then remove the n from -aHAXn to execute.
```

Restore `server/appdata/` to the apps disk's `docker/appdata/` while both containers are stopped. Restore private config separately; keep it root-only. Start services, check logs and compare a sample restored file by checksum. Never run two Plex servers with the same restored identity simultaneously.

## Source installation compatibility

The original installation used `plexserver-backup/familia/{Familia,Backups}` and `plexserver-backup/server-config/{appdata,docker-compose,dashboard,system}`. These names are not the new reference layout. Map folders explicitly; do not run the new mirror against an old backup until a separate verified copy exists. Its live appdata was copied while applications were running: successful rsync completion does not prove database consistency.

## Recovery test record

Record the test date, host architecture, OS/OMV versions, chosen image digests, source and destination disks, files restored, UID/GID mapping, application startup and playback/DNS results in a private operations log. Source tests alone cannot certify a restore.
