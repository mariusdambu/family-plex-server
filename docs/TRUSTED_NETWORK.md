# Optional trusted-network dashboard integration

This is an explicitly opt-in alternative to the authenticated reference dashboard and the OMV-session adapter. Select this policy only after explicit owner approval. Password-protected HTTPS integrations must additionally apply the session gate described in DASHBOARD_LOGIN.md to every route. Every permitted network device may update applications or restart the NAS. A compromised LAN/tailnet client has the same access. Never expose this interface to the Internet, port-forward it, or put an unauthenticated public proxy in front of it.

`network_maintenance.py` provides a maintenance page, polling status/history and fixed command dispatch. It does not provision a web server or replace the reference `dashboard.py` automatically. An existing dashboard handler must call `trusted(handler)` for **every** request before routing, serve `page(headers)` at `/maintenance`, JSON `status()` at `/maintenance/status`, and call `submit(handler)` at `/maintenance/run`. Preserve network checks on legacy routes as well. Use same-origin checks for every mutating route; maintenance additionally requires a CSRF token and explicit interruption confirmation.

Install a root-owned mode-600 `/etc/family-plex/network-policy.json`, adjusted to the actual machine:

```json
{
  "networks": ["127.0.0.0/8", "192.0.2.0/24", "100.64.0.0/10"],
  "hosts": ["127.0.0.1:8090", "192.0.2.10:8090", "100.80.1.2:8090"],
  "language": "en"
}
```

Documentation addresses must be replaced. Include actual hostname aliases, with port, only if needed. Unlisted Host headers and socket peer addresses are rejected. Forwarded headers are not trusted. The Tailscale address range is not an identity check: review tailnet ACLs and do not route untrusted CGNAT networks to this listener. Internet traffic proxied by an allowed LAN device can bypass a source-address boundary; do not deploy such a proxy. IPv6 requires an explicitly reviewed network/host policy and listener support.

The page polls every five seconds without navigation and retains confirmation checkboxes. It warns about recent backup availability but does not block updates for it. Active Plex sessions (including paused sessions), unavailable playback verification, concurrent operations and missing application storage still block actions. Restart requires a checkbox plus browser confirmation. Updates are not version discovery: pinned image digests must be changed intentionally to select a new release.

Production homepage integration polls lightweight service/backup status separately. A backup intentionally pauses Plex and AdGuard: display this as maintenance, not an unexplained service failure. Polling failures must disable maintenance controls and report unavailable state. Do not trigger real updates, backups or restarts to test UI wiring.

Keep an independent snapshot of the original dashboard and backend before installation. To roll back, restore the prior dashboard/backend and restart only its dashboard service; do not alter media or running containers.
