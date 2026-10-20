# Instructions for future assistants

Read README.md and docs/INSTALL.md, ARCHITECTURE.md, AUDIT.md and RECOVERY.md first. Treat this as a reusable reference, not a snapshot of somebody else's disks.

Read docs/MIGRATION.md before hardware replacement or RAID work. Portability is a primary goal. Apps and primary media can share a mounted pool; backup remains independent. Preserve container paths and user IDs when moving data. Do not claim that OS provisioning, RAID creation or full OMV identity restoration is automated.

- Inspect the target host read-only before proposing changes. Identify storage by UUID plus physical model/serial/size; never infer `/dev/sdX` identity from an example.
- Obtain explicit approval before formatting or deleting data. These scripts do not format disks.
- Use private config at `/etc/family-plex/config.json`. Never request the user to paste tokens, private keys, full AdGuard YAML or Plex databases into public tools.
- Register mounts and shares through the installed OMV API/UI; inspect its version and schema. Do not edit generated Samba configuration or invent model identifiers.
- Stop application writers before backup/restore of databases. Verify mount identity before mirror operations. Never force/lazily unmount removable disks.
- Respect existing user data, custom ACLs and media library paths. Do not migrate a running host to this reference without a separate reviewed migration plan.
- Use only fixed administrative commands in the dashboard. Keep authentication, CSRF protection, loopback binding and root-only configuration permissions.
- Run `python3 -m unittest discover -s tests -v` and `python3 tests/check_publication.py`. Validate generated Compose on a Linux Docker host. Do not run privileged integration actions on production to test documentation.
- Report what was actually tested. A successful copy does not prove a recoverable database or complete restore.
- Keep all public files in English. Keep one current manual per topic. No archives, binaries, generated exports, private history or dependencies in Git.
