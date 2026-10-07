import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tarfile
import time
from pathlib import Path

from common import APPS, BACKUPS, ETC, OPT, ROOT, VAR, app_env, as_user, atomic, read_json, run, save_env, services, state, user, write_json


def packages(*names):
    run('apt-get', 'update', '-qq')
    run('apt-get', 'install', '-y', '--no-install-recommends', *names)


def ensure_user(app):
    if subprocess.run(['id', user(app)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        run('useradd', '--system', '--home-dir', str(VAR / app), '--shell', '/usr/sbin/nologin', user(app))
    run('install', '-d', '-m', '0750', '-o', user(app), '-g', user(app), VAR / app)
    run('install', '-d', '-m', '0755', OPT / 'apps' / app / 'releases')


def unit(app, name, command, group=None):
    current = OPT / 'apps' / app / 'current'
    runtime = f'oneforall-{app}'
    atomic(Path('/etc/systemd/system') / f'oneforall-{app}-{name}.service', f'''[Unit]
Description=OneForAll {app} {name}
After=network.target postgresql.service mariadb.service
[Service]
User={user(app)}
Group={group or user(app)}
WorkingDirectory={current}
EnvironmentFile=/etc/oneforall/apps/{app}.env
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONNOUSERSITE=1
ExecStart={command}
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={VAR / app}
RuntimeDirectory={runtime}
RuntimeDirectoryMode=0750
UMask=0007
[Install]
WantedBy=multi-user.target
''')


def prepare_release(app, sha=None):
    spec = APPS[app]
    mirror = OPT / 'sources' / (app + '.git')
    mirror.parent.mkdir(parents=True, exist_ok=True)
    if not mirror.exists():
        key = ETC / 'git' / (app + '.key')
        if key.exists():
            ssh = f'ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes'
            run('git', 'clone', '--mirror', '-c', 'core.sshCommand=' + ssh,
                f"ssh://git@ssh.github.com:443/{spec['repo']}.git", mirror)
        else:
            run('git', 'clone', '--mirror', f"https://github.com/{spec['repo']}.git", mirror)
    run('git', '--git-dir', mirror, 'fetch', '--prune', 'origin', f"+refs/heads/{spec['ref']}:refs/heads/{spec['ref']}")
    head = run('git', '--git-dir', mirror, 'rev-parse', f"refs/heads/{spec['ref']}^{{commit}}", capture=True)
    if sha and (not re.fullmatch('[a-f0-9]{40}', sha) or sha != head):
        raise ValueError('Le SHA demandé doit être exactement la tête de la branche approuvée AllFortOne.')
    sha = head
    release = OPT / 'apps' / app / 'releases' / sha
    if (release / '.ready').exists():
        return release, sha
    if release.exists():
        # Only a known, incomplete immutable SHA directory is rebuilt.
        shutil.rmtree(release)
    release.mkdir(parents=True)
    archive = mirror.parent / (app + '.tar')
    run('git', '--git-dir', mirror, 'archive', '--format=tar', '-o', archive, sha)
    with tarfile.open(archive) as tar:
        tar.extractall(release, filter='data')
    archive.unlink()
    descriptor = read_json(release / 'packaging/oneforall.json')
    if not descriptor or descriptor.get('id') != app or descriptor.get('version') != 1:
        raise ValueError('Adaptateur OneForAll version 1 absent : utiliser la branche AllFortOne.')
    run('chown', '-R', user(app) + ':' + user(app), release)
    if spec['kind'] == 'python':
        packages('python3-venv', 'build-essential', 'libpq-dev', 'fonts-dejavu-core', 'curl')
        if app == 'doctrad':
            packages('postgresql', 'tesseract-ocr', 'tesseract-ocr-eng', 'poppler-utils')
        as_user(app, 'python3', '-m', 'venv', release / '.venv')
        pip = release / '.venv/bin/pip'
        temp = Path('/var/tmp') / ('oneforall-' + app + '-install')
        run('install', '-d', '-m', '0700', '-o', user(app), '-g', user(app), temp)
        pip_env = {'TMPDIR': str(temp)}
        if app == 'doctrad':
            # Existing lock is authoritative. Failure leaves the active version unchanged.
            as_user(app, pip, 'install', '-r', release / 'requirements.lock', env=pip_env)
        as_user(app, pip, 'install', release, env=pip_env)
        as_user(app, release / '.venv/bin/python', '-m', 'pip', 'check')
    else:
        packages('php-fpm', 'php-cli', 'php-sqlite3', 'php-mysql', 'php-curl', 'php-mbstring', 'php-xml', 'php-zip')
        if app == 'cnctolequotation':
            packages('mariadb-server', 'mariadb-client', 'python3-venv', 'libgomp1')
            as_user(app, 'python3', '-m', 'venv', release / '.venv')
            as_user(app, release / '.venv/bin/pip', 'install', 'numpy', 'pandas', 'scikit-learn', 'lightgbm', 'joblib', 'scipy')
    atomic(release / '.ready', sha + '\n')
    run('chown', '-R', 'root:root', release)
    run('chmod', '-R', 'a-w', release)
    return release, sha


def configure_python(app, release, sha):
    env = app_env(app)
    new = not env
    data = VAR / app
    current = OPT / 'apps' / app / 'current'
    paths = read_json(ETC / 'site.json', {}).get('routing_mode') == 'paths'
    env['CABLEPLAN_BASE_PATH' if app == 'cableplan' else 'DOCTRAD_BASE_PATH'] = '/' + app if paths else '/'
    if app == 'cableplan':
        env.update(CABLEPLAN_DATA=str(data), CABLEPLAN_COMMIT=sha, CABLEPLAN_PROXY_MODE='nginx', CABLEPLAN_TUNNEL_CONFIGURED='oneforall')
        unit(app, 'web', f'{current}/.venv/bin/cableplan serve --uds /run/oneforall-cableplan/app.sock', 'www-data')
        service = Path('/etc/systemd/system/oneforall-cableplan-web.service')
        atomic(service, service.read_text().replace('NoNewPrivileges=true', 'IPAddressDeny=any\nIPAddressAllow=localhost\nNoNewPrivileges=true'))
    else:
        if new:
            env = dict(DATABASE_URL=f'postgresql+psycopg://ofa_doctrad:{secrets.token_hex(32)}@127.0.0.1/ofa_doctrad',
                       SESSION_SECRET=secrets.token_hex(32), RUNTIME_SECRET=secrets.token_hex(32),
                       COOKIE_SECURE='true', OFFLINE_MODE='true', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                       HF_DATASETS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', DATA_ROOT=str(data),
                       MODEL_ROOT=str(data / 'models'), RUNTIME_URL='http://127.0.0.1:18112')
            save_env(app, env)  # Persist before provisioning: interrupted install reuses credentials.
        for name in ('models', 'uploads', 'outputs', 'temp'):
            run('install', '-d', '-m', '0750', '-o', user(app), '-g', user(app), data / name)
        run('systemctl', 'enable', '--now', 'postgresql')
        password = env['DATABASE_URL'].split(':', 2)[2].split('@')[0]
        exists = run('runuser', '-u', 'postgres', '--', 'psql', '-Atc', "SELECT 1 FROM pg_roles WHERE rolname='ofa_doctrad'", capture=True)
        if not exists:
            run('runuser', '-u', 'postgres', '--', 'psql', '-v', 'ON_ERROR_STOP=1', input=f"CREATE USER ofa_doctrad PASSWORD '{password}';\n")
        exists = run('runuser', '-u', 'postgres', '--', 'psql', '-Atc', "SELECT 1 FROM pg_database WHERE datname='ofa_doctrad'", capture=True)
        if not exists:
            run('runuser', '-u', 'postgres', '--', 'createdb', '-O', 'ofa_doctrad', 'ofa_doctrad')
        unit(app, 'web', f'{current}/.venv/bin/uvicorn app.web:app --host 127.0.0.1 --port 18102 --no-access-log')
        unit(app, 'runtime', f'{current}/.venv/bin/uvicorn app.runtime:app --host 127.0.0.1 --port 18112 --no-access-log')
        unit(app, 'worker', f'{current}/.venv/bin/python -m app.worker')
    env['CABLEPLAN_BASE_PATH' if app == 'cableplan' else 'DOCTRAD_BASE_PATH'] = '/' + app if paths else '/'
    save_env(app, env)
    executable = 'cableplan' if app == 'cableplan' else 'docutranslate'
    as_user(app, release / '.venv/bin' / executable, 'migrate', env=env)


def php_pool(app, data, env):
    runtime = f'/run/oneforall-{app}'
    pool = f'''[global]
pid = {runtime}/master.pid
error_log = /var/log/oneforall-{app}-php.log
[oneforall]
user = {user(app)}
group = {user(app)}
listen = {runtime}/php.sock
listen.owner = www-data
listen.group = www-data
listen.mode = 0660
pm = ondemand
pm.max_children = 8
clear_env = yes
catch_workers_output = yes
php_admin_value[session.name] = OFA_{app}
php_admin_value[session.cookie_path] = {env.get("PROJECTFLOW_BASE_PATH", env.get("CNCTOLE_BASE_PATH", "/")) or "/"}
php_admin_value[session.cookie_httponly] = 1
php_admin_value[session.cookie_secure] = 1
php_admin_value[session.cookie_samesite] = Lax
php_admin_value[session.save_path] = {data}/sessions
php_admin_value[upload_max_filesize] = {'55M' if app == 'cnctolequotation' else '0'}
php_admin_value[post_max_size] = {'60M' if app == 'cnctolequotation' else '0'}
php_admin_value[max_execution_time] = {'300' if app == 'cnctolequotation' else '0'}
'''
    pool += ''.join(f'env[{k}] = "{v}"\n' for k, v in env.items())
    return pool


def configure_php(app, release, admin_password=None):
    data = VAR / app
    current = OPT / 'apps' / app / 'current'
    env = app_env(app)
    if app == 'oddworks':
        # PHP-FPM rejects empty env values; '/' is normalized to '' by config.php.
        env.update(PROJECTFLOW_DB_PATH=str(data / 'database.sqlite'), PROJECTFLOW_BASE_PATH='/oddworks' if read_json(ETC / 'site.json', {}).get('routing_mode') == 'paths' else '/')
        if not (data / 'database.sqlite').exists():
            if not admin_password:
                raise ValueError('Mot de passe administrateur requis (--admin-password-file).')
            as_user(app, 'php', release / 'install/init_database.php', env={**env, 'PROJECTFLOW_ADMIN_PASSWORD': admin_password})
    else:
        if not env:
            env = {'CNCTOLE_CONFIG': str(ETC / 'cnctolequotation.php'), 'CNCTOLE_MODELS_DIR': str(data / 'models'),
                   'CNCTOLE_DB_PASSWORD': secrets.token_hex(32)}
            save_env(app, env)
        env['CNCTOLE_ALLOW_FALLBACK'] = '0'
        env['CNCTOLE_BASE_PATH'] = '/cnctolequotation' if read_json(ETC / 'site.json', {}).get('routing_mode') == 'paths' else '/'
        for name in ('models', 'uploads', 'logs', 'tmp', 'history'):
            run('install', '-d', '-m', '0750', '-o', user(app), '-g', user(app), data / name)
        run('systemctl', 'enable', '--now', 'mariadb')
        exists = run('mariadb', '-Nse', "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='ofa_cnctolequotation'", capture=True)
        if exists == '0':
            run('mariadb', input=f"CREATE DATABASE ofa_cnctolequotation; CREATE USER IF NOT EXISTS 'ofa_cnctole'@'localhost' IDENTIFIED BY '{env['CNCTOLE_DB_PASSWORD']}'; GRANT ALL ON ofa_cnctolequotation.* TO 'ofa_cnctole'@'localhost';")
        if not (data / '.schema-ready').exists():
            sql = (release / 'sql/schema.sql').read_text().replace('cnctolequotation', 'ofa_cnctolequotation')
            # Initial demo token must never become usable on a shared server.
            sql = sql.replace("SHA2('demo-token-change-me', 256), 1", "SHA2('demo-token-change-me', 256), 0")
            # Re-entering an interrupted initial schema does not duplicate seed rows.
            sql = sql.replace('INSERT INTO config ', 'INSERT IGNORE INTO config ').replace('INSERT INTO api_tokens ', 'INSERT IGNORE INTO api_tokens ')
            match = re.search(r'INSERT INTO materials (\([^;]+?\)) VALUES\s*(.*?);', sql, re.S)
            if match:
                rows = re.findall(r"\('([^']+)'[^\n]+?\)(?=,|$)", match.group(2).strip(), re.M)
                statements = []
                for row in re.findall(r"\('[^\n]+?\)(?=,|$)", match.group(2).strip(), re.M):
                    code = row.split("'", 2)[1]
                    statements.append('INSERT INTO materials ' + match.group(1) + ' SELECT ' + row[1:-1] + " WHERE NOT EXISTS (SELECT 1 FROM materials WHERE code='" + code + "');")
                if len(statements) != 9:
                    raise ValueError('Schéma CNC modifié : adapter la migration avant installation.')
                sql = sql[:match.start()] + '\n'.join(statements) + sql[match.end():]
            run('mariadb', input=sql)
            atomic(data / '.schema-ready', '1\n', 0o600)
        php = f'''<?php
return ['db'=>['host'=>'localhost','port'=>3306,'name'=>'ofa_cnctolequotation','user'=>'ofa_cnctole','password'=>'{env['CNCTOLE_DB_PASSWORD']}','charset'=>'utf8mb4'],
'paths'=>['root'=>'{current}','uploads'=>'{data}/uploads','models'=>'{data}/models','logs'=>'{data}/logs','tmp'=>'{data}/tmp','python'=>'{current}/.venv/bin/python','geometry_python'=>'{env.get('CNCTOLE_GEOMETRY_PYTHON', str(current / '.venv/bin/python'))}','geometry'=>'{current}/core/geometry/analyze.py','predict'=>'{current}/core/ml/predict.py'],
'security'=>['max_upload_mb'=>50,'allowed_ext'=>['step','stp','iges','igs']]];
'''
        atomic(ETC / 'cnctolequotation.php', php, 0o640)
        run('chown', 'root:' + user(app), ETC / 'cnctolequotation.php')
        if not (ETC / 'cnc.htpasswd').exists():
            if not admin_password:
                raise ValueError('Mot de passe administrateur CNC requis.')
            hashed = run('openssl', 'passwd', '-6', '-stdin', input=admin_password + '\n', capture=True)
            atomic(ETC / 'cnc.htpasswd', 'admin:' + hashed + '\n', 0o640)
            run('chown', 'root:www-data', ETC / 'cnc.htpasswd')
        if not (data / 'models/active_model.txt').exists():
            as_user(app, release / '.venv/bin/python', release / 'core/ml/create_initial_model.py', env=env)
            atomic(data / 'models/active_model.txt', 'v0.1.0\n', 0o640)
            run('chown', user(app) + ':' + user(app), data / 'models/active_model.txt')
    save_env(app, env)
    binaries = list(Path('/usr/sbin').glob('php-fpm[0-9]*'))
    if not binaries:
        raise ValueError('PHP-FPM absent')
    binary = max(binaries, key=lambda p: tuple(int(n) for n in re.findall(r'\d+', p.name)))
    runtime = f'/run/oneforall-{app}'
    # Root FPM master drops each pool to its own application user.
    pool = php_pool(app, data, env)
    run('install', '-d', '-m', '0700', '-o', user(app), '-g', user(app), data / 'sessions')
    atomic(ETC / (app + '-fpm.conf'), pool, 0o600)
    run(binary, '-t', '-y', ETC / (app + '-fpm.conf'))
    unit(app, 'web', f'{binary} -F -y {ETC}/{app}-fpm.conf')
    path = Path('/etc/systemd/system') / f'oneforall-{app}-web.service'
    content = path.read_text().replace(f'User={user(app)}\nGroup={user(app)}', 'User=root\nGroup=root').replace('ReadWritePaths=' + str(data), 'ReadWritePaths=' + str(data) + ' /var/log').replace('RuntimeDirectoryMode=0750', 'RuntimeDirectoryMode=0755')
    atomic(path, content)


def backup(app, restart=True):
    record = state().get(app)
    if not record:
        raise ValueError('Application non installée.')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(3)
    target = BACKUPS / app / stamp
    target.mkdir(parents=True, mode=0o700)
    active = [s for s in services(app) if subprocess.run(['systemctl', 'is-active', '--quiet', s]).returncode == 0]
    run('systemctl', 'stop', *services(app))
    try:
        with tarfile.open(target / 'data.tar', 'w') as tar:
            tar.add(VAR / app, arcname=app)
        write_json(target / 'record.json', record)
        shutil.copy2(ETC / 'apps' / (app + '.json'), target / 'env.json')
        if app == 'doctrad':
            with open(target / 'database.dump', 'wb') as f:
                subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_dump', '-Fc', 'ofa_doctrad'], stdout=f, check=True)
        elif app == 'cnctolequotation':
            with open(target / 'database.sql', 'wb') as f:
                subprocess.run(['mariadb-dump', '--single-transaction', 'ofa_cnctolequotation'], stdout=f, check=True)
            shutil.copy2(ETC / 'cnc.htpasswd', target / 'cnc.htpasswd')
        hashes = {p.name: hashlib.file_digest(p.open('rb'), 'sha256').hexdigest() for p in target.iterdir() if p.is_file()}
        write_json(target / 'SHA256.json', hashes)
    finally:
        if restart and active:
            run('systemctl', 'start', *active)
    return target


def restore(app, target):
    target = Path(target).resolve()
    if target.parent != (BACKUPS / app).resolve():
        raise ValueError('Sauvegarde hors du répertoire prévu.')
    hashes = read_json(target / 'SHA256.json')
    for name, checksum in hashes.items():
        if Path(name).name != name or hashlib.file_digest((target / name).open('rb'), 'sha256').hexdigest() != checksum:
            raise ValueError('Sauvegarde invalide.')
    record = read_json(target / 'record.json')
    release = OPT / 'apps' / app / 'releases' / record['sha']
    if not re.fullmatch('[a-f0-9]{40}', record['sha']) or not (release / '.ready').is_file():
        raise ValueError('Version sauvegardée absente : restaurer également ses fichiers de release.')
    # A restore is itself preceded by a safety snapshot.
    backup(app)
    run('systemctl', 'stop', *services(app))
    try:
        quarantine = VAR / (app + '.before-restore-' + secrets.token_hex(4))
        (VAR / app).rename(quarantine)
        with tarfile.open(target / 'data.tar') as tar:
            for member in tar.getmembers():
                if not member.name.startswith(app + '/') and member.name != app:
                    raise ValueError('Archive étrangère à cette application.')
            tar.extractall(VAR, filter='data')
        run('chown', '-R', user(app) + ':' + user(app), VAR / app)
        save_env(app, read_json(target / 'env.json'))
        if app == 'doctrad':
            with open(target / 'database.dump', 'rb') as f:
                subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_restore', '--clean', '--if-exists', '--exit-on-error', '-d', 'ofa_doctrad'], stdin=f, check=True)
        elif app == 'cnctolequotation':
            with open(target / 'database.sql', 'rb') as f:
                subprocess.run(['mariadb', 'ofa_cnctolequotation'], stdin=f, check=True)
            shutil.copy2(target / 'cnc.htpasswd', ETC / 'cnc.htpasswd')
        activate(app, release)
        if APPS[app]['kind'] == 'php':
            configure_php(app, release)
        else:
            configure_python(app, release, record['sha'])
        s = state(); s[app] = record; write_json(VAR / 'state.json', s)
        run('systemctl', 'daemon-reload')
        run('systemctl', 'start', *services(app))
        complete_deployment(app)
    except Exception:
        print('Restauration interrompue : services laissés arrêtés ; données précédentes conservées.')
        raise


def activate(app, release):
    link = OPT / 'apps' / app / 'current'
    tmp = link.with_name('current.new')
    tmp.unlink(missing_ok=True)
    tmp.symlink_to(release)
    os.replace(tmp, link)


def pending_deployment(app):
    return read_json(VAR / 'pending' / (app + '.json'))


def complete_deployment(app):
    # Only called once the frontend HTTP check has succeeded.
    (VAR / 'pending' / (app + '.json')).unlink(missing_ok=True)


def install(app, sha=None, admin_password=None, isolated=False):
    old = state().get(app)
    if not old and Path(APPS[app]['legacy']).exists() and not isolated:
        raise ValueError(f'Installation historique détectée pour {app}. Lire docs/migration.md ; --isolated autorise une installation séparée sans importer les données.')
    if not old and app in ('oddworks', 'cnctolequotation') and not admin_password:
        raise ValueError('Choisir un mot de passe administrateur via --admin-password-file avant toute installation PHP.')
    ensure_user(app)
    release, commit = prepare_release(app, sha)
    pending = pending_deployment(app)
    if pending and pending['sha'] != commit:
        raise ValueError('Déploiement précédent interrompu : restaurer sa sauvegarde avant de changer de version.')
    if old and old['sha'] == commit:
        run('systemctl', 'enable', '--now', *services(app))
        s = state(); s[app]['enabled'] = True; write_json(VAR / 'state.json', s)
        return
    snap = Path(pending['snapshot']) if pending and pending.get('snapshot') else (backup(app, restart=False) if old and not pending else None)
    write_json(VAR / 'pending' / (app + '.json'), {'sha': commit, 'snapshot': str(snap) if snap else None, 'old': old})
    try:
        if APPS[app]['kind'] == 'php':
            configure_php(app, release, admin_password)
        else:
            configure_python(app, release, commit)
        activate(app, release)
        run('systemctl', 'daemon-reload')
        run('systemctl', 'enable', '--now', *services(app))
        run('systemctl', 'restart', *services(app))
        for _ in range(20):
            if all(subprocess.run(['systemctl', 'is-active', '--quiet', s]).returncode == 0 for s in services(app)):
                break
            time.sleep(1)
        else:
            raise ValueError('Services non démarrés.')
        s = state(); s[app] = {'sha': commit, 'repo': APPS[app]['repo'], 'installed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'enabled': True}
        write_json(VAR / 'state.json', s)
        print(f'{app} : version {commit} installée. Vérification HTTP par la commande status.')
    except Exception:
        run('systemctl', 'stop', *services(app))
        print('Échec : aucune réussite enregistrée. Sauvegarde de retour arrière :', snap or 'installation initiale, configuration conservée pour reprise')
        raise
