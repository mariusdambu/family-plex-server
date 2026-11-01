# Example family accounts

Use fictional logins: `father`, `mother`, `child1`, `child2`. Display names may be Father, Mother, Child 1, Child 2. None of these accounts or passwords are supplied or precreated in the repository.

In OMV Users, create a `family` group. Create the four accounts with distinct strong passwords, add them to `family`, and grant SMB access. Do not give children SSH shells, sudo access, Docker membership or OMV administrator rights. Docker group membership is effectively root access.

Create a separate administrator account for host maintenance. The two parent accounts can receive access to both children's files without becoming system administrators.

| Folder | Father | Mother | Child 1 | Child 2 | Plex |
| --- | --- | --- | --- | --- | --- |
| Family/Shared | Read/write | Read/write | Read/write | Read/write | None |
| Family/father | Read/write | None | None | None | None |
| Family/mother | None | Read/write | None | None | None |
| Family/child1 | Read/write | Read/write | Read/write | None | None |
| Family/child2 | Read/write | Read/write | None | Read/write | None |
| Media and Movies_USB | Read/write | Read/write | Read-only | Read-only | Read-only |
| Archive and Drivers | Read/write | Read/write | Read-only | Read-only | None |
| Appdata / backup device | Administrator only | Administrator only | None | None | Its own appdata |

Use OMV shared-folder ACLs with named user entries and default ACLs for new files. Grant traverse access on parent directories. Deny other users and guest access; do not use blanket `chmod -R 777`. SMB share privileges and filesystem ACLs must both permit the intended access. A Samba `force group` setting is not a substitute for private-folder ACLs.

For media, configure parents in Samba's write list and children in the read list, or equivalent OMV privileges. Create children with no shell. Verify by logging in as each account; a parent test does not validate child isolation. Keep inherited ACL masks in mind when changing permissions.

On macOS open Finder > Network > your server and choose a share, or use `smb://YOUR_SERVER/Movies_USB`. Every opened share is an SMB connection even without a sidebar shortcut. Windows uses `\\YOUR_SERVER\Movies_USB`.

Passwords must be created on the target host through OMV. Never put real passwords, password hashes, SSH keys, AdGuard YAML or Plex preferences in a Git commit.
