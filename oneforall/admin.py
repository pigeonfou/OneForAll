"""Root orchestration; passwords travel through stdin, never argv or files."""
import json
from common import OPT, app_env, as_user

PYTHON_COMMON = '''import json, sys
name, password = json.load(sys.stdin)
'''
CABLEPLAN = PYTHON_COMMON + '''from app.db import connect
from app.main import hasher
with connect() as db:
    db.execute("INSERT INTO users(username,password_hash,role,active) VALUES(?,?,'admin',1) ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash,role='admin',active=1", (name, hasher.hash(password)))
    db.execute("DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?)", (name,))
    db.execute("DELETE FROM login_attempts")
'''
DOCTRAD = PYTHON_COMMON + '''from sqlalchemy import select
from app.db import Session, User
from app.auth import password_hash
with Session.begin() as db:
    user = db.scalar(select(User).where(User.username == name))
    if user is None:
        db.add(User(username=name, password=password_hash(password), admin=True))
    else:
        user.password = password_hash(password)
        user.admin = True
'''
ODDWORKS = '''$v=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
$db=new PDO('sqlite:'.getenv('PROJECTFLOW_DB_PATH'));
$db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);
$db->prepare("INSERT INTO utilisateurs(identifiant,mot_de_passe,role) VALUES(?,?,'admin') ON CONFLICT(identifiant) DO UPDATE SET mot_de_passe=excluded.mot_de_passe,role='admin'")->execute([$v[0],password_hash($v[1],PASSWORD_DEFAULT)]);
'''


def set_admin(app, name, password):
    if app not in ('cableplan', 'doctrad', 'oddworks'):
        raise ValueError('Application non prise en charge')
    if not name or len(name) > 100 or len(password) < 12:
        raise ValueError('Identifiant ou mot de passe invalide')
    executable = 'php' if app == 'oddworks' else OPT / 'apps' / app / 'current/.venv/bin/python'
    code = {'cableplan': CABLEPLAN, 'doctrad': DOCTRAD, 'oddworks': ODDWORKS}[app]
    # PHP -r and Python -c contain code only. The secret is sent on stdin.
    as_user(app, executable, '-r' if app == 'oddworks' else '-c', code,
            env=app_env(app), input=json.dumps([name, password]), capture=True)
