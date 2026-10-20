# Architectural audit — 2026-10-20

Scope: read-only inspection of the operating Linux host, comparison with the local documentation, and creation of this clean reference source. No original host identifiers or personal users are published. This reference has not been deployed over the source server.

## Observed architecture

Debian 13, OMV 8 family, Docker/Compose, LinuxServer Plex and AdGuard Home. Dedicated OS, apps/NVMe and main media disks. A separate removable movie USB disk supplements the main library. Backup moved to a separate flash device. A Python dashboard controls backups and removable storage. Family files are served through OMV-managed Samba shares. Optional remote access uses a VPN.

The source main media disk was 91% used; capacity needs monitoring. Plex was updated during the operating session. Exact package versions and personal device mappings belong in the private host record, not a reusable public example.

## Findings and reference decisions

| Finding | Impact | Decision in this reference |
| --- | --- | --- |
| Duplicated manuals, PDFs and old scripts | Contradictory instructions | One Markdown manual per topic; no historical copies in release |
| Private keys and full recovery exports alongside docs | Accidental publication | Clean-room public tree; never import original Git history or exports |
| Hard-coded disks, users and IPs | Cannot reproduce safely elsewhere | Private config with explicit placeholders and validation |
| Stale old backup UUID in OMV database | Future OMV regeneration may restore obsolete mounts | Record as outstanding live-host drift; review before applying filesystem deployment |
| Movie USB fstab and OMV entry differ | Two configuration sources | OMV owns mounts on new installs; do not duplicate manual entries |
| Live source backup copies appdata without stopping writers | Database consistency unproven | Reference performs offline appdata copies |
| Source script skips missing USB with exit zero | Timer success can hide no backup | Reference fails on missing/wrong filesystem |
| Mirror uses delete and lacks generations | Deletion propagates | Explain limitation; require separate independent copy |
| Source omits backup script/timer from recovery set | Incomplete rebuild kit | Reference source/services included; manual installation documented |
| Privileged source dashboard on all interfaces without auth | LAN users can invoke administration | Reference binds loopback, token authentication and CSRF guard |
| Nested movie bind under main media path | Empty USB folder confuses SMB browsing | New reference uses separate `/media-usb` container path |
| Forced SMB disconnect leaves stale Finder mount | Reconnect requires client action | Document eject/reopen; no promise of seamless Finder refresh |
| Moving USB requires Plex mount refresh | Brief service interruption | Explicit connect/eject with stop/start and normal unmount |
| Mutable latest image tags | Cannot reproduce exact version | Pin digests in private config and backup deployment records |

## Live-host issues intentionally not repaired by documentation work

The original server still uses its own Spanish dashboard, paths, service names and backup script. The public reference is an improved portable implementation, not a claim that the live host has been upgraded to it. Review the old OMV backup mount record, manual movie fstab entry, dashboard network exposure, live backup consistency, service backup coverage and stale dashboard backup copies before migrating. Avoid applying OMV filesystem deployment until its database and actual mounts agree.

## Validation boundaries

Unit tests check configuration safety and Compose structure. Python compilation, Compose schema validation and a publication scanner check the release. Full hardware recreation, unplug/replug and restore tests on a spare host remain mandatory. No claim of universal hardware compatibility or completed recovery certification is made.
