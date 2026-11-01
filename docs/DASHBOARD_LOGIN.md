# Optional password-protected HTTPS dashboard integration

`dashboard_auth.py` supplies a password login/session gate for an existing dashboard. It is separate from the small SSH-tunnel/Basic-auth reference dashboard and supersedes the password-free policy when enabled. Install only after explicit owner approval. Keep the original dashboard/backend snapshot until acceptance.

The production integration calls the gate **after** socket peer/Host restrictions and **before every GET/POST route**, including project assets, maintenance, backups and polling. Login and logout are handled by the gate. Never leave a second unauthenticated HTTP listener, route or proxy serving the same content.

The HTTPS listener uses a valid certificate and TLS 1.2 or later. HTTP only redirects GETs to a fixed canonical HTTPS hostname and refuses POSTs. No password is accepted over HTTP. Tailscale HTTPS certificates require enabling MagicDNS/HTTPS in its admin console and certificate-transparency acknowledgement. The hostname becomes public in certificate records; access does not become public. Do not enable Funnel or Internet port forwarding. Clients must use the certificate's full DNS name, not a bare IP. With Tailscale DNS this requires an active Tailscale client, including when at home unless separate LAN DNS is deliberately configured.

## Initial password and forgotten password

From the server's root console or an authorized SSH terminal:

```sh
python3 /opt/family-plex/dashboard_auth.py password
```

This prompts twice without echo and requires at least 12 characters. Never supply a password as a command argument, paste it into chat, put it into source control or use a shared default. Python must provide `hashlib.scrypt` (the Debian production Python does; some old macOS Python builds do not).

The same command resets a forgotten password without knowing the old one. It generates a new salt and session generation and invalidates all existing sessions. Recovery requires SSH/root console access; no master password or email reset endpoint exists. If both dashboard and SSH access are lost, use the physical root console/recovery procedure. Preserve independent root recovery credentials privately.

Only a scrypt hash and random salt are stored at `/etc/family-plex/dashboard-password.json`, mode 600. Sessions persist as token hashes in `/var/lib/family-plex/dashboard-auth.sqlite3`, mode 600, and expire after seven days without rolling renewal. Cookies use Secure, HttpOnly, SameSite=Strict and the `__Host-` prefix. Logout revokes the individual server-side session; password reset revokes all. Five failed logins from one socket peer produce a 15-minute cooldown. Expensive password verification is serialized to protect a small CPU.

Missing password/configuration fails closed. Never publish project files until HTTPS and the gate are actually active. Backups containing password hashes/sessions remain private. A restored session database is not needed for recovery: revoke sessions and set a new password after restoring or replacing the host.

## Browser login diagnostics

Project catalogue metadata may declare an alternative HTML entry, for example `{"entry":"install.html"}`. The entry must be a visible HTML filename inside that project; no symlink, parent traversal or absolute entry is allowed. Without metadata the default remains `index.html`.

DOCX downloads are private by default. To publish a specific document behind the same login, add its project-relative filename to `portal.json`, for example `{"downloads":["Template.docx"]}`. Only declared DOCX files are accepted; JSON metadata, undeclared documents and hidden paths remain blocked. The server supplies the Word MIME type and attachment Content-Disposition with a UTF-8 filename. Use relative HTTPS links in the application rather than a workstation-specific `file://` path. Do not place corporate documents or metadata in the public source repository.

Keep the `__Host-` cookie prefix when using the valid HTTPS hostname. A non-default HTTPS port does not itself invalidate that prefix. The login page performs a same-origin `/login/check` request and displays whether the browser actually returned the nonce cookie; the endpoint returns only a boolean, never cookie values. Do not remove Secure/HttpOnly/SameSite or accept invalid certificates to troubleshoot login.

Login GET reuses a valid existing nonce so opening another tab or prefetching login does not invalidate an earlier form. Missing cookies and stale/mismatched forms receive explicit recovery messages before any password verification. Only fixed rejection categories are logged; passwords, cookies and submitted forms are never logged. Password/session files are not changed by this compatibility fix.

Origin and Host comparison normalizes DNS case and the default HTTPS port (443). Distinct non-default ports, different hosts, HTTP origins, opaque origins and arbitrary forwarded headers remain rejected. This deployment terminates TLS directly; do not trust proxy headers without a separate reviewed proxy configuration.

## Acceptance and certificate renewal

Test unauthenticated access to the homepage, project HTML/JS/images, maintenance status and every mutating endpoint. Verify a valid HTTPS chain and hostname, session expiry, logout and reset revocation. Test actual passwords only in an operator-controlled browser/terminal; automated tests use isolated temporary files and test-only passwords. Do not execute real maintenance for testing.

Certificates issued to disk by `tailscale cert` need a renewal timer and dashboard reload/restart when replaced. Keep keys root-only. A production activation is incomplete until certificate renewal, the operator's initial password and a browser login have been verified. Do not describe staged code as an active protected dashboard.

### Optional OMV certificate enrollment

OMV may use the same valid DNS certificate on a separate HTTPS port. Import it through CertificateMgmt and enable HTTPS through WebGui, preserving the existing settings. Deploy only the OMV `certificates` and `nginx` states; do not edit generated nginx files. Dashboard links must use the certificate hostname and OMV HTTPS port, independently of the dashboard port.

After explicit enrollment, store the existing OMV certificate UUID in `/etc/family-plex/tls/omv-certificate-uuid` (root-only). The renewal helper updates that specific record using the local OMV RPC API and passes key material on stdin. It reapplies certificates/nginx when required and records the successful deployment digest in `omv-deployed-sha256`; failed deployments are retried on the next run. Hosts without the enrollment marker never invoke OMV. Preserve the previous WebGui settings and sources for rollback, and verify the HTTPS chain and hostname before switching links.
