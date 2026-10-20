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
LABELS = {'update_plex': 'Actualizar Plex', 'update_adguard': 'Actualizar AdGuard',
          'update_OMV': 'Actualizar OMV', 'reboot_host': 'Reiniciar servidor'}


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
        checks = {key: (False, 'Inicia sesion como administrador en OMV y actualiza esta seccion.') for key in LABELS}
    forms = []
    for action, label in LABELS.items():
        allowed, reason = checks[action]
        if 'backup marker is missing' in reason:
            reason = 'Primero ejecuta una copia consistente desde Backup > Ejecutar ahora.'
        elif 'last 24 hours' in reason:
            reason = 'Se requiere una copia consistente de las ultimas 24 horas.'
        disabled = '' if allowed else 'disabled'
        forms.append(f'''<form method="post" action="/maintenance/run">
<input type="hidden" name="csrf" value="{CSRF}">
<p><strong>{html.escape(label)}</strong><br>{html.escape(reason)}</p>
<label><input type="checkbox" name="confirm" value="{action}" required> Confirmo la interrupcion del servicio</label>
<button name="action" value="{action}" {disabled}>{html.escape(label)}</button></form>''')
    rows = []
    if authorized:
        for row in m.history():
            values = (time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(row['started'])),
                      LABELS.get(row['action'], row['action']), row['state'], row['detail'])
            rows.append('<tr>' + ''.join('<td>' + html.escape(str(value)) + '</td>' for value in values) + '</tr>')
    return f'''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Mantenimiento PlexServer</title><style>body{{font:16px system-ui;background:#11171b;color:#e7edf0;margin:0;padding:16px}}a{{color:#90d9b1}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}}form{{padding:16px;background:#1a2328;border:1px solid #39454b;border-radius:12px}}button{{display:block;margin-top:12px;padding:10px;font:inherit;border-radius:8px;cursor:pointer}}button:disabled{{opacity:.45;cursor:not-allowed}}td,th{{padding:8px;text-align:left;border-bottom:1px solid #39454b}}table{{width:100%;font-size:14px}}.scroll{{overflow:auto}}</style>
<h2>Mantenimiento seguro</h2><p>{'Sesion OMV administrativa verificada.' if authorized else 'Se requiere una sesion administrativa de OMV.'}
 <a href="/maintenance/omv" target="_blank" rel="noopener">Abrir OMV</a> · <a href="/maintenance">Actualizar estado</a></p>
<p>Las operaciones se bloquean con sesiones Plex activas. Las actualizaciones requieren backup consistente de las ultimas 24 horas. No se reinicia el NAS automaticamente al actualizar.</p>
<div class="grid">{''.join(forms)}</div><h3>Historial</h3><div class="scroll"><table><tr><th>Inicio</th><th>Operacion</th><th>Estado</th><th>Detalle</th></tr>{''.join(rows)}</table></div>
<p>Si un boton sigue bloqueado tras iniciar sesion en OMV, usa el mismo nombre/IP del servidor en ambas paginas y pulsa Actualizar estado.</p></html>'''


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
        respond(handler, 403, 'Sesion administrativa OMV requerida. <a href="/maintenance">Volver</a>')
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
        respond(handler, 400, 'Solicitud no valida. <a href="/maintenance">Volver</a>')
        return
    m.recover()
    allowed, reason = m.preflight(action)
    if not allowed:
        respond(handler, 409, html.escape(reason) + ' <a href="/maintenance">Volver</a>')
        return
    # A transient unit survives a restart of the dashboard and supervises its children.
    name = 'plex-maintenance-' + secrets.token_hex(6)
    result = subprocess.run(['systemd-run', '--quiet', '--collect', '--unit=' + name,
                             '--property=UMask=0077', '--property=TimeoutStopSec=300',
                             '/usr/bin/python3', '/opt/family-plex/ops.py', action],
                            capture_output=True, timeout=15, check=False)
    if result.returncode:
        respond(handler, 503, 'No se pudo iniciar la operacion. <a href="/maintenance">Volver</a>')
        return
    respond(handler, 202, 'Operacion enviada. <a href="/maintenance">Consultar historial</a>')


def guarded_wd(original, action):
    with open(m.LOCK, 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False, 'Hay otra operacion de mantenimiento o backup en curso.'
        return original(action)
