import copy
import json
from pathlib import Path
import sys
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'oneforall'))
import common
import render
import external_apps

CONFIG = json.loads((common.ROOT / 'config/site.example.json').read_text())
SPEC = {'name': 'DocTrad 2.0', 'description': 'Local translation', 'kind': 'python', 'port': 8097,
        'root': '/opt/doctrad2/current', 'health': '/health', 'managed_externally': True,
        'systemd_services': ['doctrad2-web', 'doctrad2-worker'], 'strip_prefix': True}


class ExternalApplicationTests(unittest.TestCase):
    def test_external_prefix_is_removed_and_normal_app_prefix_is_preserved(self):
        with patch.dict(common.APPS, {'doctrad2': SPEC}):
            v2 = render.path_locations('doctrad2', '/opt/doctrad2/current', False, True)
            original = render.path_locations('doctrad', '/opt/oneforall/apps/doctrad/current', False, True)
        self.assertIn('proxy_pass http://127.0.0.1:8097/;', v2)
        self.assertIn('proxy_pass http://127.0.0.1:18102;', original)
        self.assertNotIn('18102/;', original)

    def test_external_service_names_are_not_rewritten(self):
        with patch.dict(common.APPS, {'doctrad2': SPEC}):
            self.assertEqual(common.services('doctrad2'), ['doctrad2-web', 'doctrad2-worker'])
            with self.assertRaises(ValueError):
                external_apps.refuse_external('doctrad2', common.APPS)

    def test_public_access_stays_restricted_without_explicit_app_allowlist(self):
        config = copy.deepcopy(CONFIG)
        config.update(routing_mode='paths', public_enabled=True, public_apps=['doctrad'])
        with patch.dict(common.APPS, {'doctrad2': SPEC}):
            text = render.nginx(config, {'doctrad': {}, 'doctrad2': {}})
        public = text[text.index('listen 127.0.0.1:'):]
        self.assertIn('location /doctrad2/ { return 403; }', public)
        self.assertNotIn('proxy_pass http://127.0.0.1:8097', public)
