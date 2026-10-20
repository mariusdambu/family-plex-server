# Obtain dependencies without storing them in Git

| Component | Official source | What to retain privately |
| --- | --- | --- |
| OMV 8 / Debian 13 | [OMV install](https://www.openmediavault.org/install), [Debian](https://www.debian.org/distrib/) | Release, architecture, ISO checksum |
| Docker Engine + Compose | [Docker Debian install](https://docs.docker.com/engine/install/debian/) | Package versions, daemon data-root |
| Plex container | [LinuxServer Plex](https://docs.linuxserver.io/images/docker-plex/) | Immutable RepoDigest, appdata backup |
| AdGuard container | [Official Docker guide](https://github.com/AdguardTeam/AdGuardHome/wiki/Docker) | Immutable RepoDigest, private conf/work |
| Python 3 | Debian `python3` | Version |
| rsync, ACLs, mounts, SMB control | Debian `rsync acl util-linux samba-common-bin` | Package versions |
| Optional VPN | [Tailscale Linux](https://tailscale.com/download/linux) | Your own account and recovery procedure |

Docker pulls its own images; no image archive is included. Upstreams may remove old images, so retain a private offline image export if exact long-term recovery matters. OS ISOs, packages, Python virtual environments, node_modules, appdata, databases, tokens and backups do not belong in this repository. Do not redistribute Plex or other third-party software under an invented project license.

`latest` changes over time. The example pins the upstream digests observed on the audited x86-64 deployment on 2026-10-20. Check architecture availability and upstream security updates before a new deployment. Record replacements in your private config. Verify upstream downloads using published checksums/signatures. No project code requires pip or npm packages.
