# Reference audit — 2026-11-01

This is an English, parameterized reconstruction reference, not a copy of a private server filesystem. Credentials, device identities, app databases, media, corporate projects and operational inventories are deliberately excluded. Public configuration uses reserved documentation addresses and replaceable placeholders.

## Current boundaries

- Debian 13 / OMV 8, Docker Compose, LinuxServer Plex and optional AdGuard Home. Register mounts and SMB through OMV; never edit generated Samba files.
- The default dashboard remains loopback-bound with Basic authentication and CSRF. Password-protected HTTPS, trusted-network policy and private project assets are optional integration modules with explicit instructions; they are not silently enabled on new installs.
- Maintenance has a closed action allowlist, Plex-session checks, persistent history, boot-ID recovery and HTTP/DNS verification. Backup freshness is advisory. Parked AdGuard cannot be started through its update action.
- Backups stop active application writers and mirror private appdata/configuration/source. They exclude the OS, installed images and media libraries. Mirrors are not version history or a tested bare-metal image.
- Legacy removable storage retains its original behavior. Optional hotplug uses an isolated shared parent and read-only slave propagation; a confirmed force eject stops only Plex, never forcibly unmounts filesystems or kills unrelated processes.
- exFAT supports portability to macOS/Windows but lacks Linux POSIX ACLs. Apps and backup should retain filesystems that preserve Linux ownership/ACLs. Never promise native exFAT formatting or repair support from the reference.
- Hardware, storage creation, RAID selection, accounts, credentials, library definitions, router/VPN settings and complete restore rehearsal remain operator responsibilities.

## Validation

Run the complete unit suite, publication guard and Compose schema checks for both the default and hotplug/parked configurations. Tests use mocks or temporary data and must not execute production maintenance. A successful source test, transfer or backup marker is not proof of hardware integrity or a complete recovery. Repeat the installation and restore acceptance checklist on spare hardware before relying on it.
