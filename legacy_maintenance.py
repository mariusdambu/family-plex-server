"""Add an OMV-session protected maintenance panel to an existing dashboard.

No passwords are handled here. Only the browser's existing OMV session cookie
is forwarded to the local, admin-only, read-only System.noop RPC.
"""
import fcntl
import hmac
import html
import json
import pathlib
import secrets
import subprocess
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
import maintenance as m

CSRF = secrets.token_urlsafe(32)
LABELS = dict(m.ACTIONS)


def admin_session(headers):
    """Let OMV enforce its own authentication, expiration and admin role."""
    try:
        cookies = SimpleCookie()
        cookies.load(headers.get('Cookie', ''))
        session = cookies.get('PHPSESSID')
        if session is None or not 16 <= len(session.value) <= 128:
            return False
        data = json.dumps({'service': 'System', 'method': 'noop', 'params': {},
                           'options': {'updatelastaccess': False}}).encode()
        request = Request('http://127.0.0.1/rpc.php', data=data, headers={
            'Content-Type': 'application/json', 'Cookie': 'PHPSESSID=' + session.value,
            'User-Agent': headers.get('User-Agent', '')})
        with urlopen(request, timeout=4) as response:
            result = json.loads(response.read(20000))
        return result.get('error') is None and isinstance(result.get('response'), str)
    except Exception:
        return False


def page(headers):
    authorized = admin_session(headers)
    if authorized:
        checks = m.checks()
    else:
        checks = {key: (False, 'Sign in to OMV as an administrator, then refresh this section.') for key in LABELS}
    forms = []
    for action, label in LABELS.items():
        allowed, reason = checks[action]
        disabled = '' if allowed else 'disabled'
        forms.append(f'''<form method="post" action="/maintenance/run">
<input type="hidden" name="csrf" value="{CSRF}">
<p><strong>{html.escape(label)}</strong><br>{html.escape(reason)}</p>
<label><input type="checkbox" name="confirm" value="{action}" required> I confirm the service interruption</label>
<button name="action" value="{action}" {disabled}>{html.escape(label)}</button></form>''')
    rows = []
    if authorized:
        for row in m.history():
            values = (time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(row['started'])),
                      LABELS.get(row['action'], row['action']), row['state'], row['detail'])
            rows.append('<tr>' + ''.join('<td>' + html.escape(str(value)) + '</td>' for value in values) + '</tr>')
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>PlexServer Maintenance</title><style>body{{font:16px system-ui;background:#11171b;color:#e7edf0;margin:0;padding:16px}}a{{color:#90d9b1}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}}form{{padding:16px;background:#1a2328;border:1px solid #39454b;border-radius:12px}}button{{display:block;margin-top:12px;padding:10px;font:inherit;border-radius:8px;cursor:pointer}}button:disabled{{opacity:.45;cursor:not-allowed}}td,th{{padding:8px;text-align:left;border-bottom:1px solid #39454b}}table{{width:100%;font-size:14px}}.scroll{{overflow:auto}}</style>
<h2>Safe maintenance</h2><p>{'OMV administrator session verified.' if authorized else 'An OMV administrator session is required.'}
 <a href="/maintenance/omv" target="_blank" rel="noopener">Open OMV</a> · <a href="/maintenance">Refresh status</a></p>
<p>Active Plex sessions block operations. Updates require a consistent backup from the last 24 hours. Updates do not automatically reboot the NAS.</p>
<div class="grid">{''.join(forms)}</div><h3>History</h3><div class="scroll"><table><tr><th>Started</th><th>Action</th><th>State</th><th>Detail</th></tr>{''.join(rows)}</table></div>
<p>If a button stays blocked after signing in to OMV, use the same server hostname/IP on both pages and refresh status.</p></html>'''


def respond(handler, status, body):
    payload = body.encode()
    handler.send_response(status)
    handler.send_header('Content-Type', 'text/html; charset=utf-8')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('X-Frame-Options', 'SAMEORIGIN')
    handler.send_header('Content-Length', str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def submit(handler):
    if not admin_session(handler.headers):
        respond(handler, 403, 'OMV administrator session required. <a href="/maintenance">Back</a>')
        return
    try:
        origin = handler.headers.get('Origin', '')
        if urlsplit(origin).netloc != handler.headers.get('Host', ''):
            raise ValueError()
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length < 2048:
            raise ValueError()
        data = parse_qs(handler.rfile.read(length).decode())
        action = data.get('action', [''])[0]
        if action not in LABELS or data.get('confirm', [''])[0] != action:
            raise ValueError()
        if not hmac.compare_digest(data.get('csrf', [''])[0], CSRF):
            raise ValueError()
    except (ValueError, UnicodeError):
        respond(handler, 400, 'Invalid request. <a href="/maintenance">Back</a>')
        return
    m.recover()
    allowed, reason = m.preflight(action)
    if not allowed:
        respond(handler, 409, html.escape(reason) + ' <a href="/maintenance">Back</a>')
        return
    # A transient unit survives a restart of the dashboard and supervises its children.
    name = 'plex-maintenance-' + secrets.token_hex(6)
    result = subprocess.run(['systemd-run', '--quiet', '--collect', '--unit=' + name,
                             '--property=UMask=0077', '--property=TimeoutStopSec=300',
                             '/usr/bin/python3', '/opt/family-plex/ops.py', action],
                            capture_output=True, timeout=15, check=False)
    if result.returncode:
        respond(handler, 503, 'Could not start the operation. <a href="/maintenance">Back</a>')
        return
    respond(handler, 202, 'Operation submitted. <a href="/maintenance">View history</a>')


def guarded_wd(original, action):
    with open(m.LOCK, 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False, 'Another maintenance or backup operation is running.'
        return original(action)
