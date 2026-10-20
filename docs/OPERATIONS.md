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
3. Run `sudo python3 /opt/family-plex/ops.py update_plex` or `update_adguard` separately, or use the matching dashboard button.
4. Check `docker ps`, application versions, DNS and playback. Read logs if startup fails.

Pulling a pinned digest alone will not update it. Recreating containers preserves bind-mounted appdata but can migrate its schema. For rollback use the old image **and a matching pre-upgrade appdata backup** where required.

## Checked maintenance (phase 1)

The four closed maintenance actions are `update_plex`, `update_adguard`, `update_OMV` and `reboot_host`. Backup and removable-disk actions remain available separately. The old bulk `update` CLI action is removed so it cannot bypass the new checks. These changes are in the public reference; they do not replace an existing legacy production dashboard automatically.

All maintenance requires a valid Plex session check, including for AdGuard and host restart. Paused sessions also block maintenance. Missing or invalid tokens, unavailable Plex, unexpected responses and mounted-storage failures block execution. A session can still start just after the final check: phase 1 reduces this race but does not establish an exclusive Plex maintenance window.

### One-time private setup

On the target Linux host, create `/etc/family-plex/plex-token` as a root-owned regular file with mode `600`; put only your existing Plex token inside using a local editor. Do not paste the token into chat, a command-line argument, GitHub or the dashboard. The backend reads this file and sends the token in an HTTP header only to local Plex. It is never sent to the browser. No token is included or created automatically by the project.

Container and OMV updates also require the configured backup filesystem, the expected UUID, and a successful reference backup marker from the last 24 hours. The marker is `family-plex-backup/last-success.json`; the original production backup layout does not provide this marker. Do not manufacture one to bypass the requirement. Complete a consistent backup or deliberately migrate the backup workflow first.

Set `maintenance.dns_probe` to a hostname that your AdGuard should resolve to a usable IPv4 address (default `example.org`). After an AdGuard update, both its HTTP interface on port 8080 and a UDP A query sent directly to `server_address:53` must pass. Transaction ID, echoed question, DNS status and a usable answer are checked. This is a basic resolution check, not validation of all DNS policies, upstreams or filtering. A blocked probe or upstream outage prevents success even if the container starts.

OMV updates are disabled until you set `maintenance.allow_omv_updates` to `true` in private config. Review the installed OMV 8 `/usr/sbin/omv-upgrade` script and local update configuration first. The operation invokes that official tool with restrictive arguments (`--yes --no-remove` and preservation of existing conffiles), instead of its permissive default flags. If dependency changes require package removals, it must fail for manual review. It is not a major-release upgrade and does not reboot automatically. HTTP checks for Plex and HTTP/DNS checks for AdGuard run afterwards; other OMV services and package details still need operator verification.

### Confirmation, history and crash recovery

Dashboard maintenance forms require authentication, CSRF validation and an explicit confirmation checkbox whose action must match the submitted action. Direct CLI commands represent the administrator's explicit request. UI checks are repeated by `ops.py` after acquiring the common `family-plex.lock`, and again after image download before container recreation. Only the requested Compose service is recreated.

SQLite history is stored in `/var/lib/family-plex/maintenance.sqlite3`, with individual root-only `operation-N.log` files beside it. The dashboard displays the last 20 records, timestamps in UTC, and generic messages; raw private logs are not served. Files and directories must remain accessible only to root. Logs can include private package/repository information; review and rotate them privately as needed.

On dashboard startup and status refresh, recovery uses boot ID, PID and `/proc` process start time. A record whose executor disappeared is marked `interrupted`; a live executor is preserved. Reconciliation does not run while another operation holds the common lock. Command children inherit that lock so a parent failure does not immediately allow overlapping package operations. A command timeout is `needs_review`: it is not proof that the underlying action stopped, and package transactions are not forcibly killed. Inspect the private log/processes before retrying.

A restart is first recorded as `reboot_requested`. A later different boot ID marks it successful, meaning **a host boot was observed**, not that every application is healthy or that the request caused that boot. If the same boot persists after the executor exits and a two-minute grace period expires, the record is marked interrupted. No restart is triggered during source tests or deployment checks.

Reload the page to see progress. Test blocked states first. Do not click OMV update or restart merely to test that a button exists.

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
