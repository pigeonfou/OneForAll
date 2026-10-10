"""Install one isolated OneForAll application on a fresh LAN host over SSH."""
import getpass
import ipaddress
import json
import os
import shutil
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


class PasswordSSH(list):
    def __init__(self, arguments, password):
        super().__init__(arguments)
        self.password = password

    def run(self, command, **kwargs):
        # A separate inherited pipe supplies SSH authentication; stdin remains
        # available for sudo or the archive. No secret in argv or environment.
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, (self.password + '\n').encode())
            os.close(write_fd)
            write_fd = None
            return subprocess.run(['sshpass', '-d', str(read_fd), *self, command],
                                  pass_fds=(read_fd,), **kwargs)
        finally:
            os.close(read_fd)
            if write_fd is not None:
                os.close(write_fd)


def ssh_run(ssh, command, **kwargs):
    if isinstance(ssh, PasswordSSH):
        return ssh.run(command, **kwargs)
    return subprocess.run(ssh + [command], **kwargs)


def privileged_command(ssh, script, username, sudo_password=None, **kwargs):
    if username == 'root':
        return ssh_run(ssh, 'bash -c ' + shlex.quote(script), check=True, **kwargs)
    if sudo_password is None:
        command = 'sudo -n bash -c ' + shlex.quote(script)
        return ssh_run(ssh, command, check=True, **kwargs)
    # Password occupies stdin only. Drain leftover input for NOPASSWD accounts.
    command = "sudo -k -S -p '' bash -c " + shlex.quote('cat >/dev/null; ' + script)
    return ssh_run(ssh, command, input=(sudo_password + '\n').encode(), check=True, **kwargs)


def application_password(name):
    password = getpass.getpass(f'Mot de passe admin de {name} [password1234] : ') or 'password1234'
    confirmation = getpass.getpass('Confirmer le mot de passe [password1234] : ') or 'password1234'
    if len(password) < 12 or password != confirmation:
        raise ValueError('Mot de passe invalide ou confirmation différente.')
    return password


def install_remote(app, configuration):
    address = input('IP privée du serveur Ubuntu distant : ').strip()
    username = input('Compte SSH [ubuntu] : ').strip() or 'ubuntu'
    port = int(input('Port SSH [22] : ').strip() or '22')
    target, host = ssh_target(address, username, port)
    if not shutil.which('sshpass'):
        subprocess.run(['apt-get', 'install', '-y', 'sshpass'], check=True)
    login_password = getpass.getpass('Mot de passe du compte SSH distant : ')
    if not login_password or len(login_password.encode()) > 1024 or any(c in login_password for c in ('\n', '\r', '\x00')):
        raise ValueError('Mot de passe SSH invalide.')
    git_key = ETC / 'git' / (app + '.key')
    known_hosts = Path('/root/.ssh/known_hosts')
    if not git_key.is_file() or not known_hosts.is_file():
        raise ValueError(f'Préparer /etc/oneforall/git/{app}.key et les clés d’hôte GitHub vérifiées avant l’installation distante.')
    password = application_password(APPS[app]['name'])
    base = ['ssh', '-p', str(port), '-o', 'PubkeyAuthentication=no',
            '-o', 'PreferredAuthentications=password,keyboard-interactive',
            '-o', 'ConnectTimeout=15']
    # Let OpenSSH display/verify a new host key interactively without sending
    # credentials. Authentication failure here is expected; the next call logs in.
    subprocess.run(base + ['-o', 'StrictHostKeyChecking=ask', '-o',
                          'PasswordAuthentication=no', '-o', 'KbdInteractiveAuthentication=no',
                          target, 'true'], check=False)
    ssh = PasswordSSH(base + ['-o', 'StrictHostKeyChecking=yes', target], login_password)
    login_password = None
    sudo_password = None
    if username != 'root':
        sudo_password = getpass.getpass('Mot de passe sudo du serveur distant (vide si sudo sans mot de passe) : ') or None
        if sudo_password and any(c in sudo_password for c in ('\n', '\r', '\x00')):
            raise ValueError('Mot de passe sudo invalide.')
    stage = '/var/tmp/oneforall-remote-' + uuid.uuid4().hex
    def command(script, **kwargs):
        return privileged_command(ssh, script, username, sudo_password, **kwargs)
    # A fresh host only: no takeover of an existing manager or historic app.
    legacy = shlex.quote(APPS[app]['legacy'])
    command(f'''set -e
. /etc/os-release
[ "$ID" = ubuntu ] && {{ [ "$VERSION_ID" = 24.04 ] || [ "$VERSION_ID" = 26.04 ]; }}
[ ! -e /etc/oneforall/site.json ]
[ ! -e {legacy} ]
command -v python3 >/dev/null
command -v tar >/dev/null
true
''')
    ssh_run(ssh, 'umask 077; mkdir ' + shlex.quote(stage), check=True)
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
                ssh_run(ssh, 'umask 077; cat > ' + shlex.quote(stage + '/payload.tar'), stdin=stream, check=True)
            command(f'tar -xf {stage}/payload.tar -C {stage}')
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
        try:
            command('rm -rf -- ' + shlex.quote(stage))
        finally:
            sudo_password = None
            ssh.password = None
