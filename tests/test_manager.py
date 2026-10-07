import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'oneforall'))
import common
import render
import cli
import deploy

CONFIG = json.loads((common.ROOT / 'config/site.example.json').read_text())


class ConfigurationTests(unittest.TestCase):
    def test_configuration_rejects_injection_and_public_network(self):
        for key, value in [('domain','x; include evil;'),('lan_ip','0.0.0.0'),('lan_networks',['0.0.0.0/0']),('certificate','/tmp/a;bad'),('public_apps',['evil']),('lan_port','8443')]:
            c=copy.deepcopy(CONFIG);c[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError): common.validate_site(c)

    def test_closed_tunnel_has_no_upstream(self):
        text=render.nginx(CONFIG, {a:{} for a in common.APPS})
        public=text[text.index('listen 127.0.0.1:'):]
        self.assertNotIn('proxy_pass',public)
        self.assertNotIn('fastcgi_pass',public)
        self.assertEqual(public.count('return 403;'),5)

    def test_channels_and_allowlist(self):
        c=copy.deepcopy(CONFIG);c.update(public_enabled=True,public_apps=['cableplan'])
        text=render.nginx(c,{a:{} for a in common.APPS})
        public=text[text.index('listen 127.0.0.1:'):]
        self.assertIn('X-CablePlan-Access-Channel tunnel;',public)
        self.assertNotIn('X-CablePlan-Access-Channel lan;',public)
        self.assertNotIn('fastcgi_pass',public)
        self.assertIn('allow 192.168.1.0/24; deny all;',text)
        self.assertNotIn('0.0.0.0:',text)

    def test_php_protected_and_bearer_preserved(self):
        text=render.nginx(CONFIG,{a:{} for a in common.APPS})
        self.assertIn('auth_basic "CNCToleQuotation";',text)
        self.assertIn('location = /api/v1/quote { auth_basic off;',text)
        self.assertIn('fastcgi_param HTTP_AUTHORIZATION $http_authorization;',text)
        self.assertIn('config|includes|install|tests|scripts|docs|packaging',text)
        self.assertLess(text.index(':https://cnctolequotation'),text.index('~^(POST|PUT|PATCH|DELETE): 1;'))

    def test_unknown_cli_app_refused_before_operations(self):
        with self.assertRaises(ValueError): cli.main(['install','--apps','../../etc'])

    def test_atomic_configuration_and_secret_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';common.write_json(p,{'a':1})
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
            common.write_json(p,{'a':2})
            self.assertEqual(common.read_json(p),{'a':2})
            self.assertFalse(p.with_name('config.json.new').exists())

    def test_invalid_secret_does_not_overwrite_config(self):
        with tempfile.TemporaryDirectory() as d,patch.object(common,'ETC',Path(d)):
            common.save_env('doctrad',{'SECRET':'valid'})
            with self.assertRaises(ValueError): common.save_env('doctrad',{'SECRET':'bad\ninjection'})
            self.assertEqual(common.app_env('doctrad'),{'SECRET':'valid'})

    def test_unknown_app_has_no_route(self):
        text=render.nginx(CONFIG,{})
        self.assertNotIn('proxy_pass',text)
        self.assertNotIn('fastcgi_pass',text)

    def test_stale_configuration_rolls_back_on_reload_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);previous=copy.deepcopy(CONFIG)
            common.write_json(root/'site.json',previous)
            candidate=copy.deepcopy(CONFIG);candidate['public_enabled']=True
            common.write_json(root/'candidate.json',candidate)
            with patch.object(cli,'ETC',root),patch.object(cli.Path,'exists',return_value=True),patch.object(cli,'reload_front',side_effect=ValueError('nginx invalid')):
                with self.assertRaises(ValueError): cli.configure(root/'candidate.json')
            self.assertEqual(common.read_json(root/'site.json'),previous)

    def test_same_commit_reenable_without_migration(self):
        old={'cableplan':{'sha':'a'*40,'enabled':False}}
        with patch.object(deploy,'state',return_value=old),patch.object(deploy,'ensure_user'),patch.object(deploy,'prepare_release',return_value=(Path('/unused'),'a'*40)),patch.object(deploy,'run'),patch.object(deploy,'write_json') as saved,patch.object(deploy,'configure_python') as migrate:
            deploy.install('cableplan')
            migrate.assert_not_called()
            self.assertTrue(saved.call_args.args[1]['cableplan']['enabled'])

    def test_incomplete_doctrad_never_reported_ready(self):
        result=type('Result',(),{'returncode':0,'stdout':json.dumps({'database':True,'storage':True,'ready':False})+'\n200'})()
        with patch.object(cli.subprocess,'run',return_value=result):
            self.assertEqual(cli.check('doctrad',CONFIG),'limited')

    def test_failing_database_never_reported_ready(self):
        result=type('Result',(),{'returncode':0,'stdout':json.dumps({'database':False,'storage':True})+'\n200'})()
        with patch.object(cli.subprocess,'run',return_value=result):
            self.assertEqual(cli.check('cableplan',CONFIG),'unavailable')

    def test_cableplan_remote_restriction_preserved(self):
        result=type('Result',(),{'returncode':0,'stdout':'{}\n403'})()
        with patch.object(cli.subprocess,'run',return_value=result):
            self.assertEqual(cli.check('cableplan',CONFIG,True),'restricted')

    def test_failed_update_stops_app_and_retains_snapshot(self):
        old={'cableplan':{'sha':'a'*40,'enabled':True}}
        with patch.object(deploy,'state',return_value=old),patch.object(deploy,'ensure_user'),patch.object(deploy,'prepare_release',return_value=(Path('/unused'),'b'*40)),patch.object(deploy,'backup',return_value=Path('/safe/backup')) as snapshot,patch.object(deploy,'configure_python',side_effect=ValueError('migration')),patch.object(deploy,'run') as run,patch.object(deploy,'write_json') as saved:
            with self.assertRaises(ValueError): deploy.install('cableplan')
            snapshot.assert_called_once_with('cableplan',restart=False)
            self.assertTrue(all(str(call.args[0]).endswith('pending/cableplan.json') for call in saved.call_args_list))
            run.assert_called_once_with('systemctl','stop','oneforall-cableplan-web')

    def test_restore_path_cannot_escape(self):
        with self.assertRaises(ValueError): deploy.restore('cableplan','/tmp/foreign')

    def test_interrupted_update_retains_original_snapshot(self):
        old={'cableplan':{'sha':'a'*40,'enabled':True}}
        pending={'sha':'b'*40,'snapshot':'/safe/original','old':old['cableplan']}
        with patch.object(deploy,'state',return_value=old),patch.object(deploy,'ensure_user'),patch.object(deploy,'prepare_release',return_value=(Path('/unused'),'b'*40)),patch.object(deploy,'pending_deployment',return_value=pending),patch.object(deploy,'backup') as snapshot,patch.object(deploy,'configure_python',side_effect=ValueError('migration')),patch.object(deploy,'run'),patch.object(deploy,'write_json'):
            with self.assertRaises(ValueError): deploy.install('cableplan')
            snapshot.assert_not_called()

    def test_cnc_requires_a_working_database(self):
        result=type('Result',(),{'returncode':0,'stdout':'\n401'})()
        active=type('Result',(),{'returncode':0})()
        with patch.object(cli.subprocess,'run',side_effect=[result,active]),patch.object(cli,'as_user',return_value='{"database":false,"ready":false}'),patch.object(cli,'app_env',return_value={}):
            self.assertEqual(cli.check('cnctolequotation',CONFIG),'unavailable')

    def test_cnc_ready_requires_backend_check(self):
        result=type('Result',(),{'returncode':0,'stdout':'\n401'})()
        active=type('Result',(),{'returncode':0})()
        with patch.object(cli.subprocess,'run',side_effect=[result,active]),patch.object(cli,'as_user',return_value='{"database":true,"ready":true}'),patch.object(cli,'app_env',return_value={}):
            self.assertEqual(cli.check('cnctolequotation',CONFIG),'available')

    def test_legacy_environment_is_read_without_shell_execution(self):
        import migrate
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'legacy.env';file.write_text('# comment\nDATA_ROOT="/var/lib/docutranslate"\nDATABASE_URL=$(never-execute)\n')
            with patch.object(migrate,'run') as run:
                values=migrate.read_env(file)
            run.assert_not_called()
            self.assertEqual(values['DATABASE_URL'],'$(never-execute)')
            self.assertEqual(values['DATA_ROOT'],'/var/lib/docutranslate')

if __name__=='__main__': unittest.main()
