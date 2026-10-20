# Install on another computer

Read all steps before running commands. Use a spare machine for rehearsal. Keep existing data disks disconnected while installing the OS to avoid selecting the wrong disk.

## 1. Obtain the platform

Use the official [OMV installation guide](https://docs.openmediavault.org/en/latest/installation/) for OMV 8 / Debian 13. Install to a dedicated OS disk. Download installation media from upstream and verify its supplied checksum. See [Dependencies](DEPENDENCIES.md). Enable SSH and use a new keypair generated on your own client; never reuse somebody else's key. Reserve a LAN address in your router. Set your timezone in OMV.

Install Docker Engine and the Compose plugin using the [official Debian instructions](https://docs.docker.com/engine/install/debian/). Install required host tools:

```sh
sudo apt-get update
sudo apt-get install python3 rsync acl psmisc util-linux samba-common-bin
docker compose version
```

Use a Compose version supporting long bind syntax and `create_host_path: false`; upgrade if `docker compose config` rejects it. Configure Docker's data root on the apps disk before starting services if the OS disk is small; follow [Docker daemon guidance](https://docs.docker.com/engine/daemon/). Do not copy a running Docker data directory.

## 2. Prepare storage in OMV

Identify each disk by model, serial and size. Format only disks you explicitly intend to erase. The project does not automate formatting. Use ext4 for apps, media, removable movies and backups to preserve Linux ACLs. Mount the apps, primary media and removable movie disk through OMV Storage > File Systems. Note their UUID paths using `lsblk -f` and `findmnt`.

Give the movie disk a persistent UUID mount with `nofail`. Keep the backup device separate. It must be mounted at the configured path before backup; this reference does not silently skip a missing backup. OMV should remain the owner of persistent mounts; do not add competing fstab entries.

For an initially absent movie disk, before mounting it for the first time, create an **empty** `Media` directory underneath its mountpoint. Then mount the disk and create `Media/Movies` on the actual disk. This lets Plex start with the main library when the USB is absent. Verify each step with `findmnt`; never store films in the underlying empty directory.

## 3. Accounts and directories

Follow [Family accounts](USERS.md). Create `Family`, `Archive`, `Drivers` on apps storage; `Media/Movies`, `Media/Series`, `Media/Documentaries`, `Media/Kids` on primary media; and `Media/Movies` on the movie USB. Create `docker/appdata/plex`, `docker/appdata/adguard/work` and `docker/appdata/adguard/conf` on apps storage.

Create a dedicated unprivileged `plexapp` account in OMV. Read its actual IDs using `id plexapp`. Give it read/traverse access to both media trees and ownership of its Plex appdata directory. Do not assume the example UID matches a new machine. Give family members write access to media shares using ACLs in OMV. Restrict private per-user folders as described in USERS.md.

## 4. Install this project and configure

Clone this repository; copy its source to `/opt/family-plex` (root-owned, not writable by family users). Create `/etc/family-plex` with mode 700. Copy `config.example.json` there as `config.json`, mode 600. Edit all fields:

- Replace `192.0.2.10` (documentation-only address) with your reserved LAN IPv4 address.
- Use your own filesystem mountpoints and UUIDs, timezone, and Plex IDs. Apps and primary media may share one mounted RAID pool; USB movies and backup use separate filesystems. See [Migration](MIGRATION.md).
- Generate a dashboard password with `openssl rand -hex 32`; insert it locally without posting it to chat or GitHub.
- Check the example image digests for your architecture and select newer verified releases when appropriate. `latest` is not an immutable version.

```sh
sudo python3 /opt/family-plex/configure.py
sudo docker compose -f /etc/family-plex/compose.json config --quiet
sudo docker compose -f /etc/family-plex/compose.json pull
sudo docker compose -f /etc/family-plex/compose.json up -d
```

After pulling, obtain each `RepoDigests` using `docker image inspect IMAGE --format '{{json .RepoDigests}}'`. Save the selected `image@sha256:...` in the private config, regenerate Compose, and retain that private config in your backup. Confirm the selected architecture exists.

## 5. Complete first-run setup

Plex: open `http://YOUR_SERVER:32400/web`, claim the server with your own account and add primary and USB library paths. USB movies are `/media-usb/Movies`. No Plex token is provided by this repo.

AdGuard: use `http://YOUR_SERVER:3000` for initial onboarding. Select port **80 inside the container** for its regular web UI, then use host port 8080. Create your own admin credentials. Verify DNS on the reserved LAN address before making it the router's DNS. If port 53 conflicts, inspect `ss -luntp` and upstream instructions rather than disabling the host resolver blindly. DHCP service is outside this template.

Create SMB exports through OMV, selecting the relevant shared folders; do not edit `/etc/samba/smb.conf`. Name the removable movie share `Movies_USB` (or match `usb_share` in config). Restrict it to the family group and allow writes. Existing source-installation share names may be kept privately but are not required here.

## 6. Install optional services

Copy the three files from `systemd/` to `/etc/systemd/system/`:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now family-plex-dashboard.service
sudo systemctl enable --now family-plex-backup.timer
```

From your client use `ssh -L 8090:127.0.0.1:8090 YOUR_ADMIN@YOUR_SERVER`. Open `http://127.0.0.1:8090` and log in as `admin` with the private dashboard token. If port 8090 is used locally, forward 18090 instead and open that port.

## Acceptance checklist

- Host boots with movie USB absent; main library works.
- Plex reads both media roots when connected; movies play.
- Each family login can access only the intended folders.
- AdGuard answers DNS; household fallback DNS procedure works.
- Dashboard rejects unauthenticated requests and is reachable only through the intended tunnel.
- Backup completes and a sample file plus Plex appdata restore succeeds on spare storage.
- Eject refuses unrelated busy handles, closes only the movie SMB share, and reports success before unplugging.
- Reconnect restores Plex access; Finder eject/reopen works if needed.

Do not call this a tested deployment until this checklist passes on the target machine.
