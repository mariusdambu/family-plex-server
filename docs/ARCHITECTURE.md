# Architecture

The Linux host owns the filesystems, users, mounts and SMB exports. OpenMediaVault manages those settings. Docker runs Plex and AdGuard; it does not own the media disks. The dashboard calls a narrow set of fixed operations on the host.

| Role | Contents | Container view | Backup |
| --- | --- | --- | --- |
| OS disk | Debian, OMV, Docker, service definitions | Host only | Reinstall from instructions |
| Apps disk | Family, Archive, Docker appdata | `/config` in Plex | Yes |
| Main media disk | Media library | `/media` | No |
| Removable movie disk | `Media/Movies` | `/media-usb/Movies` | No |
| Separate backup disk | Private mirror | Not exposed | Destination |

The backup device may be a microSD reader, but flash media can fail. Keep an additional independent, preferably offline/off-site, backup of irreplaceable files. One mirror is not a disaster recovery strategy by itself.

SMB shares such as `Media`, `Family`, `Archive`, `Drivers` and `Movies_USB` belong to the same server. Docker paths are not network shares. The reference uses `/media-usb` outside `/media` to avoid the confusing empty `Media/USB` directory created by nested Docker binds in the source installation.

Mounts use filesystem UUIDs, never `/dev/sdc` or another discovery-order name. OMV must own persistent filesystem entries. Never hand-edit the OMV-generated Samba config. Configure `nofail` for removable storage so its absence does not prevent host boot. Hotplug alone does not guarantee mounting; use the explicit mount action.

Docker can keep references to an old mount. Eject stops Plex, closes only the USB SMB share, flushes writes and requests a normal unmount, then starts Plex again. Connect stops Plex, mounts by its configured fstab entry, verifies the filesystem UUID and restarts Plex. Busy unmounts fail safely; forced/lazy unmount is deliberately absent. Existing Finder SMB mounts may need eject/reopen after server-side disconnection.

The generated Plex bind uses `create_host_path: false`. On first boot, create the required empty `Media` directory under the unmounted USB mountpoint as documented. With USB absent, Plex can start on the main disk; reconnect the USB through the operation so Plex sees its new mount. Never write into that underlying empty directory.

## Boundaries

`maintenance.py` adds a fixed action allowlist, persistent SQLite history, Plex session checks, individual container updates, explicit restart confirmation and boot-ID recovery. All CLI operations share the same advisory flock. No language model or arbitrary shell execution is involved. The dashboard remains a root administrative interface requiring its existing authentication and SSH tunnel. History confirms defined checks, not full NAS health.

- Dashboard binds to localhost and requires a private token plus CSRF protection. Use an SSH tunnel. It runs as root because mounts and Docker require privilege. Do not publish it directly to the Internet.
- OMV/SMB/AdGuard stay on a trusted LAN or VPN. Firewall rules must reflect your network. Never expose SMB or Docker's socket publicly.
- Family account roles are filesystem permissions, not browser or content filtering. Child Plex profiles and parental controls are separate Plex settings.
- AdGuard being the household DNS creates an availability dependency. Keep a documented router/DNS fallback for maintenance.
- Pinned container digests and a saved private configuration make redeployment repeatable. OS/package repositories still evolve; record versions at deployment.
