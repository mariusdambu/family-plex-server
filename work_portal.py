"""Read-only web project catalogue, separate from SMB filesystem permissions.

Only static web assets inside project directories with a declared HTML entry are served.
There is no upload, directory listing or access to arbitrary NAS files.
"""
import html
import json
import mimetypes
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

ASSETS = {'.html', '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.woff', '.woff2'}
LOGOS = {'.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif'}


def project_entry(project):
    """Default to index.html; private metadata may name another HTML entry file."""
    project = Path(project)
    entry = 'index.html'
    metadata = project / 'portal.json'
    try:
        if metadata.is_file() and not metadata.is_symlink() and metadata.stat().st_size <= 4096:
            value = json.loads(metadata.read_text())
            if isinstance(value, dict):
                entry = value.get('entry', entry)
    except (ValueError, OSError):
        return None
    if (not isinstance(entry, str) or not entry or entry.startswith('.')
            or Path(entry).name != entry or '\\' in entry or not entry.endswith('.html')):
        return None
    target = project / entry
    return entry if target.is_file() and not target.is_symlink() else None


def project_logo(project):
    """Optional private portal.json selects a logo; conventional filenames also work."""
    project = Path(project)
    candidates = []
    metadata = project / 'portal.json'
    try:
        if metadata.is_file() and not metadata.is_symlink() and metadata.stat().st_size <= 4096:
            value = json.loads(metadata.read_text()).get('logo')
            if isinstance(value, str):
                candidates.append(value)
    except (OSError, ValueError, AttributeError):
        pass
    candidates += ['assets/' + stem + ext for stem in ('project-logo', 'logo')
                   for ext in ('.png', '.svg', '.webp', '.jpg')]
    for relative in candidates:
        try:
            target = asset(project.parent, project.name + '/' + relative)
            if target.suffix.lower() in LOGOS:
                return '/work/' + quote(project.name, safe='') + '/' + quote(relative, safe='/')
        except (ValueError, OSError):
            continue
    return None


def project_card(project):
    metadata = {}
    path = project / 'portal.json'
    try:
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= 4096:
            value = json.loads(path.read_text())
            if isinstance(value, dict):
                metadata = value
    except (OSError, ValueError):
        pass
    label = html.escape(str(metadata.get('name', project.name.replace('_', ' '))), quote=True)
    logo = project_logo(project)
    visual = ('<img src="' + html.escape(logo, quote=True) + '" alt="' + label + '" loading="lazy">'
              if logo else '<svg viewBox="0 0 100 80" aria-hidden="true"><path d="M8 20h32l10 10h42v42H8z" fill="#45abd0"/><path d="M8 20V8h30l12 12z" fill="#7bd2ea"/></svg>')
    if not logo and metadata.get('icon') in ('command-bridge', 'autopilot', 'cv'):
        visual = external_icon(metadata['icon'])
    entry = project_entry(project)
    if not entry:
        return ''
    return ('<a class="card" href="/work/' + quote(project.name, safe='') + '/' + quote(entry, safe='') + '" '
            'aria-label="' + label + '" title="' + label + '"><div class="project-logo">' + visual + '</div></a>')


def external_icon(kind):
    """Small original vector marks; no remote image requests or vendor dependencies."""
    if kind == 'command-bridge':
        graphic = '''<rect x="25" y="20" width="106" height="78" rx="12" fill="#e9f5ff" stroke="#157ec5" stroke-width="3"/>
<path d="M55 38h22v22H55zm27 0h22v22H82zM55 65h22v22H55zm27 0h22v22H82z" fill="#159de8"/>
<path d="M65 99v10m-20 0h60" stroke="#157ec5" stroke-width="5" stroke-linecap="round"/>
<rect x="183" y="22" width="106" height="77" rx="13" fill="#f0f1f5" stroke="#526375" stroke-width="3"/>
<path d="M169 100h134l-12 12H181z" fill="#526375"/>
<path d="M222 41h22v38h-22z" fill="#77bdf3"/><path d="M244 41h20v38h-20z" fill="#e2edf8"/>
<path d="M246 42l-4 15 6 8-5 13" fill="none" stroke="#526375" stroke-width="2"/>
<path d="M228 67q13 12 26 0" fill="none" stroke="#526375" stroke-width="2"/>
<path d="M140 50h30m-6-6 6 6-6 6M170 76h-30m6-6-6 6 6 6" fill="none" stroke="#26a69a" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
<text x="160" y="147" text-anchor="middle" fill="#17354d" font-size="25" font-weight="750">Command Bridge</text>'''
    elif kind == 'autopilot':
        graphic = '''<rect x="106" y="12" width="108" height="98" rx="22" fill="#e8f4ff"/>
<path d="M127 32h29v29h-29zm35 0h29v29h-29zM127 67h29v29h-29zm35 0h29v29h-29z" fill="#168de2"/>
<circle cx="208" cy="92" r="22" fill="#178d7a"/><path d="m197 92 8 8 15-16" fill="none" stroke="white" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
<text x="160" y="141" text-anchor="middle" fill="#17354d" font-size="23" font-weight="750">Windows 11 Autopilot</text>
<text x="160" y="165" text-anchor="middle" fill="#526375" font-size="15">Provisioning Guide</text>'''
    else:
        graphic = '''<rect x="113" y="12" width="94" height="106" rx="13" fill="#edf6f6" stroke="#157c7b" stroke-width="3"/>
<circle cx="160" cy="43" r="13" fill="#157c7b"/><path d="M137 75q23-26 46 0" fill="#157c7b"/>
<path d="M135 88h50m-50 13h36" stroke="#6a8f9a" stroke-width="4" stroke-linecap="round"/>
<text x="160" y="149" text-anchor="middle" fill="#17354d" font-size="25" font-weight="750">Curriculum Vitae</text>
<text x="160" y="172" text-anchor="middle" fill="#526375" font-size="16">CV</text>'''
    return '<svg class="external-logo" viewBox="0 0 320 185" aria-hidden="true" style="font-family:system-ui,sans-serif">' + graphic + '</svg>'


def external_cards(root):
    """Read operator-maintained local/external links; keep catalogue JSON private."""
    path = Path(root) / '.portal-links.json'
    try:
        if path.is_symlink() or path.stat().st_size > 65536:
            return ''
        links = json.loads(path.read_text())
        if not isinstance(links, list):
            return ''
    except (OSError, ValueError):
        return ''
    cards = []
    for link in links[:50]:
        if not isinstance(link, dict) or not isinstance(link.get('url'), str):
            continue
        try:
            url = urlsplit(link['url'])
            local = not url.scheme and not url.netloc and url.path.startswith('/work/')
            if local:
                if url.query or url.fragment:
                    continue
                asset(root, unquote(url.path.removeprefix('/work/')))
            elif url.scheme != 'https' or not url.hostname or url.username or url.password:
                continue
        except (ValueError, OSError):
            continue
        label = html.escape(str(link.get('name', url.hostname)), quote=True)
        href = html.escape(link['url'], quote=True)
        attributes = '' if local else ' target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer"'
        cards.append('<a class="card" href="' + href + '"' + attributes + ' aria-label="' + label + '" title="' + label + '">'
                     '<div class="project-logo">' + external_icon(link.get('icon')) + '</div></a>')
    return ''.join(cards)


def asset(root, relative):
    root = Path(root).resolve()
    parts = Path(relative).parts
    if not parts or any(p.startswith('.') or p == '..' for p in parts):
        raise ValueError('Invalid project path')
    current = root
    project_root = None
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Symlinks are not published')
        if current.is_dir():
            if project_entry(current):
                project_root = current
    target = current.resolve()
    if not project_root or root not in target.parents or not target.is_file():
        raise ValueError('Not a published web asset')
    if target.suffix.lower() not in ASSETS and not document_allowed(project_root, target):
        raise ValueError('Not a published web asset')
    return target


def document_allowed(project, target):
    """Only DOCX documents explicitly named in private project metadata are downloadable."""
    if target.suffix.lower() != '.docx':
        return False
    metadata = project / 'portal.json'
    try:
        if metadata.is_symlink() or metadata.stat().st_size > 4096:
            return False
        allowed = json.loads(metadata.read_text()).get('downloads', [])
        return isinstance(allowed, list) and target.relative_to(project).as_posix() in allowed
    except (OSError, ValueError, AttributeError):
        return False


def send(handler, status, body, content_type='text/html; charset=utf-8', download=None):
    if isinstance(body, str):
        body = body.encode()
    handler.send_response(status)
    handler.send_header('Content-Type', content_type)
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('X-Frame-Options', 'SAMEORIGIN')
    if download:
        handler.send_header('Content-Disposition', 'attachment; filename="document.docx"; filename*=UTF-8\'\'' + quote(download, safe=''))
    handler.end_headers()
    handler.wfile.write(body)


def serve(handler, root):
    """Call only after the dashboard's trusted-network check."""
    path = urlsplit(handler.path).path
    if path in ('/work', '/work/'):
        projects = [p for p in sorted(Path(root).iterdir())
                    if p.is_dir() and not p.is_symlink() and not p.name.startswith('.')
                    and project_entry(p)]
        cards = ''.join(project_card(p) for p in projects) + external_cards(root)
        send(handler, 200, '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Work · Family Plex</title>
<style>body{font:16px system-ui;background:#101316;color:#eef3f6;max-width:1100px;margin:auto;padding:24px}
a{color:#90d9b1}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:22px}
.card{display:flex;align-items:center;justify-content:center;background:#fff;border:2px solid transparent;border-radius:18px;padding:20px;text-decoration:none;min-height:170px;transition:transform .15s,border-color .15s,box-shadow .15s}
.project-logo{width:100%;height:150px;display:flex;align-items:center;justify-content:center}
.project-logo img{display:block;max-width:100%;max-height:100%;object-fit:contain}.project-logo svg{width:90px;height:80px}
.project-logo svg.external-logo{width:100%;height:100%}
.card:hover,.card:focus-visible{border-color:#75d58b;transform:translateY(-3px);box-shadow:0 8px 24px #0005;outline:3px solid #75d58b;outline-offset:3px}p{color:#adb8bf}
@media(max-width:480px){body{padding:18px}.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.card{padding:14px;min-height:120px}.project-logo{height:105px}}
@media(prefers-reduced-motion:reduce){.card{transition:none}.card:hover{transform:none}}</style>
<a href="/">← Dashboard</a><h1>Work</h1>
<p>Projects and tools. Folders with index.html appear here automatically.</p>
<div class="grid">''' + (cards or '<p>No web projects yet.</p>') + '</div></html>')
        return
    try:
        relative = unquote(path.removeprefix('/work/'))
        target = asset(root, relative)
        if target.suffix.lower() == '.docx':
            send(handler, 200, target.read_bytes(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', download=target.name)
        else:
            send(handler, 200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
    except (OSError, ValueError):
        send(handler, 404, 'Archivo no publicado.')
