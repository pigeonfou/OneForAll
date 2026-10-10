#!/usr/bin/env python3
import argparse
import contextlib
import fcntl
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from common import APPS, BACKUPS, ETC, OPT, ROOT, VAR, app_env, as_user, atomic, read_json, require_root, run, save_env, services, state, validate_site, write_json
from deploy import backup, complete_deployment, configure_php, install, packages, php_pool, restore
from migrate import import_legacy
from render import nginx


def site():
    c = read_json(ETC / 'site.json')
    if not c:
        raise ValueError('Configurer le site avec configure --config <fichier>.')
    return validate_site(c)


def configure(source):
    candidate = validate_site(read_json(source))
    if not candidate:
        raise ValueError('Configuration absente')
    previous = read_json(ETC / 'site.json')
    changed = candidate.get('routing_mode', 'subdomains') != (previous or {}).get('routing_mode', 'subdomains')
    snapshots = {}
    affected = list(state()) if changed else []
    if affected:
        folder = BACKUPS / ('routing-' + str(time.time_ns()))
        folder.mkdir(parents=True, mode=0o700)
        for app in affected:
            for path in (ETC / 'apps' / (app + '.json'), ETC / 'apps' / (app + '.env'), ETC / (app + '-fpm.conf')):
                if path.exists():
                    snapshots[path] = path.read_text()
                    atomic(folder / path.name, snapshots[path], 0o600)
        if previous:
            write_json(folder / 'site.json', previous)
    write_json(ETC / 'site.json', candidate)
    try:
        for app in affected:
            env = app_env(app)
            base = '/' + app if candidate.get('routing_mode') == 'paths' else '/'
            if app == 'oddworks':
                env['PROJECTFLOW_BASE_PATH'] = base
            elif app == 'cnctolequotation':
                env['CNCTOLE_BASE_PATH'] = base
            elif app in ('cableplan', 'doctrad'):
                env['CABLEPLAN_BASE_PATH' if app == 'cableplan' else 'DOCTRAD_BASE_PATH'] = base
            save_env(app, env)
            if APPS[app]['kind'] == 'php':
                atomic(ETC / (app + '-fpm.conf'), php_pool(app, VAR / app, env), 0o600)
                binary = max(Path('/usr/sbin').glob('php-fpm[0-9]*'), key=lambda p: tuple(map(int, re.findall(r'\d+', p.name))))
                run(binary, '-t', '-y', ETC / (app + '-fpm.conf'))
        if affected:
            run('systemctl', 'restart', *[service for app in affected for service in services(app)])
        if Path('/etc/systemd/system/oneforall-nginx.service').exists():
            reload_front()
    except Exception:
        if previous is not None:
            write_json(ETC / 'site.json', previous)
        for path, content in snapshots.items():
            atomic(path, content, 0o600)
        if affected:
            run('systemctl', 'restart', *[service for app in affected for service in services(app)])
        raise


def reload_front():
    c = site()
    enabled = {a: v for a, v in state().items() if v.get('enabled', True)}
    conf = ETC / 'nginx.conf'
    candidate = ETC / 'nginx.candidate.conf'
    atomic(candidate, nginx(c, enabled))
    run('nginx', '-t', '-c', candidate)
    previous = conf.read_text() if conf.exists() else None
    os.replace(candidate, conf)
    try:
        run('systemctl', 'reload-or-restart', 'oneforall-nginx')
    except Exception:
        if previous is not None:
            atomic(conf, previous)
            run('systemctl', 'restart', 'oneforall-nginx')
        raise


def bootstrap():
    c = site()
    # The common frontend has its own nginx instance and no stock-site includes.
    nginx_existed = shutil.which('nginx') is not None
    if not nginx_existed:
        run('systemctl', 'mask', '--runtime', 'nginx.service')
    try:
        packages('nginx', 'openssl', 'git', 'curl', 'ca-certificates', 'sudo', 'python3', 'python3-venv')
    finally:
        if not nginx_existed:
            run('systemctl', 'unmask', '--runtime', 'nginx.service')
    for p, mode in [(ETC, 0o755), (ETC / 'apps', 0o700), (VAR, 0o755), (BACKUPS, 0o700), (OPT, 0o755)]:
        p.mkdir(parents=True, exist_ok=True); p.chmod(mode)
    for name in ('body', 'proxy', 'fastcgi', 'uwsgi', 'scgi'):
        run('install', '-d', '-m', '0700', '-o', 'www-data', '-g', 'www-data', VAR / 'nginx' / name)
    run('install', '-d', '-m', '0755', VAR / 'public')
    target = OPT / 'manager'
    if ROOT != target:
        # Manager source must not be writable by the CI runner.
        shutil.copytree(ROOT, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns('.git', '__pycache__', '.venv', 'site.json'))
        run('chown', '-R', 'root:root', target)
        run('chmod', '-R', 'go-w', target)
    shutil.copytree(ROOT / 'portal', OPT / 'portal', dirs_exist_ok=True)
    setup_portal_service()
    cert, key = Path(c['certificate']), Path(c['private_key'])
    if cert.exists() != key.exists():
        raise ValueError('Paire certificat/clé incomplète ; fichiers existants conservés.')
    if not cert.exists():
        cert.parent.mkdir(parents=True, exist_ok=True)
        key.parent.mkdir(parents=True, exist_ok=True)
        names = ','.join('DNS:' + sub + '.' + c['domain'] for sub in ('www', *APPS))
        run('openssl', 'req', '-x509', '-newkey', 'rsa:3072', '-nodes', '-days', '365', '-subj', '/CN=www.' + c['domain'], '-addext', 'subjectAltName=' + names + ',IP:' + c['lan_ip'], '-keyout', key, '-out', cert)
        key.chmod(0o600)
    atomic(Path('/etc/systemd/system/oneforall-nginx.service'), '''[Unit]
Description=OneForAll common frontend
After=network-online.target
Wants=network-online.target
[Service]
Type=forking
PIDFile=/run/oneforall-nginx.pid
ExecStartPre=/usr/sbin/nginx -t -c /etc/oneforall/nginx.conf
ExecStart=/usr/sbin/nginx -c /etc/oneforall/nginx.conf
ExecReload=/usr/sbin/nginx -t -c /etc/oneforall/nginx.conf
ExecReload=/bin/kill -HUP $MAINPID
ExecStop=/bin/kill -QUIT $MAINPID
TimeoutStopSec=30
[Install]
WantedBy=multi-user.target
''')
    atomic(Path('/etc/systemd/system/oneforall-status.service'), '''[Unit]
Description=OneForAll local application checks
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/oneforall/manager/oneforall/cli.py status
''')
    atomic(Path('/etc/systemd/system/oneforall-status.timer'), '''[Unit]
Description=Refresh OneForAll availability
[Timer]
OnBootSec=15s
OnUnitActiveSec=30s
[Install]
WantedBy=timers.target
''')
    run('systemctl', 'daemon-reload')
    reload_front()
    run('systemctl', 'enable', '--now', 'oneforall-nginx', 'oneforall-status.timer')
    status()


def setup_portal_service():
    if subprocess.run(['id', 'ofa-portal'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        run('useradd', '--system', '--home-dir', str(VAR / 'portal-admin'), '--shell', '/usr/sbin/nologin', 'ofa-portal')
    run('install', '-d', '-m', '0750', '-o', 'ofa-portal', '-g', 'www-data', VAR / 'portal-admin')
    credentials = ETC / 'portal.htpasswd'
    if not credentials.exists():
        atomic(credentials, '', 0o640)
    run('chown', 'root:www-data', credentials)
    run('chmod', '0640', credentials)
    atomic(Path('/etc/systemd/system/oneforall-portal-admin.service'), '''[Unit]
Description=OneForAll LAN portal administration
After=network.target
[Service]
User=ofa-portal
Group=www-data
ExecStart=/usr/bin/python3 /opt/oneforall/manager/oneforall/portal_settings.py
Restart=on-failure
RuntimeDirectory=oneforall-portal
RuntimeDirectoryMode=0750
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/oneforall/portal-admin
RestrictAddressFamilies=AF_UNIX
[Install]
WantedBy=multi-user.target
''')
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', '--now', 'oneforall-portal-admin')
    run('systemctl', 'restart', 'oneforall-portal-admin')


def portal_admin_account():
    import getpass
    password = getpass.getpass('Mot de passe admin du portail (12 caractères minimum) : ')
    confirmation = getpass.getpass('Confirmer le mot de passe : ')
    if len(password) < 12 or password != confirmation:
        raise ValueError('Mot de passe trop court ou confirmation différente.')
    if not (ETC / 'nginx.conf').exists():
        raise ValueError('Installer le socle avant de créer le compte du portail.')
    hashed = run('openssl', 'passwd', '-6', '-stdin', input=password + '\n', capture=True)
    atomic(ETC / 'portal.htpasswd', 'admin:' + hashed + '\n', 0o640)
    run('chown', 'root:www-data', ETC / 'portal.htpasswd')
    print('Compte admin du portail configuré. Ouvrir Paramètres (admin) depuis le LAN.')


def check(app, c, public=False):
    paths = c.get('routing_mode') == 'paths'
    host = ('www' if paths else app) + '.' + c['domain']
    health_path = ('/' + app if paths else '') + APPS[app]['health']
    if public:
        url = f"http://127.0.0.1:{c['tunnel_port']}{health_path}"
        args = ['-H', 'Host: ' + host]
    else:
        url = f"https://{host}:{c['lan_port']}{health_path}"
        args = ['--resolve', f"{host}:{c['lan_port']}:{c['lan_ip']}", '--cacert', c['certificate']]
    result = subprocess.run(['curl', '--noproxy', '*', '--silent', '--show-error', '--max-time', '8', *args, '-w', '\n%{http_code}', url], capture_output=True, text=True)
    if result.returncode:
        return 'unavailable'
    body, _, code = result.stdout.rpartition('\n')
    if code == '403':
        return 'restricted'
    if app == 'cnctolequotation':
        # Basic challenge proves frontend access only. FPM and DB checked separately below.
        if code != '401':
            return 'unavailable'
        good = all(subprocess.run(['systemctl', 'is-active', '--quiet', s]).returncode == 0 for s in services(app))
        if not good:
            return 'unavailable'
        try:
            details = json.loads(as_user(app, 'php', OPT / 'apps' / app / 'current/packaging/oneforall-health.php', env=app_env(app), capture=True))
        except (ValueError, OSError, subprocess.CalledProcessError):
            return 'unavailable'
        if not details.get('database'):
            return 'unavailable'
        return 'available' if details.get('ready') else 'limited'
    if code != '200':
        return 'unavailable'
    if app in ('cableplan', 'doctrad'):
        try:
            details = json.loads(body)
        except ValueError:
            return 'unavailable'
        if not details.get('database') or not details.get('storage'):
            return 'unavailable'
        if app == 'doctrad' and not details.get('ready'):
            return 'limited'
    return 'available'


def status():
    c = site(); installed = state()
    from portal_settings import load_services
    external = load_services()
    for public in (False, True):
        records = []
        for app, spec in APPS.items():
            if not public and app in external:
                records.append({'id': app, 'name': spec['name'], 'description': spec['description'], 'status': 'external', 'url': external[app]})
                continue
            record = installed.get(app)
            enabled = bool(record and record.get('enabled', True))
            allowed = not public or (c['public_enabled'] and app in c['public_apps'])
            result = check(app, c, public) if enabled and allowed else ('not_installed' if not record else 'restricted')
            suffix = '' if public else ':' + str(c['lan_port'])
            records.append({'id': app, 'name': spec['name'], 'description': spec['description'], 'status': result,
                            'url': (f"https://{('www.' + c['domain']) if public else c['lan_ip']}{suffix}/{app}/" if c.get('routing_mode') == 'paths' else f"https://{app}.{c['domain']}{suffix}/") if enabled and allowed else None})
        write_json(VAR / 'public' / ('status-public.json' if public else 'status-lan.json'), {'checked_at': int(time.time()), 'apps': records, 'admin_enabled': not public}, 0o644)
    print(json.dumps({'installed': list(installed), 'checks': records}, ensure_ascii=False))


def setup_runner():
    if subprocess.run(['id', 'oneforall-runner'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        run('useradd', '--create-home', '--shell', '/bin/bash', 'oneforall-runner')
    # Fixed root-owned program, validated app and SHA; no caller-supplied script/config path.
    atomic(Path('/usr/local/sbin/oneforall-deploy'), '''#!/usr/bin/python3
import os, re, sys
apps = {"cableplan", "doctrad", "oddworks", "cnctolequotation"}
if len(sys.argv) != 3 or sys.argv[1] not in apps or not re.fullmatch("[a-f0-9]{40}", sys.argv[2]):
    raise SystemExit("Usage: oneforall-deploy APP SHA")
os.execve('/usr/bin/python3', ['python3', '/opt/oneforall/manager/oneforall/cli.py', 'update', '--apps', sys.argv[1], '--sha', sys.argv[2]], {'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/root','LANG':'C.UTF-8'})
''', 0o755)
    sudoers = Path('/etc/sudoers.d/oneforall-runner')
    atomic(sudoers, 'oneforall-runner ALL=(root) NOPASSWD: /usr/local/sbin/oneforall-deploy\n', 0o440)
    run('visudo', '-cf', sudoers)
    print('Compte et commande sudo préparés. Enregistrer maintenant le runner dans pigeonfou/OneForAll avec le label oneforall. Procédure : docs/github-cloudflare.md.')


def cloudflare(token_file):
    c = site()
    if not c['public_enabled']:
        raise ValueError('Activer public_enabled explicitement et choisir public_apps avant le tunnel.')
    binary = shutil.which('cloudflared')
    if not binary:
        raise ValueError('cloudflared absent : installer le paquet officiel, puis relancer. Voir docs/github-cloudflare.md.')
    version = re.search(r'(\d{4})\.(\d+)\.(\d+)', run(binary, '--version', capture=True))
    if not version or tuple(map(int, version.groups())) < (2025, 4, 0):
        raise ValueError('cloudflared 2025.4.0 ou ultérieur requis pour --token-file.')
    path = Path(token_file)
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('Le fichier token doit être privé (chmod 600).')
    token = path.read_text().strip()
    if not re.fullmatch('[A-Za-z0-9_=+/-]{20,}', token):
        raise ValueError('Format du token invalide.')
    atomic(ETC / 'cloudflared.token', token + '\n', 0o600)
    atomic(Path('/etc/systemd/system/oneforall-cloudflared.service'), f'''[Unit]
Description=OneForAll dedicated Cloudflare tunnel
After=network-online.target oneforall-nginx.service
Wants=network-online.target
[Service]
ExecStart={binary} --no-autoupdate tunnel run --token-file /etc/oneforall/cloudflared.token
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
''')
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', '--now', 'oneforall-cloudflared')
    print('Tunnel dédié démarré ; les tunnels existants sont conservés. Configurer les hostnames vers http://127.0.0.1:18080 (ou le port tunnel configuré).')


def installation_choices():
    from portal_settings import validate_services
    local, distant = [], {}
    for app, spec in APPS.items():
        while True:
            mode = input(f"{spec['name']} : 1 local, 2 distant déjà installé, 3 ne pas installer, 4 installer via SSH [3] : ").strip() or '3'
            if mode == '1':
                local.append(app)
                break
            if mode == '3':
                break
            if mode == '4':
                from remote_install import install_remote
                distant[app] = install_remote(app, site())
                break
            if mode == '2':
                try:
                    value = validate_services({app: input('URL LAN complète (ex. http://192.168.7.20:8080/) : ')})
                    if app not in value:
                        raise ValueError('Adresse obligatoire pour un service distant.')
                    distant.update(value)
                    break
                except ValueError as exc:
                    print(exc)
            else:
                print('Choisir 1, 2, 3 ou 4.')
    return local, distant


def setup_installation():
    from portal_settings import load_services, save_services, SETTINGS
    if not (ETC / 'site.json').exists():
        main(['configure', '--config', input('Chemin du JSON de configuration réseau : ').strip()])
    local, distant = installation_choices()
    isolated = False
    if any(Path(APPS[app]['legacy']).exists() for app in local):
        if input('Installation historique détectée. Saisir INSTANCE pour créer une instance séparée : ') != 'INSTANCE':
            raise ValueError('Installation annulée ; utiliser l’import historique si nécessaire.')
        isolated = True
    main(['bootstrap'])
    # Preserve choices for skipped services; do not uninstall existing applications.
    with open('/run/lock/oneforall.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Une autre opération OneForAll est en cours.')
        links = load_services()
        for app in local:
            links.pop(app, None)
        links.update(distant)
        save_services(links)
        run('chown', 'ofa-portal:www-data', SETTINGS)
    for app in local:
        args = ['install', '--apps', app]
        if isolated:
            args.append('--isolated')
        temp = ETC / 'admin-password.tmp'
        try:
            if app not in state():
                password = getpass.getpass(f'Mot de passe admin de {APPS[app]["name"]} (12 caractères minimum) : ')
                if len(password) < 12:
                    raise ValueError('Mot de passe : 12 caractères minimum.')
                if password != getpass.getpass('Confirmer le mot de passe : '):
                    raise ValueError('Les mots de passe diffèrent.')
                atomic(temp, password, 0o600)
                args += ['--admin-password-file', str(temp)]
            main(args)
        finally:
            temp.unlink(missing_ok=True)
    main(['status'])
    print('Services distants : liens LAN configurés ; le choix SSH installe les services, le choix adresse seule référence une installation existante. Modifier ces adresses dans Paramètres (admin).')


def interactive():
    print('OneForAll — administration native Ubuntu')
    while True:
        print('''\n1 Diagnostic  2 Installer le socle  3 Installer des applications
4 Configuration réseau  5 Cloudflare Tunnel  6 Préparer GitHub Actions
7 Mettre à jour  8 État / journaux  9 Sauvegarder
10 Restaurer / revenir en arrière  11 Désinstaller (données conservées)  12 Quitter
13 Importer une installation historique  14 Créer un compte admin Python
15 Importer des modèles DocTrad  16 Configurer le Python OpenCascade
17 Configurer le compte admin du portail
18 Installation guidée : services locaux ou distants''')
        choice = input('Choix : ').strip()
        if choice == '12':
            return
        if choice == '18' or (choice == '2' and not (ETC / 'nginx.conf').exists()):
            try:
                setup_installation()
            except (ValueError, subprocess.CalledProcessError, OSError) as exc:
                print('Échec installation guidée :', str(exc))
            continue
        args = {'1':['diagnose'], '2':['bootstrap'], '6':['setup-runner'], '8':['status']}.get(choice)
        if choice in ('3','7','9','11'):
            selected = input('Applications, séparées par virgules (cableplan,doctrad,oddworks,cnctolequotation) : ')
            args = [{'3':'install','7':'update','9':'backup','11':'uninstall'}[choice], '--apps', selected]
            if choice == '3' and any(Path(APPS[app]['legacy']).exists() for app in selected.split(',') if app in APPS):
                print('Installation historique détectée. La nouvelle instance sera séparée ; l’import des données utilise ensuite le choix 13.')
                if input('Saisir INSTANCE pour autoriser cette installation séparée : ') != 'INSTANCE':
                    continue
                args += ['--isolated']
            if choice == '3' and set(selected.split(',')) & {'oddworks','cnctolequotation'}:
                secret = getpass.getpass('Mot de passe admin (12 caractères minimum, conservé uniquement pendant cette installation) : ')
                temp = ETC / 'admin-password.tmp'
                atomic(temp, secret, 0o600)
                args += ['--admin-password-file', str(temp)]
        elif choice == '4':
            args = ['configure','--config',input('Chemin du JSON de configuration : ')]
        elif choice == '5':
            args = ['cloudflare','--token-file',input('Fichier privé contenant le token : ')]
        elif choice == '10':
            app = input('Application : '); snapshot = input('Chemin de sauvegarde : ')
            if input('La restauration remplace les données actuelles. Saisir RESTAURER : ') == 'RESTAURER':
                args = ['restore','--apps',app,'--snapshot',snapshot,'--confirm-restore']
        elif choice == '13':
            app=input('Application à importer : ')
            if input('Les données OneForAll de cette application seront remplacées après sauvegarde. Saisir IMPORTER : ') == 'IMPORTER':
                args=['import-legacy','--apps',app,'--confirm-import']
        elif choice == '14':
            args=['create-admin','--apps',input('Application (cableplan ou doctrad) : ')]
        elif choice == '15':
            args=['import-models','--apps','doctrad','--source',input('Dossier local contenant les modèles vérifiés (id/manifest.json) : ')]
        elif choice == '17':
            args=['portal-admin']
        elif choice == '16':
            args=['configure-geometry','--apps','cnctolequotation','--python',input('Chemin absolu du Python avec OpenCascade : ')]
        if args:
            try:
                main(args)
            except (ValueError, subprocess.CalledProcessError, OSError) as exc:
                print('Échec :', type(exc).__name__, str(exc) if isinstance(exc, ValueError) else 'consulter le diagnostic et les journaux des services')
            finally:
                (ETC / 'admin-password.tmp').unlink(missing_ok=True)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        require_root(); ETC.mkdir(parents=True, exist_ok=True)
        return interactive()
    parser = argparse.ArgumentParser(description='OneForAll — Ubuntu natif')
    parser.add_argument('command', choices=['setup','diagnose','configure','bootstrap','install','update','status','logs','backup','restore','uninstall','setup-runner','cloudflare','create-admin','reset-admin','render','import-legacy','import-models','configure-geometry','portal-admin'])
    parser.add_argument('--apps', default='')
    parser.add_argument('--sha')
    parser.add_argument('--config')
    parser.add_argument('--token-file')
    parser.add_argument('--admin-password-file')
    parser.add_argument('--snapshot')
    parser.add_argument('--confirm-restore', action='store_true')
    parser.add_argument('--isolated', action='store_true')
    parser.add_argument('--confirm-import', action='store_true')
    parser.add_argument('--source')
    parser.add_argument('--python')
    a = parser.parse_args(argv)
    apps = list(dict.fromkeys(part.strip().lower() for part in a.apps.split(',') if part.strip()))
    if any(app not in APPS for app in apps):
        raise ValueError('Application inconnue')
    if a.command == 'render':
        print(nginx(validate_site(read_json(a.config)), {app: {} for app in apps}))
        return
    if a.command == 'diagnose':
        print(Path('/etc/os-release').read_text())
        for command in (['ss','-lnt'], ['systemctl','--failed','--no-pager'], ['df','-h','/']):
            subprocess.run(command, check=False)
        print('Installations historiques :', {app:Path(spec['legacy']).exists() for app,spec in APPS.items()})
        return
    require_root()
    if a.command == 'setup':
        return setup_installation()
    if a.command in ('install','update','backup','restore','uninstall','logs','create-admin','reset-admin','import-legacy','import-models','configure-geometry') and not apps:
        raise ValueError('--apps est requis')
    if a.command in ('restore','create-admin','import-legacy','import-models','configure-geometry') and len(apps) != 1:
        raise ValueError('Sélectionner une seule application')
    if a.sha and len(apps) != 1:
        raise ValueError('--sha exige une seule application')
    with open('/run/lock/oneforall.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Une autre opération OneForAll est en cours.')
        if a.command == 'configure':
            if not a.config: raise ValueError('--config requis')
            configure(a.config)
        elif a.command == 'bootstrap': bootstrap()
        elif a.command == 'portal-admin': portal_admin_account()
        elif a.command in ('install','update'):
            site()
            if not (ETC / 'nginx.conf').exists(): raise ValueError('Installer le socle avant les applications.')
            password = None
            if a.admin_password_file:
                file = Path(a.admin_password_file)
                if file.stat().st_mode & 0o077: raise ValueError('chmod 600 requis pour le fichier mot de passe')
                password = file.read_text().rstrip('\n')
                if len(password) < 12: raise ValueError('Mot de passe : 12 caractères minimum')
            for app in apps:
                if a.command == 'update' and app not in state(): raise ValueError('Installer initialement cette application via le menu.')
                install(app, a.sha, password, a.isolated)
                reload_front()
                c = site()
                for attempt in range(15):
                    result = check(app,c)
                    if result in ('available','limited'): break
                    time.sleep(2)
                else:
                    run('systemctl', 'stop', *services(app))
                    raise ValueError(f'{app} : contrôle HTTP échoué. Consulter status/logs ; sauvegarde conservée pour restauration.')
                complete_deployment(app)
            status()
        elif a.command == 'status': status()
        elif a.command == 'logs':
            run('journalctl', *[x for app in apps for s in services(app) for x in ('-u',s)], '-n','100','--no-pager')
        elif a.command == 'backup':
            for app in apps: print(backup(app))
        elif a.command == 'restore':
            if not a.confirm_restore or not a.snapshot: raise ValueError('--snapshot et --confirm-restore requis')
            restore(apps[0], a.snapshot); reload_front(); status()
        elif a.command == 'uninstall':
            s = state()
            for app in apps:
                backup(app)
                run('systemctl','disable','--now',*services(app))
                s[app]['enabled'] = False
            write_json(VAR / 'state.json',s); reload_front(); status()
            print('Services désactivés et accès retirés. Données, versions et sauvegardes conservées.')
        elif a.command == 'setup-runner': setup_runner()
        elif a.command == 'import-legacy':
            if not a.confirm_import: raise ValueError('--confirm-import requis après examen des sauvegardes.')
            import_legacy(apps[0]); reload_front(); status()
        elif a.command == 'configure-geometry':
            if apps != ['cnctolequotation'] or not a.python or not re.fullmatch(r'/opt/[a-zA-Z0-9_./-]+',a.python):
                raise ValueError('Choisir cnctolequotation et un Python installé sous /opt.')
            if 'cnctolequotation' not in state(): raise ValueError('Installer CNCToleQuotation avant cette configuration.')
            as_user('cnctolequotation',a.python,'-c','from OCC.Core.STEPControl import STEPControl_Reader; print("OpenCascade OK")')
            backup('cnctolequotation',restart=False)
            values=app_env('cnctolequotation'); values['CNCTOLE_GEOMETRY_PYTHON']=a.python
            from common import save_env
            save_env('cnctolequotation',values)
            configure_php('cnctolequotation',OPT/'apps/cnctolequotation/current')
            run('systemctl','restart',*services('cnctolequotation')); status()
        elif a.command == 'import-models':
            if apps != ['doctrad'] or not a.source or not Path(a.source).is_dir(): raise ValueError('Dossier local de modèles DocTrad requis.')
            if 'doctrad' not in state(): raise ValueError('Installer DocTrad avant l’import des modèles.')
            import secrets
            target=VAR/'doctrad/models'
            staged=VAR/('doctrad-models-'+secrets.token_hex(5))
            shutil.copytree(a.source,staged)
            run('chown','-R','ofa-doctrad:ofa-doctrad',staged)
            executable=OPT/'apps/doctrad/current/.venv/bin/python'
            code='import sys; from app.registry import Registry; items=Registry(sys.argv[1]).list(); assert items and all(m["status"]=="ready" for m in items), "Modèles non vérifiés"; print("Modèles vérifiés")'
            as_user('doctrad',executable,'-c',code,staged,env=app_env('doctrad'))
            backup('doctrad',restart=False)
            previous=VAR/('doctrad-models-before-'+secrets.token_hex(5))
            target.rename(previous); staged.rename(target)
            run('systemctl','start',*services('doctrad')); status()
        elif a.command == 'cloudflare':
            if not a.token_file: raise ValueError('--token-file requis')
            cloudflare(a.token_file)
        elif a.command == 'reset-admin':
            name = input('Identifiant administrateur [admin] : ').strip() or 'admin'
            password = getpass.getpass('Nouveau mot de passe (12 caractères minimum) : ')
            if len(password) < 12: raise ValueError('12 caractères minimum requis')
            if password != getpass.getpass('Confirmer le nouveau mot de passe : '): raise ValueError('Les mots de passe diffèrent')
            for app in apps:
                if app not in state(): raise ValueError('Application non installée : ' + app)
                if app not in ('cableplan','doctrad','oddworks'): raise ValueError('Application non prise en charge')
            from admin import set_admin
            for app in apps:
                backup(app)
                set_admin(app, name, password)
                print(app + ' : compte ' + name + ' configuré.')
        elif a.command == 'create-admin':
            app=apps[0]
            if app not in ('cableplan','doctrad'): raise ValueError('Les applications PHP ont un compte admin initial configuré pendant l’installation.')
            name=input('Identifiant : ')
            args=['create-user',name]+(['--admin'] if app=='doctrad' else [])
            executable='cableplan' if app=='cableplan' else 'docutranslate'
            as_user(app, OPT/'apps'/app/'current/.venv/bin'/executable,*args,env=app_env(app))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, subprocess.CalledProcessError, OSError) as error:
        print('ÉCHEC : ' + (str(error) if isinstance(error, ValueError) else type(error).__name__ + ' — consulter les journaux ; opération non validée.'), file=sys.stderr)
        raise SystemExit(1)
