"""Offline Ansible-expression checks; no inventory, network, or credentials."""
import base64
from pathlib import Path
import sys
import unittest
import tempfile
import subprocess
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar
try:
    from ansible.template import trust_as_template
except ImportError:  # ansible-core 2.14 on the validation controller
    trust_as_template = lambda value: value


def expressions(tasks):
    guard = next(t for t in tasks if 'block' in t and 'bootstrap' in t['name'])
    return next(t['ansible.builtin.assert']['that'] for t in guard['block']
                if t['name'].startswith('Refuse a deploy'))


class BootstrapGuard(unittest.TestCase):
    expressions = None

    def permits(self, config):
        variables = {
            'dns_standby_expected_bootstrap_dns': ['192.0.2.10', '192.0.2.11'],
            'dns_standby_protected_config': {
                'content': base64.b64encode(yaml.safe_dump(config).encode()).decode()
            },
        }
        templar = Templar(loader=DataLoader(), variables=variables)
        return all(templar.template(trust_as_template('{{ ' + e + ' }}')) in (True, 'True')
                   for e in self.expressions)

    def setUp(self):
        if self.expressions is None:
            self.expressions = expressions(yaml.safe_load(
                (Path(__file__).resolve().parents[2] / 'roles/dns_standby/tasks/bootstrap-preflight.yml').read_text()))
        self.config = {'dns': {
            'bootstrap_dns': ['192.0.2.10', '192.0.2.11'],
            'upstream_dns': ['https://resolver.example/dns-query'],
        }}

    def test_expected(self):
        self.assertTrue(self.permits(self.config))

    def test_wrong_bootstrap(self):
        self.config['dns']['bootstrap_dns'] = ['192.0.2.99']
        self.assertFalse(self.permits(self.config))

    def test_http_rejected(self):
        self.config['dns']['upstream_dns'] = ['http://resolver.example/dns-query']
        self.assertFalse(self.permits(self.config))

    def test_empty_upstream_rejected(self):
        self.config['dns']['upstream_dns'] = []
        self.assertFalse(self.permits(self.config))

    def test_tls_bypass_rejected(self):
        self.config['dns']['insecure_skip_verify'] = True
        self.assertFalse(self.permits(self.config))

    def test_upstream_file_rejected(self):
        self.config['dns']['upstream_dns_file'] = '/tmp/alternate-upstreams'
        self.assertFalse(self.permits(self.config))

    def test_fallback_rejected(self):
        self.config['dns']['fallback_dns'] = ['192.0.2.99']
        self.assertFalse(self.permits(self.config))

    def test_explicit_empty_alternatives(self):
        self.config['dns'].update(upstream_dns_file='', fallback_dns=[])
        self.assertTrue(self.permits(self.config))


class InstalledGuard(unittest.TestCase):
    def test_real_preflight_lifecycle(self):
        task = Path(__file__).resolve().parents[2] / 'roles/dns_standby/tasks/bootstrap-preflight.yml'
        with tempfile.TemporaryDirectory(prefix='dns-guard-') as folder:
            root = Path(folder)
            config = root / 'conf/AdGuardHome.yaml'
            config.parent.mkdir()
            config.write_text(yaml.safe_dump({'dns': {
                'bootstrap_dns': ['192.0.2.10', '192.0.2.11'],
                'upstream_dns': ['https://resolver.example/dns-query'],
            }}))
            before = config.read_bytes()
            play = root / 'test.yml'

            def run(enabled, expected=True):
                variables = {'dns_standby_project_dir': str(root),
                             'dns_standby_bootstrap_guard': enabled,
                             'dns_standby_expected_bootstrap_dns': ['192.0.2.10', '192.0.2.11'] if expected else []}
                play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
                    'vars': variables, 'tasks': [{'ansible.builtin.import_tasks': str(task)}]}]))
                result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)],
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(config.read_bytes(), before)
                return result

            self.assertEqual(run(False).returncode, 0)  # legacy untouched
            marker = root / '.bootstrap-protected.json'
            self.assertFalse(marker.exists())
            self.assertEqual(run(True).returncode, 0)
            original = marker.stat().st_mtime_ns
            self.assertEqual(run(True).returncode, 0)
            self.assertEqual(marker.stat().st_mtime_ns, original)  # idempotent
            self.assertNotEqual(run(False).returncode, 0)  # removed wrapper policy
            self.assertNotEqual(run(True, expected=False).returncode, 0)  # incomplete policy
            self.assertTrue(marker.exists())


if __name__ == '__main__':
    if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
        tasks = yaml.safe_load(base64.b64decode(sys.argv.pop(1)))
        BootstrapGuard.expressions = expressions(tasks)
    unittest.main()
