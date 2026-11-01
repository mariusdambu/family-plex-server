#!/usr/bin/env python3
"""Fail closed on private artifacts and known credential material."""
import pathlib
import re
import sys

root = pathlib.Path(__file__).resolve().parents[1]
errors = []
for path in root.rglob('*'):
    if '.git' in path.parts or '__pycache__' in path.parts or path.name == '.DS_Store':
        continue
    if path.is_symlink():
        errors.append(str(path.relative_to(root)) + ': symlink not allowed')
        continue
    if not path.is_file():
        continue
    relative = str(path.relative_to(root))
    if path.stat().st_size > 512 * 1024:
        errors.append(relative + ': unexpected large file')
    if path.suffix.lower() in ('.iso', '.img', '.gz', '.zip', '.pdf', '.db', '.pem', '.key', '.pyc', '.csv', '.log', '.sqlite', '.sqlite3', '.docx', '.p12', '.pfx', '.7z', '.bak'):
        errors.append(relative + ': forbidden artifact')
    if path.name in ('config.json', '.env', 'shadow', 'gshadow', 'known_hosts', 'authorized_keys', 'estado.json', 'sync.log', 'media_sources.json', 'OPERACION_PRIVADA.md'):
        errors.append(relative + ': private filename')
    try:
        text = path.read_text(errors='strict')
    except UnicodeDecodeError:
        errors.append(relative + ': unexpected binary content')
        continue
    # Public examples use reserved documentation addresses and synthetic UUIDs.
    for value in re.findall(r'\b(?:10|172|192)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', text):
        parts = [int(x) for x in value.split('.')]
        if parts[0] == 10 or parts[:2] == [192, 168] or (parts[0] == 172 and 16 <= parts[1] <= 31):
            errors.append(relative + ': private LAN address')
    for value in re.findall(r'\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b', text):
        if not value.startswith('00000000-'):
            errors.append(relative + ': non-example machine identifier')
    if re.search('/' + r'Users/[^/\s]+/', text) or re.search(r'[A-Za-z0-9._%+-]+@(?:gmail|outlook|hotmail)\.[A-Za-z]+', text):
        errors.append(relative + ': personal home path or email')
    patterns = [r'-----BEGIN [A-Z ]*PRIVATE KEY-----', r'gh[pousr]_[A-Za-z0-9]{30,}',
                r'github_pat_[A-Za-z0-9_]{30,}', r'ssh-(?:rsa|ed25519) AAAA[A-Za-z0-9+/]+',
                r'\$[126y]\$[^\s]{20,}']
    for pattern in patterns:
        if re.search(pattern, text):
            errors.append(relative + ': credential-like material')
if errors:
    sys.exit('\n'.join(errors))
print('Publication checks passed: text-only, small files, no recognized credentials')
