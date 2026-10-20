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
    if path.suffix.lower() in ('.iso', '.img', '.gz', '.zip', '.pdf', '.db', '.pem', '.key', '.pyc'):
        errors.append(relative + ': forbidden artifact')
    if path.name in ('config.json', '.env', 'shadow', 'gshadow', 'known_hosts', 'authorized_keys'):
        errors.append(relative + ': private filename')
    try:
        text = path.read_text(errors='strict')
    except UnicodeDecodeError:
        errors.append(relative + ': unexpected binary content')
        continue
    patterns = [r'-----BEGIN [A-Z ]*PRIVATE KEY-----', r'gh[pousr]_[A-Za-z0-9]{30,}',
                r'github_pat_[A-Za-z0-9_]{30,}', r'ssh-(?:rsa|ed25519) AAAA[A-Za-z0-9+/]+',
                r'\$[126y]\$[^\s]{20,}']
    for pattern in patterns:
        if re.search(pattern, text):
            errors.append(relative + ': credential-like material')
if errors:
    sys.exit('\n'.join(errors))
print('Publication checks passed: text-only, small files, no recognized credentials')
