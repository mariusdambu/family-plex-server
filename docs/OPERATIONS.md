# Daily operations

## Removable movie disk

Movie USB is additional storage; the main media disk remains attached. Connect the cable and use **Connect movie USB** in the dashboard. Wait for success; Plex briefly restarts. Open `Movies_USB` under the same SMB server as your other shares. Add `/media-usb/Movies` to a Plex library on a new deployment.

Before removal, finish transfers where possible and use **Eject movie USB**. The server stops Plex, disconnects everyone from this USB SMB share, flushes writes, performs a normal unmount and resumes Plex on the primary disk. Wait for explicit success. A busy error means **do not unplug**. Never use `umount -l`, `umount -f` or kill arbitrary file users to bypass the error.

Server-side disconnect can leave a stale Finder mount. Eject that share on the Mac and reopen it from Network > your server. Do not alternate hostname, IP and mDNS addresses; use one server identity consistently. Refresh alone is not guaranteed to repair a stale mount. Ejecting a Mac SMB share alone does not unmount the physical disk on the server.

Plex scanning and trash behavior are left to the owner's preferences. A missing USB can make titles unavailable; automatic trash emptying can remove entries. Scan the library after adding/deleting movies; reconnect does not itself guarantee a complete library scan.

## Backup

Mount the configured backup device, then run `sudo python3 /opt/family-plex/ops.py backup` or the dashboard button. This reference stops Plex **and AdGuard** while copying app databases, so household DNS is temporarily unavailable. Schedule the interruption and keep an alternative DNS procedure. A missing device fails visibly instead of returning a false success.

The backup contains family files, archive, appdata, private configuration, source and OMV settings. It does **not** include either media library, the OS, installed Docker images or system password databases. Keep separate offline recovery credentials and user/ID records. Backup contents are private, even though the source is public.

This is a single mirror with `--delete`. It is not ransomware protection or a versioned archive. Keep another independent copy of irreplaceable documents. Check `last-success.json` and `journalctl -u family-plex-backup.service` and periodically test restore. A timer being active does not prove the last backup succeeded.

## Updates

1. Complete a backup and record current image digests.
2. Choose new tags/digests from upstream, edit the private config and regenerate Compose.
3. Run `sudo python3 /opt/family-plex/ops.py update`.
4. Check `docker ps`, application versions, DNS and playback. Read logs if startup fails.

Pulling a pinned digest alone will not update it. Recreating containers preserves bind-mounted appdata but can migrate its schema. For rollback use the old image **and a matching pre-upgrade appdata backup** where required.

## Troubleshooting

| Symptom | First check |
| --- | --- |
| Movies missing | `findmnt`, actual library path, Plex user permissions and scan |
| USB busy | Active SMB access / local handles via `fuser -vm MOUNTPOINT` |
| Finder original item missing | Eject stale client SMB connection and reopen by the same hostname |
| DNS down | AdGuard container, port 53, router DNS fallback |
| Backup fails | Correct UUID mounted, free capacity, missing source, service journal |
| Dashboard unavailable | SSH tunnel, token, `systemctl status family-plex-dashboard` |

Useful commands: `docker logs --tail 50 plex`, `docker logs --tail 50 adguardhome`, `lsblk -f`, `df -h`, `systemctl list-timers family-plex-backup.timer`. Logs can contain personal details: redact before sharing.
