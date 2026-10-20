# Family Plex Server

A small, reproducible home server: OpenMediaVault 8 on Debian 13, Plex and AdGuard Home in Docker, family SMB folders, an optional removable movie disk, a USB backup, and a local administration dashboard.

Start with [Installation](docs/INSTALL.md). Use [Migration](docs/MIGRATION.md) to move to another PC or RAID storage, [Operations](docs/OPERATIONS.md) after setup, [Recovery](docs/RECOVERY.md) after a failure, and [Architecture](docs/ARCHITECTURE.md) to understand the design. [Audit](docs/AUDIT.md) explains the source installation and limitations. [AI handoff](AGENTS.md) defines the rules for future assistants.

This repository is a clean reference implementation derived from an operating home server. It contains no personal accounts, credentials, app databases, disk images, media, machine UUIDs, or original exports. It is not an unattended OS installer. Disk selection, OMV shares, passwords, Plex claiming and AdGuard onboarding require explicit local setup.

## Layout

```text
config.example.json    Non-secret configuration template
configure.py           Validate configuration and generate Compose
ops.py                 Backup, update, removable disk operations
dashboard.py           Authenticated loopback dashboard
systemd/               Service and timer templates
docs/                  One current manual per topic
tests/                 Non-destructive checks
```

No third-party dependencies are vendored. Python uses the standard library. Obtain the OS, Docker images and packages from their official upstreams; see [Dependencies](docs/DEPENDENCIES.md). Containers are selected explicitly in your private configuration; record immutable image digests for reproducible reinstalls.

## Quick orientation

1. Install Debian/OMV and Docker following their official instructions.
2. Mount your disks by UUID through OMV; create your own accounts and SMB shares.
3. Copy `config.example.json` to `/etc/family-plex/config.json`, replace every placeholder, and keep it private (`chmod 600`).
4. Install this source at `/opt/family-plex`. Run `sudo python3 /opt/family-plex/configure.py`.
5. Review `/etc/family-plex/compose.json`, then start it using the command in the installation manual.
6. Complete Plex/AdGuard onboarding; install the optional dashboard and backup timer.

The repository never formats a disk. Backup is an overwriting mirror, not version history; deleted source files disappear from the next mirror. Media files are deliberately excluded from backup by default.

Validation: `python3 -m unittest discover -s tests -v`. No automated test here changes mounts, users, services or disks. Full installation and restore acceptance must be performed on a spare machine before relying on it.
