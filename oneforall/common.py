import ipaddress
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ETC = Path('/etc/oneforall')
VAR = Path('/var/lib/oneforall')
OPT = Path('/opt/oneforall')
BACKUPS = Path('/var/backups/oneforall')
APPS = json.loads((ROOT / 'config/apps.json').read_text())


def run(*args, capture=False, input=None, env=None):
    # Never echo arguments: some programs receive secret material via stdin/env.
    result = subprocess.run([str(a) for a in args], check=True, text=True,
                            stdout=subprocess.PIPE if capture else None,
                            input=input, env=env)
    return result.stdout.strip() if capture else ''


def atomic(path, content, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.new')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)
    tmp.chmod(mode)
    os.replace(tmp, path)


def write_json(path, value, mode=0o600):
    atomic(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n', mode)


def read_json(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


def validate_site(c):
    if c.get("routing_mode", "subdomains") not in ("subdomains", "paths"):
        raise ValueError("Mode de routage invalide")
    domain = c.get('domain', '')
    if not re.fullmatch(r'(?=.{1,190}$)[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?', domain) or '.' not in domain or '..' in domain:
        raise ValueError('Domaine DNS invalide')
    ip = ipaddress.ip_address(c['lan_ip'])
    if ip.version != 4 or not ip.is_private or ip.is_loopback or ip.is_unspecified:
        raise ValueError('Adresse LAN IPv4 privée requise')
    for key in ('lan_port', 'tunnel_port'):
        if type(c[key]) is not int or not 1024 <= c[key] <= 65535:
            raise ValueError('Port invalide (1024–65535)')
    if c['lan_port'] == c['tunnel_port']:
        raise ValueError('Ports identiques')
    if type(c['public_enabled']) is not bool or not isinstance(c['public_apps'], list):
        raise ValueError('Exposition publique invalide')
    if set(c['public_apps']) - APPS.keys():
        raise ValueError('Application publique inconnue')
    if not c['lan_networks']:
        raise ValueError('Au moins un réseau LAN est requis')
    for net in c['lan_networks']:
        n = ipaddress.ip_network(net)
        if n.version != 4 or not n.is_private or n.prefixlen < 8:
            raise ValueError('Réseau LAN privé explicite requis')
    for key in ('certificate', 'private_key'):
        if not re.fullmatch(r'/[a-zA-Z0-9_./-]+', c[key]) or '..' in Path(c[key]).parts:
            raise ValueError('Chemin TLS invalide')
    return c


def state():
    return read_json(VAR / 'state.json', {})


def services(app):
    return ['oneforall-' + app + '-' + name for name in APPS[app]['services']]


def user(app):
    return 'ofa-' + app


def as_user(app, *args, env=None, capture=False):
    values = dict(env or {})
    if os.environ.get("TMPDIR") and "TMPDIR" not in values:
        values["TMPDIR"] = os.environ["TMPDIR"]
    return run('runuser', '-u', user(app), '--', 'env', *[f'{k}={v}' for k, v in values.items()],
               *args, capture=capture)


def app_env(app):
    return read_json(ETC / 'apps' / (app + '.json'), {})


def save_env(app, values):
    if any('\n' in str(v) or '"' in str(v) or '\\' in str(v) for v in values.values()):
        raise ValueError('Valeur de configuration non prise en charge')
    write_json(ETC / 'apps' / (app + '.json'), values)
    atomic(ETC / 'apps' / (app + '.env'), ''.join(f'{k}="{v}"\n' for k, v in values.items()), 0o600)


def require_root():
    if os.geteuid() != 0:
        raise ValueError('Exécuter avec sudo.')
    info = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if info.get('ID', '').strip('"') != 'ubuntu' or info.get('VERSION_ID', '').strip('"') not in ('24.04', '26.04'):
        raise ValueError('Ubuntu 24.04 ou 26.04 requis ; validation sur serveur nécessaire.')
