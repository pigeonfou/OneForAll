"""LAN-only portal links; no privileged operations or remote URL fetching."""
import ipaddress
import json
import os
import secrets
import socket
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from common import APPS, VAR

SETTINGS = VAR / 'portal-admin' / 'services.json'
SOCKET = '/run/oneforall-portal/admin.sock'
TOKEN = secrets.token_urlsafe(32)


def validate_services(value):
    if not isinstance(value, dict) or set(value) - APPS.keys():
        raise ValueError('Liste de services invalide.')
    result = {}
    for app, url in value.items():
        if not isinstance(url, str) or len(url) > 2048:
            raise ValueError('Adresse invalide.')
        url = url.strip()
        if not url:
            continue
        try:
            parsed = urlsplit(url)
            address = ipaddress.ip_address(parsed.hostname or '')
            port = parsed.port
        except ValueError:
            raise ValueError('Utilisez une adresse IP privée du LAN, avec http:// ou https://.')
        private = (address.version == 4 and any(address in ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))) or (address.version == 6 and address in ipaddress.ip_network('fc00::/7'))
        if parsed.scheme not in ('http', 'https') or not private or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or (port is not None and not 1 <= port <= 65535) or any(ord(c) < 32 or c in '\\"<>' for c in url):
            raise ValueError('Adresse LAN invalide : aucun identifiant, paramètre ou fragment autorisé.')
        result[app] = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or '/', '', ''))
    return result


def load_services(path=None):
    try:
        return validate_services(json.loads(Path(path or SETTINGS).read_text()))
    except (OSError, ValueError):
        return {}


def save_services(value, path=None):
    value = validate_services(value)
    path = Path(path or SETTINGS)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.services-')
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o640)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return value


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, value):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        return self.path == '/api/settings' and bool(self.headers.get('X-OFA-Admin'))

    def do_GET(self):
        if not self.authorized():
            return self.reply(403, {'error': 'Accès administrateur requis.'})
        self.reply(200, {'services': load_services(), 'token': TOKEN, 'apps': [{'id': app, 'name': spec['name']} for app, spec in APPS.items()]})

    def do_POST(self):
        if not self.authorized():
            return self.reply(403, {'error': 'Accès administrateur requis.'})
        origin = self.headers.get('Origin', '')
        if not origin or origin != self.headers.get('X-OFA-Origin') or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.reply(403, {'error': 'Origine de la requête invalide.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                return self.reply(413, {'error': 'Requête trop volumineuse.'})
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict) or not isinstance(body.get('token'), str) or not secrets.compare_digest(body['token'], TOKEN):
                return self.reply(403, {'error': 'Session expirée. Rechargez la page.'})
            services = save_services(body.get('services'))
            self.reply(200, {'services': services})
        except (ValueError, TypeError):
            self.reply(400, {'error': 'Adresse invalide. Utilisez une IP privée du LAN et un port valide.'})
        except OSError:
            self.reply(503, {'error': 'Enregistrement impossible ; les réglages précédents sont conservés.'})


class Server(HTTPServer):
    address_family = socket.AF_UNIX

    def server_bind(self):
        self.socket.bind(self.server_address)
        os.chmod(self.server_address, 0o660)
        self.server_name = 'localhost'
        self.server_port = 0

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(10)
        return connection, address


if __name__ == '__main__':
    Path(SOCKET).unlink(missing_ok=True)
    Server(SOCKET, Handler).serve_forever()
