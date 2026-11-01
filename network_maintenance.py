"""Explicit trusted-network adapter: no user authentication. Never expose publicly."""
import hmac
import html
import ipaddress
import json
import pathlib
import secrets
import subprocess
import time
from urllib.parse import parse_qs, urlsplit
import maintenance as m
from configure import load

POLICY = pathlib.Path('/etc/family-plex/network-policy.json')
CSRF = secrets.token_urlsafe(32)


def trusted(handler):
    """Use socket peer, never forwarded headers. Restrict Host against DNS rebinding."""
    try:
        policy = json.loads(POLICY.read_text())
        peer = ipaddress.ip_address(handler.client_address[0])
        host = handler.headers.get('Host', '')
        return (host in policy['hosts'] and
                any(peer in ipaddress.ip_network(net) for net in policy['networks']))
    except (OSError, ValueError, KeyError):
        return False


def respond(handler, status, value, *, json_body=False):
    body = (json.dumps(value) if json_body else value).encode()
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json' if json_body else 'text/html; charset=utf-8')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('X-Frame-Options', 'SAMEORIGIN')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def status():
    warning = ''
    try:
        m.backup_ready(load())
    except Exception as error:
        warning = str(error)
    return {'checks': m.checks(), 'history': m.history(), 'backup_warning': warning,
            'csrf': CSRF}


def page(headers):
    spanish = json.loads(POLICY.read_text()).get('language') == 'es'
    labels = (['Update Plex', 'Update AdGuard', 'Update OMV', 'Restart server']
              if spanish else list(m.ACTIONS.values()))
    title = 'Maintenance' if spanish else 'Maintenance'
    confirm = 'I confirm the service interruption' if spanish else 'I confirm the service interruption'
    cards = ''.join(f'''<form data-action="{action}"><h2>{html.escape(label)}</h2>
<p class="reason">…</p><label><input type="checkbox" required>{confirm}</label>
<button disabled>{html.escape(label)}</button></form>'''
                    for action, label in zip(m.ACTIONS, labels))
    host = headers.get('Host', '').split(':')[0]
    mode = 'Tailscale' if host.startswith('100.') else ('Local network' if spanish else 'Local network')
    text = ('Trusted LAN/Tailscale access, without an OMV session. Status updates every five seconds.'
            if spanish else 'Trusted LAN/Tailscale access, without OMV sign-in. Status updates every 5 seconds.')
    return '''<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>''' + title + '''</title><style>
body{font:16px system-ui;background:#101316;color:#eef3f6;max-width:1200px;margin:auto;padding:24px}
a{color:#90d9b1}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
form{background:#191f24;padding:20px;border:1px solid #39454b;border-radius:14px}
button{display:block;padding:12px;margin-top:18px;border:0;border-radius:8px;font:inherit;cursor:pointer;background:#75d58b;color:#102318}
button:disabled{background:#39454b;color:#b5bec5;cursor:not-allowed}.reason{min-height:3em}td,th{text-align:left;padding:10px;border-bottom:1px solid #39454b}
.scroll{overflow:auto}#warning{color:#f0bd61}#message{min-height:2em}</style>
<a href="/">← PlexServer</a><h1>''' + title + '''</h1><p>''' + html.escape(mode + ' · ' + host) + '''</p>
<p>''' + text + '''</p><p id="warning"></p><p id="message" role="status"></p><div class="grid">''' + cards + '''</div>
<h2>''' + ('History' if spanish else 'History') + '''</h2><div class="scroll"><table><tbody id="history"></tbody></table></div>
<script>
const es=''' + json.dumps(spanish) + '''; let token='', sending=false;
const message=document.getElementById('message');
async function refresh(){try{
const r=await fetch('/maintenance/status',{cache:'no-store'});if(!r.ok)throw Error(r.status);
const s=await r.json();token=s.csrf;
for(const f of document.querySelectorAll('form')){const [ok,why]=s.checks[f.dataset.action];
f.querySelector('button').disabled=!ok||sending;
f.querySelector('.reason').textContent=ok?(es?'Ready':'Ready'):(es?'Blocked: ':'Blocked: ')+why;}
document.getElementById('warning').textContent=s.backup_warning?
(es?'Aviso: no se verifica una copia reciente. Puedes continuar; revisa tu backup.':'Warning: a recent backup cannot be verified. You may continue; review your backup.'):
(es?'Recent backup verified. It is not required to update.':'Recent backup verified. It is not required to update.');
const rows=s.history.map(x=>{const tr=document.createElement('tr');
for(const v of [new Date(x.started*1000).toLocaleString(),x.action,x.state,x.detail]){const td=document.createElement('td');td.textContent=v;tr.append(td);}return tr;});
document.getElementById('history').replaceChildren(...rows);
}catch(e){for(const b of document.querySelectorAll('button'))b.disabled=true;
message.textContent=es?'Server unavailable. Retrying…':'Server unavailable. Retrying…';}}
for(const f of document.querySelectorAll('form'))f.addEventListener('submit',async e=>{
e.preventDefault();if(sending)return;
if(f.dataset.action==='reboot_host'&&!confirm(es?'Restart the NAS and interrupt services?':'Restart the NAS and interrupt services?'))return;
sending=true;for(const b of document.querySelectorAll('button'))b.disabled=true;
try{const r=await fetch('/maintenance/run',{method:'POST',body:new URLSearchParams({action:f.dataset.action,confirm:f.dataset.action,csrf:token})});
const s=await r.json();message.textContent=s.message;if(r.ok)f.reset();}
catch(e){message.textContent=es?'Submission uncertain; check history before retrying.':'Submission uncertain; check history before retrying.';}
finally{sending=false;await refresh();}});
refresh();setInterval(refresh,5000);
</script></html>'''


def submit(handler):
    if not trusted(handler):
        respond(handler, 403, {'message': 'Network not permitted'}, json_body=True)
        return
    try:
        origin = urlsplit(handler.headers.get('Origin', ''))
        if origin.scheme not in ('http', 'https') or origin.netloc != handler.headers.get('Host', ''):
            raise ValueError()
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length < 2048:
            raise ValueError()
        data = parse_qs(handler.rfile.read(length).decode())
        action = data.get('action', [''])[0]
        if action not in m.ACTIONS or data.get('confirm', [''])[0] != action:
            raise ValueError()
        if not hmac.compare_digest(data.get('csrf', [''])[0], CSRF):
            raise ValueError()
    except (ValueError, UnicodeError):
        respond(handler, 400, {'message': 'Invalid request'}, json_body=True)
        return
    m.recover()
    allowed, reason = m.preflight(action)
    if not allowed:
        respond(handler, 409, {'message': reason}, json_body=True)
        return
    try:
        result = subprocess.run(['systemd-run', '--quiet', '--collect',
            '--unit=plex-maintenance-' + secrets.token_hex(6), '--property=UMask=0077',
            '--property=TimeoutStopSec=300', '/usr/bin/python3', '/opt/family-plex/ops.py', action],
            capture_output=True, timeout=15, check=False)
        if result.returncode:
            raise RuntimeError()
    except (RuntimeError, subprocess.TimeoutExpired, OSError):
        respond(handler, 503, {'message': 'Dispatch not confirmed; check history before retrying'}, json_body=True)
        return
    respond(handler, 202, {'message': 'Operation submitted'}, json_body=True)
