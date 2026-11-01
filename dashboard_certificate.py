"""Root-only renewal helper for an explicitly enabled Tailscale HTTPS deployment."""
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile

TLS = pathlib.Path('/etc/family-plex/tls')


def sync_omv_certificate():
    """Synchronize an explicitly enrolled OMV certificate through its RPC API."""
    marker = TLS / 'omv-certificate-uuid'
    if not marker.exists():
        return
    import uuid
    certificate_id = str(uuid.UUID(marker.read_text().strip()))
    records = json.loads(subprocess.check_output(
        ['omv-confdbadm', 'read', 'conf.system.certificate.ssl'], timeout=15))
    record = next(item for item in records if item['uuid'] == certificate_id)
    certificate = (TLS / 'dashboard.crt').read_text()
    key = (TLS / 'dashboard.key').read_text()
    digest = hashlib.sha256((certificate + key).encode()).hexdigest()
    deployed = TLS / 'omv-deployed-sha256'
    if record['certificate'] == certificate and record['privatekey'] == key and deployed.exists() and deployed.read_text() == digest:
        return
    payload = dict(uuid=certificate_id, certificate=certificate,
                   privatekey=key, comment=record['comment'])
    # Pass key material through stdin, never command-line arguments or logs.
    php = r'''require_once("openmediavault/autoloader.inc");
require_once("openmediavault/globals.inc");
require_once("openmediavault/functions.inc");
$p=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
\OMV\Rpc\Rpc::call("CertificateMgmt","set",$p,
 ["username"=>\OMV\Environment::get("OMV_WEBGUI_ADMINUSER_NAME","admin"),
  "role"=>OMV_ROLE_ADMINISTRATOR], \OMV\Rpc\Rpc::MODE_REMOTE);'''
    subprocess.run(['php', '-c', '/etc/openmediavault', '-r', php],
                   input=json.dumps(payload), text=True, capture_output=True,
                   check=True, timeout=30)
    subprocess.run(['omv-salt', 'deploy', 'run', 'certificates', 'nginx'],
                   check=True, capture_output=True, timeout=180)
    deployed.write_text(digest)
    deployed.chmod(0o600)


def main():
    if os.geteuid() != 0:
        raise SystemExit('Root required')
    domain = (TLS / 'domain').read_text().strip()
    if not domain.endswith('.ts.net') or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789.-' for c in domain):
        raise SystemExit('Invalid certificate hostname')
    TLS.mkdir(mode=0o700, parents=True, exist_ok=True)
    old = hashlib.sha256((TLS / 'dashboard.crt').read_bytes()).hexdigest() if (TLS / 'dashboard.crt').exists() else None
    with tempfile.TemporaryDirectory(prefix='renew-', dir=TLS) as temporary:
        root = pathlib.Path(temporary)
        cert, key = root / 'cert.pem', root / 'key.pem'
        subprocess.run(['tailscale', 'cert', '--min-validity=720h', '--cert-file=' + str(cert),
                        '--key-file=' + str(key), domain], check=True, timeout=180)
        subprocess.run(['openssl', 'x509', '-in', str(cert), '-noout', '-checkhost', domain],
                       check=True, capture_output=True, timeout=5)
        for source, name in [(key, 'dashboard.key'), (cert, 'dashboard.crt')]:
            source.chmod(0o600)
            source.replace(TLS / name)
    current = hashlib.sha256((TLS / 'dashboard.crt').read_bytes()).hexdigest()
    if old is not None and current != old:
        subprocess.run(['systemctl', 'try-restart', 'plexserver-dashboard.service'], check=True, timeout=30)
    # Also retries OMV synchronization after a previous failed deployment.
    sync_omv_certificate()


if __name__ == '__main__':
    main()
