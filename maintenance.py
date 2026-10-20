#!/usr/bin/env python3
"""Closed maintenance actions. execute() requires the shared operations lock."""
import datetime as dt
import contextlib
import fcntl
import ipaddress
import json
import os
import pathlib
import secrets
import socket
import sqlite3
import stat
import struct
import subprocess
import time
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen

from configure import COMPOSE, load

STATE = pathlib.Path('/var/lib/family-plex')
LOCK = pathlib.Path('/run/lock/family-plex.lock')
TOKEN = pathlib.Path('/etc/family-plex/plex-token')
ACTIONS = {
    'update_plex': 'Update Plex',
    'update_adguard': 'Update AdGuard',
    'update_OMV': 'Update OMV / system packages',
    'reboot_host': 'Restart server',
}


@contextlib.contextmanager
def db():
    STATE.mkdir(parents=True, mode=0o700, exist_ok=True)
    connection = sqlite3.connect(STATE / 'maintenance.sqlite3', timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA synchronous=FULL')
    connection.execute('''CREATE TABLE IF NOT EXISTS operations (
        id INTEGER PRIMARY KEY, started REAL NOT NULL, finished REAL,
        action TEXT NOT NULL, state TEXT NOT NULL, detail TEXT NOT NULL,
        boot TEXT NOT NULL, pid INTEGER NOT NULL, process_start TEXT NOT NULL
    )''')
    connection.commit()
    (STATE / 'maintenance.sqlite3').chmod(0o600)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def boot_id():
    return pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def process_identity(pid):
    try:
        # Fields after the last ')' start at field 3; starttime is field 22.
        fields = pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return '' if fields[0] == 'Z' else fields[19]
    except (OSError, IndexError):
        return ''


def finish(job, state, detail):
    with db() as connection:
        connection.execute('''UPDATE operations SET state=?,detail=?,finished=?
                              WHERE id=?''', (state, detail, time.time(), job))


def recover():
    """Only reconcile while no CLI operation holds the common lock."""
    with open(LOCK, 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        current = boot_id()
        with db() as connection:
            rows = connection.execute("SELECT * FROM operations WHERE state IN ('running','reboot_requested')").fetchall()
        for row in rows:
            if row['state'] == 'reboot_requested' and row['boot'] != current:
                finish(row['id'], 'success', 'A subsequent host boot was observed; services need separate verification')
            elif row['boot'] == current and process_identity(row['pid']) == row['process_start'] and row['process_start']:
                continue
            elif row['state'] == 'reboot_requested' and time.time() - row['started'] < 120:
                continue
            else:
                finish(row['id'], 'interrupted', 'Executor exited or host restarted before completion; inspect before retrying')


def history():
    with db() as connection:
        return [dict(row) for row in connection.execute('SELECT * FROM operations ORDER BY id DESC LIMIT 20')]


def token():
    info = TOKEN.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise RuntimeError('Plex token must be a root-owned regular file, mode 600')
    value = TOKEN.read_text().strip()
    if not value or '\n' in value or '\r' in value:
        raise RuntimeError('Plex token is missing or invalid')
    return value


def plex_sessions():
    request = Request('http://127.0.0.1:32400/status/sessions',
                      headers={'X-Plex-Token': token(), 'Accept': 'application/xml'})
    with urlopen(request, timeout=4) as response:
        root = ET.fromstring(response.read(2_000_000))
    if root.tag != 'MediaContainer' or 'size' not in root.attrib:
        raise RuntimeError('Unexpected Plex response')
    size = int(root.attrib['size'])
    if size < 0:
        raise RuntimeError('Invalid session count')
    return size


def lock_busy():
    with open(LOCK, 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True


def backup_ready(config):
    root = config['backup_root']
    if not os.path.ismount(root):
        raise RuntimeError('Backup disk must be mounted')
    actual = subprocess.check_output(['findmnt', '-n', '-o', 'UUID', '--target', root], text=True, timeout=4).strip()
    if actual != config['backup_uuid']:
        raise RuntimeError('Unexpected backup disk')
    marker = pathlib.Path(root) / 'family-plex-backup/last-success.json'
    completed = dt.datetime.fromisoformat(json.loads(marker.read_text())['completed_utc'])
    age = (dt.datetime.now(dt.timezone.utc) - completed).total_seconds()
    if not 0 <= age <= 86400:
        raise RuntimeError('A successful backup from the last 24 hours is required')


def preflight(action, *, locked=False, config=None, sessions=None, job=None):
    if action not in ACTIONS:
        return False, 'Unknown action'
    try:
        if not locked and lock_busy():
            return False, 'Another operation holds the shared lock'
        with db() as connection:
            pending = connection.execute("SELECT id FROM operations WHERE state IN ('running','reboot_requested')").fetchall()
        if any(row['id'] != job for row in pending):
            return False, 'A pending operation needs completion or recovery'
        config = config or load()
        count = plex_sessions() if sessions is None else sessions
        if count:
            return False, f'Plex has {count} active session(s), including paused sessions'
        if not os.path.ismount(config['apps_root']):
            return False, 'Application storage is not mounted'
        if action != 'reboot_host':
            backup_ready(config)
        if action in ('update_plex', 'update_adguard') and not COMPOSE.is_file():
            return False, 'Generated Compose file is missing'
        if action == 'update_OMV':
            if not pathlib.Path('/usr/sbin/omv-upgrade').is_file():
                return False, 'Official OMV upgrade tool is unavailable'
            if not config.get('maintenance', {}).get('allow_omv_updates', False):
                return False, 'Enable allow_omv_updates in private configuration after reviewing the update policy'
            version = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', 'openmediavault'], text=True, timeout=4)
            if not version.startswith('8.'):
                return False, 'This update policy supports OMV 8 only'
        return True, 'Ready; checks will be repeated at execution'
    except Exception:
        return False, 'Cannot verify Plex token, configuration or recent backup; action blocked'


def checks():
    recover()
    try:
        config, sessions = load(), plex_sessions()
    except Exception:
        return {key: (False, 'Cannot verify Plex; configure its private token and check availability') for key in ACTIONS}
    return {key: preflight(key, config=config, sessions=sessions) for key in ACTIONS}


def dns_answer_valid(data, ident, question):
    """Validate a small UDP A response, including transaction/question identity."""
    if len(data) < 12:
        return False
    reply, flags, qd, an, _, _ = struct.unpack('!6H', data[:12])
    if reply != ident or not flags & 0x8000 or flags & 0x020f or qd != 1:
        return False
    if data[12:12 + len(question)] != question:
        return False
    offset = 12 + len(question)
    for _ in range(an):
        while True:
            if offset >= len(data):
                return False
            length = data[offset]
            offset += 1
            if length & 0xc0 == 0xc0:
                offset += 1
                break
            if length & 0xc0 or length > 63:
                return False
            if length == 0:
                break
            offset += length
        if offset + 10 > len(data):
            return False
        kind, cls, _, length = struct.unpack('!HHIH', data[offset:offset + 10])
        offset += 10
        value = data[offset:offset + length]
        if len(value) != length:
            return False
        offset += length
        if kind == 1 and cls == 1 and length == 4:
            address = ipaddress.ip_address(value)
            if not address.is_unspecified and not address.is_loopback:
                return True
    return False


def dns_ready(config):
    domain = config.get('maintenance', {}).get('dns_probe', 'example.org')
    labels = domain.rstrip('.').encode('idna').split(b'.')
    if not labels or any(not 0 < len(label) <= 63 for label in labels) or len(domain) > 253:
        raise RuntimeError('Invalid DNS probe name')
    question = b''.join(bytes([len(label)]) + label for label in labels) + b'\0\0\1\0\1'
    ident = secrets.randbelow(65536)
    packet = struct.pack('!6H', ident, 0x100, 1, 0, 0, 0) + question
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(3)
        client.connect((config['server_address'], 53))
        client.send(packet)
        if not dns_answer_valid(client.recv(4096), ident, question):
            raise RuntimeError('DNS probe did not return a usable A answer')


def readiness(action, config):
    container = 'plex' if action == 'update_plex' else 'adguardhome'
    raw = subprocess.check_output(['docker', 'inspect', container], text=True, timeout=5)
    state = json.loads(raw)[0]['State']
    if not state['Running'] or state.get('Health', {}).get('Status', 'healthy') != 'healthy':
        raise RuntimeError('Container is not ready')
    if action == 'update_plex':
        request = Request('http://127.0.0.1:32400/identity', headers={'X-Plex-Token': token()})
    else:
        request = Request(f"http://{config['server_address']}:8080/")
    with urlopen(request, timeout=4) as response:
        if response.status != 200:
            raise RuntimeError('HTTP readiness check failed')
    if action == 'update_adguard':
        dns_ready(config)


def wait_ready(action, config):
    deadline, consecutive = time.monotonic() + 90, 0
    while time.monotonic() < deadline:
        try:
            readiness(action, config)
            consecutive += 1
            if consecutive == 2:
                return
        except Exception:
            consecutive = 0
        time.sleep(2)
    raise RuntimeError('Readiness deadline exceeded')


def command(args, log, lock_fd, timeout=1800, env=None):
    """Children retain the common lock even if the Python executor crashes."""
    process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT,
                               env=env, pass_fds=(lock_fd,), start_new_session=True)
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Do not kill package transactions; inherited lock remains held.
        raise RuntimeError('Command timed out and may still be running; inspect before retrying')
    if code:
        raise RuntimeError('Command failed; inspect the private operation log')


def execute(action, lock_fd):
    if action not in ACTIONS:
        raise ValueError('Unknown action')
    with db() as connection:
        job = connection.execute('''INSERT INTO operations
            (started,action,state,detail,boot,pid,process_start) VALUES(?,?,?,?,?,?,?)''',
            (time.time(), action, 'running', 'Checking prerequisites', boot_id(), os.getpid(), process_identity(os.getpid()))).lastrowid
    state, detail = 'failed', 'Operation failed'
    try:
        config = load()
        allowed, reason = preflight(action, locked=True, config=config, job=job)
        if not allowed:
            state, detail = 'blocked', reason
            return False
        log_path = STATE / f'operation-{job}.log'
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as log:
            if action == 'reboot_host':
                # Persist intent first; a new boot confirms it on dashboard startup.
                finish(job, 'reboot_requested', 'Waiting for a different host boot ID')
                state, detail = 'reboot_requested', 'Waiting for a different host boot ID'
                command(['systemctl', 'reboot', '--no-block'], log, lock_fd, timeout=15)
                return True
            if action == 'update_OMV':
                environment = dict(os.environ)
                environment['OMV_UPGRADE_APT_ARGS'] = '--yes --no-remove --option DPkg::Options::=--force-confold'
                command(['/usr/sbin/omv-upgrade'], log, lock_fd, timeout=7200, env=environment)
                detail = 'OMV upgrade tool completed; services need verification'
                # Package success alone does not demonstrate DNS/playback recovery.
                wait_ready('update_plex', config)
                wait_ready('update_adguard', config)
                detail = 'OMV updates completed; Plex HTTP and AdGuard HTTP/DNS passed'
                if pathlib.Path('/var/run/reboot-required').exists():
                    detail += '; a separate host restart is required'
            else:
                service = 'plex' if action == 'update_plex' else 'adguard'
                base = ['docker', 'compose', '-f', str(COMPOSE)]
                command(base + ['config', '--quiet'], log, lock_fd)
                command(base + ['pull', service], log, lock_fd)
                allowed, reason = preflight(action, locked=True, config=config, job=job)
                if not allowed:
                    state, detail = 'blocked', reason
                    return False
                command(base + ['up', '-d', '--no-deps', service], log, lock_fd)
                wait_ready(action, config)
                detail = 'Configured image applied; HTTP' + (' and DNS' if service == 'adguard' else '') + ' checks passed'
        state = 'success'
        return True
    except Exception:
        state, detail = 'needs_review', f'Operation incomplete; inspect private operation-{job}.log and services before retrying'
        return False
    finally:
        finish(job, state, detail)
