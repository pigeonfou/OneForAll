"""Install one isolated OneForAll application on a fresh LAN host over SSH."""
import getpass
import ipaddress
import json
import re
import shlex
import subprocess
import tarfile
import tempfile
import uuid
from pathlib import Path
from common import APPS, ETC, ROOT
from portal_settings import validate_services


def ssh_target(address, username, port):
    # Reuse the portal's explicit private-network allowlist.
    ip = ipaddress.ip_address(address)
    host = f'[{ip}]' if ip.version == 6 else str(ip)
    validate_services({'cableplan': f'https://{host}/'})
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', username):
        raise ValueError('Compte SSH invalide.')
    if not 1 <= port <= 65535:
        raise ValueError('Port SSH invalide.')
    return f'{username}@{ip}', host


def install_remote(app, configuration):
    address = input('IP privée du serveur Ubuntu distant : ').strip()
    username = input('Compte SSH [ubuntu] : ').strip() or 'ubuntu'
    port = int(input('Port SSH [22] : ').strip() or '22')
    target, host = ssh_target(address, username, port)
    identity = Path(input('Chemin local absolu de la clé privée SSH du serveur : ').strip())
    if not identity.is_absolute() or not identity.is_file():
        raise ValueError('Clé SSH locale introuvable.')
    git_key = ETC / 'git' / (app + '.key')
    known_hosts = Path('/root/.ssh/known_hosts')
    if not git_key.is_file() or not known_hosts.is_file():
        raise ValueError(f'Préparer /etc/oneforall/git/{app}.key et les clés d’hôte GitHub vérifiées avant l’installation distante.')
    password = getpass.getpass(f'Mot de passe admin de {APPS[app]["name"]} (12 caractères minimum) : ')
    if len(password) < 12 or password != getpass.getpass('Confirmer le mot de passe : '):
        raise ValueError('Mot de passe invalide ou confirmation différente.')
    ssh = ['ssh', '-p', str(port), '-i', str(identity), '-o', 'IdentitiesOnly=yes',
           '-o', 'StrictHostKeyChecking=ask', '-o', 'ConnectTimeout=15', target]
    prefix = '' if username == 'root' else 'sudo -n '
    stage = '/var/tmp/oneforall-remote-' + uuid.uuid4().hex
    def command(script, **kwargs):
        return subprocess.run(ssh + [prefix + 'bash -c ' + shlex.quote(script)], check=True, **kwargs)
    # A fresh host only: no takeover of an existing manager or historic app.
    legacy = shlex.quote(APPS[app]['legacy'])
    command(f'''set -e
. /etc/os-release
[ "$ID" = ubuntu ] && {{ [ "$VERSION_ID" = 24.04 ] || [ "$VERSION_ID" = 26.04 ]; }}
[ ! -e /etc/oneforall/site.json ]
[ ! -e {legacy} ]
command -v python3 >/dev/null
command -v tar >/dev/null
mkdir -m 700 {stage}
''')
    try:
        with tempfile.TemporaryDirectory(prefix='ofa-remote-') as directory:
            root = Path(directory)
            config = dict(configuration)
            config.update(lan_ip=address, routing_mode='paths', public_enabled=False, public_apps=[])
            # The trusted LAN source ranges are taken from the central configuration.
            (root / 'site.json').write_text(json.dumps(config))
            (root / 'admin-password').write_text(password)
            (root / 'admin-password').chmod(0o600)
            password = None
            (root / 'git.key').write_bytes(git_key.read_bytes())
            (root / 'known_hosts').write_bytes(known_hosts.read_bytes())
            archive = root / 'payload.tar'
            with tarfile.open(archive, 'w') as tar:
                for path in ROOT.rglob('*'):
                    relative = path.relative_to(ROOT)
                    if path.is_file() and not path.is_symlink() and not any(part.startswith('.') or part == '__pycache__' for part in relative.parts) and relative.parts[0] in {'oneforall', 'config', 'portal', 'install-oneforall.sh'}:
                        tar.add(path, arcname='manager/' + str(relative), recursive=False)
                for name in ('site.json', 'admin-password', 'git.key', 'known_hosts'):
                    tar.add(root / name, arcname=name)
            with archive.open('rb') as stream:
                command(f'tar -xf - -C {stage}', stdin=stream)
            command(f'''set -e
install -d -m 700 /etc/oneforall/git /root/.ssh
install -m 600 {stage}/git.key /etc/oneforall/git/{app}.key
# Add verified GitHub keys without replacing existing SSH host records.
cat {stage}/known_hosts >> /root/.ssh/known_hosts
chmod 600 /root/.ssh/known_hosts
python3 {stage}/manager/oneforall/cli.py configure --config {stage}/site.json
python3 {stage}/manager/oneforall/cli.py bootstrap
python3 /opt/oneforall/manager/oneforall/cli.py install --apps {app} --admin-password-file {stage}/admin-password
''')
            certificate = command('cat ' + shlex.quote(config['certificate']), capture_output=True).stdout
            cert = root / 'server.crt'
            cert.write_bytes(certificate)
            url = f'https://{host}:{config["lan_port"]}/{app}/'
            health = url.rstrip('/') + APPS[app]['health']
            result = subprocess.run(['curl', '--noproxy', '*', '--cacert', str(cert), '--silent', '--show-error', '--max-time', '30', '-o', '/dev/null', '-w', '%{http_code}', health], check=True, capture_output=True, text=True)
            if result.stdout not in ('200', '401' if app == 'cnctolequotation' else '200'):
                raise ValueError('Service installé mais accès LAN non validé : vérifier le pare-feu et les réseaux LAN autorisés.')
            print('Service distant installé et accès LAN vérifié : ' + url)
            print('Le certificat LAN autosigné doit être approuvé sur les postes clients. DocTrad nécessite ensuite ses modèles ; CNC nécessite OpenCascade.')
            return url
    finally:
        command(f'rm -rf -- {stage}')
