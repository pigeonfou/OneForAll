#!/usr/bin/env python3
"""Validate rendered nginx configurations with the actual native parser.

Does not install or start system services. Use --native-root for extracted debs.
"""
import argparse
import copy
import json
import os
import pwd
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'oneforall'))
from common import ROOT, APPS
from render import nginx
from deploy import php_pool

parser=argparse.ArgumentParser()
parser.add_argument('--native-root',type=Path,default=Path('/'))
a=parser.parse_args()
a.native_root=a.native_root.resolve()
exe=a.native_root/'usr/sbin/nginx'
if not exe.is_file():
    raise SystemExit('Install nginx or supply --native-root; no native validation performed.')
with tempfile.TemporaryDirectory() as d:
    p=Path(d)
    cert=p/'server.crt';key=p/'server.key'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=www.pigeonfou.com','-keyout',str(key),'-out',str(cert)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    for app in APPS:
        (p/'opt/oneforall/apps'/app/'current').mkdir(parents=True)
    for case in ('empty','all-local','all-public','selected-public'):
        c=json.loads((ROOT/'config/site.example.json').read_text());c.update(certificate=str(cert),private_key=str(key))
        with socket.socket() as lan_socket, socket.socket() as tunnel_socket:
            lan_socket.bind(('127.0.0.1', 0)); tunnel_socket.bind(('127.0.0.1', 0))
            c['lan_port']=lan_socket.getsockname()[1]; c['tunnel_port']=tunnel_socket.getsockname()[1]
        installed={} if case=='empty' else {app:{} for app in APPS}
        if case.endswith('public'):
            c.update(public_enabled=True,public_apps=list(APPS) if case=='all-public' else ['cableplan'])
        text=nginx(c,installed)
        text=text.replace('listen ' + c['lan_ip'] + ':', 'listen 127.0.0.1:')
        text=text.replace('user www-data;', 'user ' + pwd.getpwuid(os.getuid()).pw_name + ';')
        text=text.replace('/etc/nginx/',str(a.native_root/'etc/nginx')+'/')
        for folder in ('/var/lib/oneforall','/run/oneforall','/opt/oneforall','/var/log/oneforall'):
            text=text.replace(folder,str(p)+folder)
        (p/'var/log').mkdir(parents=True,exist_ok=True)
        (p/'run').mkdir(exist_ok=True)
        (p/'var/lib/oneforall/nginx').mkdir(parents=True,exist_ok=True)
        conf=p/(case+'.conf');conf.write_text(text)
        subprocess.run([str(exe),'-t','-e',str(p/'error.log'),'-p',str(p),'-c',str(conf)],check=True)
        print(case+': nginx syntax OK')
    fpm_files=list((a.native_root/'usr/sbin').glob('php-fpm[0-9]*'))
    if fpm_files:
        for app in ('oddworks','cnctolequotation'):
            text=php_pool(app, p/app, {'PROJECTFLOW_BASE_PATH':'/'} if app=='oddworks' else {'CNCTOLE_CONFIG':str(p/'config.php')})
            name=pwd.getpwuid(os.getuid()).pw_name
            text=text.replace('user = ofa-'+app, 'user = '+name).replace('group = ofa-'+app,'group = '+name)
            text=text.replace('/run/oneforall-'+app,str(p/'run')).replace('/var/log/',str(p)+'/')
            conf=p/(app+'-fpm.conf');conf.write_text(text)
            subprocess.run([str(fpm_files[-1]),'-t','-y',str(conf)],check=True)
            print(app+': PHP-FPM syntax OK')
