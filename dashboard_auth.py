"""Password login for the production dashboard; HTTPS is mandatory.

Root-only CLI: python3 dashboard_auth.py password. This initializes or resets
the password and revokes every existing session. No password appears in argv.
"""
import contextlib
import getpass
import hashlib
import hmac
import html
import json
import logging
import os
from pathlib import Path
import secrets
import sqlite3
import time
import threading
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

ROOT = Path('/etc/family-plex')
PASSWORD = ROOT / 'dashboard-password.json'
STATE = Path('/var/lib/family-plex/dashboard-auth.sqlite3')
COOKIE = '__Host-PlexSession'
NONCE = '__Host-PlexLogin'
LIFETIME = 7 * 86400
LOGIN_LOCK = threading.Lock()


@contextlib.contextmanager
def connection():
    STATE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(STATE, timeout=5)
    STATE.chmod(0o600)
    db.execute('CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, expires REAL, generation TEXT, csrf TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS attempts (peer TEXT PRIMARY KEY, count INTEGER, until REAL)')
    db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
    db.commit()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def derive(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1,
                          maxmem=64 * 1024 * 1024, dklen=32).hex()


def set_password(password):
    if len(password) < 12 or len(password) > 1024:
        raise ValueError('Use between 12 and 1024 characters')
    salt = secrets.token_bytes(16)
    record = {'salt': salt.hex(), 'hash': derive(password, salt),
              'generation': secrets.token_hex(16)}
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = PASSWORD.with_suffix('.tmp')
    fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(record, out)
        out.flush()
        os.fsync(out.fileno())
    temporary.replace(PASSWORD)
    with connection() as db:
        db.execute('DELETE FROM sessions')
        db.execute('DELETE FROM attempts')


def record():
    info = PASSWORD.stat()
    if info.st_mode & 0o077 or info.st_uid != os.geteuid():
        raise ValueError('Password file permissions are unsafe')
    return json.loads(PASSWORD.read_text())


def cookies(handler):
    try:
        result = SimpleCookie()
        result.load(handler.headers.get('Cookie', ''))
        return result
    except Exception:
        return SimpleCookie()


def login_nonce(handler):
    value = cookies(handler).get(NONCE)
    if value and len(value.value) == 64 and all(c in '0123456789abcdef' for c in value.value):
        return value.value
    return None


def session(handler):
    try:
        value = cookies(handler).get(COOKIE)
        if value is None or len(value.value) != 64:
            return None
        digest = hashlib.sha256(value.value.encode()).hexdigest()
        generation = record()['generation']
        with connection() as db:
            row = db.execute('SELECT csrf FROM sessions WHERE token=? AND expires>? AND generation=?',
                             (digest, time.time(), generation)).fetchone()
        return row[0] if row else None
    except (OSError, ValueError, KeyError, sqlite3.Error):
        return None


def send(handler, status, body='', *, cookie=None, location=None, content_type='text/html; charset=utf-8'):
    payload = body.encode()
    handler.send_response(status)
    handler.send_header('Content-Type', content_type)
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('X-Frame-Options', 'DENY')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('Referrer-Policy', 'same-origin')
    if cookie:
        handler.send_header('Set-Cookie', cookie)
    if location:
        handler.send_header('Location', location)
    handler.send_header('Content-Length', str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def cookie(name, value, age):
    return f'{name}={value}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age={age}'


def login_page(handler, message=''):
    if not PASSWORD.is_file():
        send(handler, 503, '<h1>Protected dashboard</h1><p>Set a password from SSH or the host console with dashboard_auth.py password.</p>')
        return
    # Reuse an existing nonce: another tab/prefetch must not invalidate a form.
    nonce = login_nonce(handler) or secrets.token_hex(32)
    send(handler, 200, '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Sign in · Family Plex</title>
<style>body{font:18px system-ui;background:#101316;color:#eef3f6;max-width:420px;margin:12vh auto;padding:24px}
input,button{box-sizing:border-box;width:100%;padding:14px;margin-top:16px;font:inherit;border-radius:8px}
button{background:#75d58b;border:0;cursor:pointer}p{color:#adb8bf}</style><h1>PlexServer</h1>
<p>Private dashboard · LAN and Tailscale</p><p role="status">''' + html.escape(message) + '''</p>
<p id="cookie-status" role="status">Checking secure access…</p>
<form method="post" action="/login"><input type="hidden" name="nonce" value="''' + nonce + '''">
<label>Password<input type="password" name="password" required maxlength="1024" autocomplete="current-password" autofocus></label>
<button>Sign in</button></form><p>Sessions last seven days. Reset a forgotten password through SSH or the NAS console.</p>
<script>fetch('/login/check',{credentials:'same-origin',cache:'no-store'})
.then(r=>{if(!r.ok)throw Error();return r.json();}).then(s=>{
document.getElementById('cookie-status').textContent=s.cookie_ready?'Secure connection and login cookie verified.':'The browser did not return the login cookie. Allow cookies for this site and use its valid HTTPS hostname.';
}).catch(()=>{document.getElementById('cookie-status').textContent='Could not verify the connection. Reload the login page.';});</script></html>''',
         cookie=cookie(NONCE, nonce, 600))


def authority(value, *, origin=False):
    """Normalize hostname/default HTTPS port, never equate distinct actual ports."""
    parsed = urlsplit(value if origin else 'https://' + value)
    if (parsed.scheme.lower() != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or any(c.isspace() for c in value)):
        raise ValueError('Invalid origin')
    return parsed.hostname.lower(), parsed.port or 443


def form(handler):
    if authority(handler.headers.get('Origin', ''), origin=True) != authority(handler.headers.get('Host', '')):
        raise ValueError('Invalid origin')
    length = int(handler.headers.get('Content-Length', '0'))
    if not 0 < length <= 8192:
        raise ValueError('Invalid request length')
    return parse_qs(handler.rfile.read(length).decode())


def login(handler):
    if not LOGIN_LOCK.acquire(blocking=False):
        send(handler, 429, 'Another login is in progress. Wait a few seconds.')
        return
    try:
        _login(handler)
    finally:
        LOGIN_LOCK.release()


def _login(handler):
    try:
        data = form(handler)
        nonce = login_nonce(handler)
        submitted = data.get('nonce', [''])[0]
        if nonce is None:
            logging.warning('Dashboard login rejected: missing_or_invalid_nonce_cookie')
            login_page(handler, 'Login cookie missing. Check the cookie notice and enter your password again.')
            return
        if len(submitted) != 64 or not hmac.compare_digest(nonce, submitted):
            logging.warning('Dashboard login rejected: stale_or_mismatched_form')
            login_page(handler, 'This form expired or changed in another tab. Enter your password in the refreshed form.')
            return
        peer = handler.client_address[0]
        with connection() as db:
            row = db.execute('SELECT count,until FROM attempts WHERE peer=?', (peer,)).fetchone()
            if row and row[0] >= 5 and row[1] > time.time():
                send(handler, 429, 'Too many attempts. Wait 15 minutes.')
                return
        password = data.get('password', [''])[0]
        if not 0 < len(password) <= 1024:
            raise ValueError('Invalid password length')
        saved = record()
        correct = hmac.compare_digest(derive(password, bytes.fromhex(saved['salt'])), saved['hash'])
        with connection() as db:
            if not correct:
                now = time.time()
                count = row[0] + 1 if row and row[1] > now else 1
                db.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)', (peer, count, now + 900))
            else:
                raw = secrets.token_hex(32)
                db.execute('DELETE FROM attempts WHERE peer=?', (peer,))
                db.execute('INSERT INTO sessions VALUES(?,?,?,?)',
                           (hashlib.sha256(raw.encode()).hexdigest(), time.time() + LIFETIME,
                            saved['generation'], secrets.token_hex(32)))
        if not correct:
            login_page(handler, 'Incorrect password.')
            return
        send(handler, 303, cookie=cookie(COOKIE, raw, LIFETIME), location='/')
    except (ValueError, UnicodeError):
        logging.warning('Dashboard login rejected: invalid_origin_or_form')
        send(handler, 400, 'Invalid request. <a href="/login">Back to sign in</a>')
    except (KeyError, OSError, sqlite3.Error):
        logging.error('Dashboard login failed: private_config_or_database_unavailable')
        send(handler, 503, 'Cannot verify access. Check the service log.')


def logout(handler):
    try:
        data = form(handler)
        csrf = session(handler)
        if not csrf or not hmac.compare_digest(csrf, data.get('csrf', [''])[0]):
            raise ValueError()
        value = cookies(handler)[COOKIE].value
        with connection() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(value.encode()).hexdigest(),))
        send(handler, 303, cookie=cookie(COOKIE, '', 0), location='/login')
    except (ValueError, KeyError):
        send(handler, 400, 'Invalid request.')


def gate(handler):
    """Return True only for an authenticated request; login/logout are handled here."""
    path = urlsplit(handler.path).path
    if path == '/login/check' and handler.command == 'GET':
        send(handler, 200, json.dumps({'cookie_ready': bool(login_nonce(handler))}), content_type='application/json')
        return False
    if path == '/login':
        login(handler) if handler.command == 'POST' else login_page(handler)
        return False
    if path == '/logout':
        if handler.command == 'POST':
            logout(handler)
        else:
            csrf = session(handler)
            if csrf:
                send(handler, 200, '<form method="post"><input type="hidden" name="csrf" value="' + csrf + '"><button>Sign out</button></form>')
            else:
                send(handler, 303, location='/login')
        return False
    if session(handler):
        return True
    if path.startswith('/api/') or path == '/maintenance/status' or handler.command != 'GET':
        send(handler, 401, 'Session expired. Sign in again.')
    else:
        send(handler, 303, location='/login')
    return False


if __name__ == '__main__':
    import sys
    if sys.argv[1:] != ['password'] or os.geteuid() != 0:
        raise SystemExit('Run as root: python3 dashboard_auth.py password')
    first = getpass.getpass('New dashboard password (at least 12 characters): ')
    second = getpass.getpass('Repeat password: ')
    if first != second:
        raise SystemExit('Passwords do not match. Nothing changed.')
    set_password(first)
    print('Password saved. All previous sessions were revoked.')
