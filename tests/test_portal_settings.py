import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'oneforall'))
import cli, common, render
import portal_settings as settings

class PortalTests(unittest.TestCase):
    def test_private_addresses_and_local_reset(self):
        self.assertEqual(settings.validate_services({'doctrad':' https://192.168.9.150:8443/doctrad/ ', 'oddworks':''}), {'doctrad':'https://192.168.9.150:8443/doctrad/'})
        self.assertEqual(settings.validate_services({'cableplan':'http://10.0.0.2:8080'}), {'cableplan':'http://10.0.0.2:8080/'})
        self.assertEqual(settings.validate_services({'doctrad':'https://[fd00::2]:8443/'}), {'doctrad':'https://[fd00::2]:8443/'})

    def test_untrusted_targets(self):
        for url in ('https://example.com/', 'http://127.0.0.1/', 'http://169.254.169.254/', 'http://8.8.8.8/', 'http://0.0.0.0/', 'http://[::1]/', 'ftp://192.168.1.2/', 'https://user:pass@192.168.1.2/', 'http://192.168.1.2:0/', 'http://192.168.1.2:65536/', 'http://192.168.1.2/?token=secret', 'http://192.168.1.2/#x', 'http://192.168.1.2/\ninvalid'):
            with self.subTest(url=url), self.assertRaises(ValueError): settings.validate_services({'doctrad':url})
        with self.assertRaises(ValueError): settings.validate_services({'unknown':'http://192.168.1.2/'})

    def test_atomic_save_and_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'services.json'
            settings.save_services({'doctrad':'http://192.168.1.2/'},path)
            with self.assertRaises(ValueError): settings.save_services({'doctrad':'http://example.com/'},path)
            self.assertEqual(settings.load_services(path),{'doctrad':'http://192.168.1.2/'})
            self.assertEqual(path.stat().st_mode & 0o777,0o640)
            settings.save_services({},path)
            self.assertEqual(settings.load_services(path),{})

    def request(self,body,headers=None):
        handler=object.__new__(settings.Handler);handler.path='/api/settings'
        encoded=json.dumps(body).encode();handler.rfile=io.BytesIO(encoded)
        handler.headers={'Content-Length':str(len(encoded)),'Content-Type':'application/json','Origin':'https://192.168.9.132:8443','X-OFA-Origin':'https://192.168.9.132:8443','X-OFA-Admin':'admin'}
        handler.headers.update(headers or {})
        handler.reply=lambda code,body:setattr(handler,'result',(code,body))
        handler.do_POST();return handler.result

    def test_auth_origin_csrf_size(self):
        with patch.object(settings,'save_services') as save:
            for headers,body in [({'X-OFA-Admin':''},{'token':settings.TOKEN}),({'Origin':'https://evil.example'},{'token':settings.TOKEN}),({}, {'token':'bad'}),({'Content-Type':'text/plain'},{'token':settings.TOKEN}),({'Content-Length':'99999'}, {})]:
                self.assertIn(self.request(body,headers)[0],(403,413))
            save.assert_not_called();save.return_value={'doctrad':'http://192.168.1.2/'}
            self.assertEqual(self.request({'token':settings.TOKEN,'services':save.return_value})[0],200)
            save.assert_called_once_with({'doctrad':'http://192.168.1.2/'})

    def test_admin_only_lan(self):
        config=json.loads((common.ROOT/'config/site.example.json').read_text());config.update(public_enabled=True,public_apps=['doctrad'])
        lan,public=render.nginx(config,{'doctrad':{}}).split('listen 127.0.0.1:',1)
        self.assertIn('auth_basic "OneForAll administration"',lan)
        self.assertIn('proxy_set_header X-OFA-Admin $remote_user;',lan)
        self.assertIn('location = /admin.html { return 403; }',public)
        self.assertIn('location /api/ { return 403; }',public)
        self.assertNotIn('admin.sock',public)

    def test_remote_not_installed_and_no_public_leak(self):
        config=json.loads((common.ROOT/'config/site.example.json').read_text())
        with patch.object(cli,'site',return_value=config),patch.object(cli,'state',return_value={}),patch.object(settings,'load_services',return_value={'doctrad':'http://192.168.9.150:8090/'}),patch.object(cli,'write_json') as write,patch.object(cli,'check') as check:
            cli.status();lan=write.call_args_list[0].args[1];public=write.call_args_list[1].args[1]
            self.assertEqual(lan['apps'][1]['url'],'http://192.168.9.150:8090/')
            self.assertEqual(lan['apps'][1]['status'],'external')
            self.assertTrue(lan['admin_enabled']);self.assertFalse(public['admin_enabled'])
            self.assertIsNone(public['apps'][1]['url']);check.assert_not_called()

    def test_portal_password_is_only_sent_on_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            etc=Path(directory);(etc/'nginx.conf').write_text('test')
            password='private-password-123'
            with patch.object(cli,'ETC',etc),patch('getpass.getpass',side_effect=[password,password]),patch.object(cli,'run',return_value='hashed') as run,patch.object(cli,'atomic') as atomic:
                cli.portal_admin_account()
                self.assertEqual(run.call_args_list[0].kwargs['input'],password+'\n')
                self.assertNotIn(password,str(run.call_args_list[0].args))
                self.assertEqual(atomic.call_args.args[1],'admin:hashed\n')

    def test_invalid_password_keeps_credentials(self):
        with patch('getpass.getpass',side_effect=['short','short']),patch.object(cli,'atomic') as atomic:
            with self.assertRaises(ValueError): cli.portal_admin_account()
            atomic.assert_not_called()
