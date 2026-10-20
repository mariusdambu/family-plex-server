#!/usr/bin/env python3
"""Private dashboard: SSH tunnel + HTTP Basic authentication + CSRF token."""
import base64
import hmac
import html
import json
import os
import pathlib
import secrets
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from configure import load

CSRF = secrets.token_urlsafe(32)
BUSY = threading.Lock()
RESULT = 'Ready'


class Handler(BaseHTTPRequestHandler):
    def authorized(self):
        expected = 'Basic ' + base64.b64encode(('admin:' + load()['dashboard_token']).encode()).decode()
        if hmac.compare_digest(self.headers.get('Authorization', ''), expected):
            return True
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Family Plex"')
        self.end_headers()
        return False

    def do_GET(self):
        if not self.authorized():
            return
        c = load()
        disk = 'Mounted' if os.path.ismount(c['usb_root']) else 'Unmounted'
        buttons = ''.join(f'<button name="action" value="{action}">{label}</button>' for action, label in [
            ('usb-mount', 'Connect movie USB'), ('usb-eject', 'Eject movie USB'), ('backup', 'Run backup')])
        page = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Family Plex</title>
<style>body{{font:18px system-ui;max-width:48rem;margin:3rem auto;padding:1rem;background:#111820;color:#eee}}button{{padding:1rem;margin:.4rem;cursor:pointer}}pre{{white-space:pre-wrap}}</style>
<h1>Family Plex</h1><p>Movie USB: {disk}</p>
<p>Eject disconnects everyone from the movie USB share and interrupts transfers. Plex restarts briefly. Wait for confirmation before unplugging.</p>
<form method="post"><input type="hidden" name="csrf" value="{CSRF}">{buttons}</form>
<p>Operation: {'Running; refresh for the result' if BUSY.locked() else 'Idle'}</p>
<pre>{html.escape(RESULT)}</pre><p><a href="/">Refresh status</a></p></html>'''
        body = page.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.authorized():
            return
        from urllib.parse import parse_qs
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length < 2048:
                raise ValueError()
            data = parse_qs(self.rfile.read(length).decode())
            action = data.get('action', [''])[0]
            if not hmac.compare_digest(data.get('csrf', [''])[0], CSRF):
                raise ValueError()
            if action not in ('usb-mount', 'usb-eject', 'backup'):
                raise ValueError()
        except (ValueError, UnicodeError):
            self.send_error(400)
            return
        if BUSY.acquire(blocking=False):
            def worker():
                global RESULT
                try:
                    p = subprocess.run(['/usr/bin/python3', str(pathlib.Path(__file__).with_name('ops.py')), action],
                                       capture_output=True, text=True, timeout=15000)
                    RESULT = ('Success\n' if p.returncode == 0 else 'Failed; do not unplug\n') + (p.stdout + p.stderr)[-6000:]
                except Exception as error:
                    RESULT = 'Operation failed: ' + str(error)
                finally:
                    BUSY.release()
            threading.Thread(target=worker, daemon=True).start()
        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    load()
    ThreadingHTTPServer(('127.0.0.1', 8090), Handler).serve_forever()
