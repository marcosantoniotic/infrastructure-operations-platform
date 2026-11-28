"""Offline Ansible-expression checks; no inventory, network, or credentials."""
import base64
from pathlib import Path
import sys
import unittest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar
try:
    from ansible.template import trust_as_template
except ImportError:  # ansible-core 2.14 on the validation controller
    trust_as_template = lambda value: value


def expressions(tasks):
    guard = next(t for t in tasks if 'block' in t and 'bootstrap' in t['name'])
    return guard['block'][-1]['ansible.builtin.assert']['that']


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
                (Path(__file__).resolve().parents[2] / 'roles/dns_standby/tasks/main.yml').read_text()))
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


if __name__ == '__main__':
    if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
        tasks = yaml.safe_load(base64.b64decode(sys.argv.pop(1)))
        BootstrapGuard.expressions = expressions(tasks)
    unittest.main()
