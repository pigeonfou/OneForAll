import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'oneforall'))
import admin

class AdminTests(unittest.TestCase):
    def test_secret_only_passed_on_stdin(self):
        for app in ('oddworks','cableplan','doctrad'):
            with self.subTest(app=app), patch.object(admin,'as_user') as run, patch.object(admin,'app_env',return_value={'APP':'test'}):
                admin.set_admin(app,'admin','test-password-123')
                self.assertNotIn('test-password-123',str(run.call_args.args))
                self.assertNotIn('test-password-123',str(run.call_args.kwargs['env']))
                self.assertEqual(json.loads(run.call_args.kwargs['input']),['admin','test-password-123'])
    def test_invalid_input_never_runs(self):
        with patch.object(admin,'as_user') as run:
            for app,name,password in [('bad','admin','long-password-123'),('oddworks','','long-password-123'),('doctrad','admin','short')]:
                with self.assertRaises(ValueError):admin.set_admin(app,name,password)
            run.assert_not_called()
