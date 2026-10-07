"""Copy legacy installations into isolated instances; never delete legacy data."""
import datetime
import json
import re
import secrets
import shutil
import sqlite3
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from common import BACKUPS, ETC, OPT, VAR, app_env, read_json, run, save_env, services, state, user, write_json
from deploy import backup, configure_php, configure_python

LEGACY_UNITS = {
    'cableplan': ['cableplan'],
    'doctrad': ['docutranslate-web', 'docutranslate-worker', 'docutranslate-translation'],
    'oddworks': [],  # Shared Apache must continue serving the other legacy sites.
    'cnctolequotation': [],
}


def read_env(path):
    values={}
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'): continue
        key, separator, value=line.partition('=')
        if not separator or not re.fullmatch('[A-Z][A-Z0-9_]*',key):
            raise ValueError('Format du fichier historique non pris en charge ; aucune commande shell exécutée.')
        values[key]=value.strip().strip('"').strip("'")
    return values


def db_name(name):
    if not re.fullmatch('[a-zA-Z][a-zA-Z0-9_]{0,62}',name):
        raise ValueError('Nom de base historique invalide')
    return name


def import_legacy(app):
    if app not in state():
        raise ValueError('Installer d’abord une instance OneForAll séparée avec --isolated.')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+secrets.token_hex(3)
    snapshot=BACKUPS/('legacy-'+app)/stamp
    snapshot.mkdir(parents=True,mode=0o700)
    source=None; models=None; source_db=None; source_config=None
    if app=='cableplan': source=Path('/var/lib/cableplan')
    elif app=='oddworks': source=Path('/var/lib/projectflow')
    elif app=='doctrad':
        source_config=read_env('/etc/docutranslate/docutranslate.env')
        url=urlsplit(source_config['DATABASE_URL'])
        if not url.scheme.startswith('postgresql') or url.hostname not in ('localhost','127.0.0.1') or url.port not in (None,5432):
            raise ValueError('Import DocTrad automatique réservé à PostgreSQL local sur le port standard.')
        source_db=db_name(url.path.lstrip('/'))
        source=Path(source_config.get('DATA_ROOT','/var/lib/docutranslate'))
        models=Path(source_config.get('MODEL_ROOT','/opt/docutranslate/models/translation'))
    else:
        # Read the legacy PHP config as its existing unprivileged owner.
        command=['runuser','-u','cnctole','--','php','-r',"echo json_encode(require '/opt/cnctolequotation/api/config.php');"]
        result=subprocess.run(command,capture_output=True,text=True,check=True)
        source_config=json.loads(result.stdout)
        if source_config['db']['host'] not in ('localhost','127.0.0.1') or int(source_config['db']['port'])!=3306:
            raise ValueError('Import CNC automatique réservé à MariaDB local sur le port standard.')
        source_db=db_name(source_config['db']['name'])
        source=Path('/opt/cnctolequotation/data')
        models=source/'models'
    if not source.is_dir(): raise ValueError('Données historiques introuvables ; aucune modification effectuée.')
    if models is not None and not models.is_dir(): raise ValueError('Modèles historiques introuvables ; corriger la configuration source avant import.')
    active=[unit for unit in LEGACY_UNITS[app] if subprocess.run(['systemctl','is-active','--quiet',unit]).returncode==0]
    if active: run('systemctl','stop',*active)
    safety=None
    try:
        # Snapshot files before altering the new instance. SQLite backup is coherent
        # even while a shared Apache instance continues serving OddWorks.
        if app in ('cableplan','oddworks'):
            src=source/'database.sqlite'
            if not src.is_file(): raise ValueError('Base SQLite historique introuvable')
            with sqlite3.connect('file:'+str(src)+'?mode=ro',uri=True) as db,sqlite3.connect(snapshot/'database.sqlite') as dst:
                db.backup(dst)
        elif app=='doctrad':
            with open(snapshot/'database.dump','wb') as stream:
                subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc',source_db],stdout=stream,check=True)
            shutil.copytree(source,snapshot/'data')
            shutil.copytree(models,snapshot/'models')
        else:
            with open(snapshot/'database.sql','wb') as stream:
                subprocess.run(['mariadb-dump','--single-transaction',source_db],stdout=stream,check=True)
            shutil.copytree(source,snapshot/'data')
            for name in ('logs','tmp'):
                legacy=Path('/opt/cnctolequotation')/name
                if legacy.is_dir(): shutil.copytree(legacy,snapshot/name)
        if source_config: write_json(snapshot/'source-config.json',source_config)
        safety=backup(app,restart=False)
        target=VAR/app
        if app in ('cableplan','oddworks'):
            for suffix in ('','-wal','-shm'):
                (target/('database.sqlite'+suffix)).unlink(missing_ok=True)
            shutil.copy2(snapshot/'database.sqlite',target/'database.sqlite')
        elif app=='doctrad':
            for item in (snapshot/'data').iterdir():
                dest=target/item.name
                if dest.is_dir(): shutil.rmtree(dest)
                elif dest.exists(): dest.unlink()
                if item.is_dir(): shutil.copytree(item,dest)
                else: shutil.copy2(item,dest)
            if (target/'models').exists(): shutil.rmtree(target/'models')
            shutil.copytree(snapshot/'models',target/'models')
            with open(snapshot/'database.dump','rb') as stream:
                subprocess.run(['runuser','-u','postgres','--','pg_restore','--clean','--if-exists','--no-owner','--role=ofa_doctrad','--exit-on-error','-d','ofa_doctrad'],stdin=stream,check=True)
        else:
            for item in (snapshot/'data').iterdir():
                dest=target/item.name
                if dest.is_dir(): shutil.rmtree(dest)
                elif dest.exists(): dest.unlink()
                if item.is_dir(): shutil.copytree(item,dest)
                else: shutil.copy2(item,dest)
            for name in ('logs','tmp'):
                if (snapshot/name).is_dir():
                    shutil.rmtree(target/name,ignore_errors=True)
                    shutil.copytree(snapshot/name,target/name)
            with open(snapshot/'database.sql','rb') as stream:
                subprocess.run(['mariadb','ofa_cnctolequotation'],stdin=stream,check=True)
            # Imported demo tokens remain disabled; keep other tokens intact.
            run('mariadb','ofa_cnctolequotation',input="UPDATE api_tokens SET is_active=0 WHERE token_hash=SHA2('demo-token-change-me',256);")
            geometry=source_config['paths'].get('geometry_python','')
            if geometry and re.fullmatch(r'/opt/[a-zA-Z0-9_./-]+',geometry) and Path(geometry).is_file():
                values=app_env(app);values['CNCTOLE_GEOMETRY_PYTHON']=geometry;save_env(app,values)
        run('chown','-R',user(app)+':'+user(app),target)
        release=OPT/'apps'/app/'current'
        if app in ('oddworks','cnctolequotation'): configure_php(app,release)
        else: configure_python(app,release,state()[app]['sha'])
        run('systemctl','daemon-reload')
        run('systemctl','start',*services(app))
        write_json(snapshot/'import.json',{'app':app,'target_safety_snapshot':str(safety),'completed':True})
        print(f'Import {app} terminé. Source historique conservée ; sauvegarde cible : {safety}')
        if app=='oddworks':
            print('La source Apache est restée active. Pour la bascule finale, suspendre les écritures OddWorks historiques, refaire l’import puis réserver les écritures à OneForAll.')
    except Exception:
        print('Import interrompu. Source conservée. Sauvegarde cible :',safety or 'cible non modifiée')
        raise
    finally:
        if active: run('systemctl','start',*active)
