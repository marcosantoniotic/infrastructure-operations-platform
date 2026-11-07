import importlib.util
import json
from pathlib import Path
import ssl
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('profile_policy', ROOT / 'filter_plugins/grafana_profiles.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class Profiles(unittest.TestCase):
    def test_admin_credentials_never_use_remote_plaintext_http(self):
        for url in ['http://grafana.example.test', 'ftp://localhost', 'https://u:p@grafana.example.test', 'https://grafana.example.test/?token=x']:
            with self.assertRaises(ValueError):
                policy.grafana_profiles_admin_endpoint(url)
        for url in ['http://127.0.0.1:3000', 'http://[::1]:3000', 'https://grafana.example.test']:
            self.assertTrue(policy.grafana_profiles_admin_endpoint(url))

    def test_positive_policy_and_dedicated_credentials(self):
        args = ['sha256:'+'a'*64, 'isolated_tls', 'https://zabbix.example.test/api_jsonrpc.php', 'public-fixture-ca', 'dedicated-reader', 'x'*32]
        with patch.object(policy.ssl, 'create_default_context') as context:
            self.assertTrue(policy.grafana_profiles_policy(*args))
            context.assert_called_once_with(cadata='public-fixture-ca')
            for index,value in [(4,'Admin'),(4,'guest'),(5,'short')]:
                bad=list(args);bad[index]=value
                with self.assertRaises(ValueError):policy.grafana_profiles_policy(*bad)

    def test_adoption_checks_precede_artifact_writes(self):
        prepare=(ROOT/'roles/grafana_profiles/tasks/prepare.yml').read_text()
        first_write=prepare.index('Create only the profile dashboard directory')
        for guard in ['Refuse unowned providers or dashboard files','Refuse an incompatible existing source','Refuse an unowned folder','Refuse to overwrite dashboards']:
            self.assertLess(prepare.index(guard),first_write)

    def test_four_dashboards_keep_identity_and_queries(self):
        for path in (ROOT / 'technical-dashboards').glob('*.json'):
            before = json.loads(path.read_text(encoding='utf-8'))
            after = policy.grafana_profile_dashboard(before, 'TEST ENVIRONMENT')
            self.assertEqual(after['uid'], before['uid'])
            self.assertEqual(after['templating'], before['templating'])
            self.assertEqual([p.get('targets') for p in after['panels']], [p.get('targets') for p in before['panels']])
            self.assertNotIn('candidate', after['tags'])
            self.assertNotIn('LABORATÓRIO SINTÉTICO', json.dumps(after, ensure_ascii=False))
            self.assertIn('candidate', before['tags'])

    def test_refuses_unowned_dashboard(self):
        with self.assertRaises(ValueError):
            policy.grafana_profile_dashboard({'uid': 'existing-local-dashboard'}, 'test')

    def test_windows_services_are_paginated_without_changing_collection(self):
        before = json.loads((ROOT / 'technical-dashboards/windows.json').read_text(encoding='utf-8'))
        after = policy.grafana_profile_dashboard(before, 'test')
        old = next(p for p in before['panels'] if p['title'] == 'Serviços Windows · estado')
        new = next(p for p in after['panels'] if p['title'] == old['title'])
        self.assertEqual(new['type'], 'table')
        self.assertTrue(new['options']['enablePagination'])
        self.assertEqual(new['targets'], old['targets'])
        old_states = old['fieldConfig']['defaults']['mappings'][0]['options']
        new_states = new['fieldConfig']['defaults']['mappings'][0]['options']
        self.assertEqual({k:v['text'] for k,v in new_states.items()}, {k:v['text'] for k,v in old_states.items()})
        self.assertEqual(new_states['6']['color'], 'gray')
        self.assertEqual(new['gridPos']['h'], 14)

    def test_policy_refuses_mutable_image_http_and_private_key(self):
        args = ['sha256:' + 'a' * 64, 'isolated_tls', 'https://zabbix.example.test/api_jsonrpc.php', 'not-a-certificate', 'dedicated-reader', 'x'*32]
        for index, value in [(0, 'grafana:latest'), (1, 'host'), (2, 'http://zabbix/api_jsonrpc.php'), (2, 'https://u:p@zabbix/api_jsonrpc.php'), (3, 'PRIVATE KEY')]:
            values = list(args); values[index] = value
            with self.assertRaises((ValueError, ssl.SSLError)):
                policy.grafana_profiles_policy(*values)

    def test_overlay_is_additive_and_deployment_is_scoped(self):
        tasks = (ROOT / 'roles/grafana_profiles/tasks/main.yml').read_text()
        self.assertIn('services: [grafana]', tasks)
        self.assertIn('dependencies: false', tasks)
        self.assertIn('pull: never', tasks)
        prepare = (ROOT / 'roles/grafana_profiles/tasks/prepare.yml').read_text()
        self.assertIn("'prune': false", prepare)
        self.assertIn("'tlsSkipVerify': false", prepare)
        self.assertIn('grafana_profiles_backup_confirmed', prepare)
        self.assertIn('Refuse to overwrite dashboards', prepare)


if __name__ == '__main__':
    unittest.main()
