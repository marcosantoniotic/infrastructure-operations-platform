import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('policy', Path(__file__).resolve().parents[2] / 'filter_plugins/blackbox_tls.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class TLSPolicyTest(unittest.TestCase):
    ca = '-----BEGIN CERTIFICATE-----\nfixture-not-for-crypto-tests\n-----END CERTIFICATE-----'

    def target(self, **changes):
        return dict(dict(name='glpi', url='https://glpi.test', require_https=True, private_ca=True), **changes)

    def test_legacy_and_valid(self):
        self.assertTrue(policy.validate_targets([dict(name='legacy', url='http://legacy:80')]))
        self.assertTrue(policy.validate_targets([self.target()], self.ca, 'ci-api'))

    def test_reject_inconsistent_policy(self):
        for changes in [dict(url='http://glpi.test'), dict(tls_insecure=True),
                        dict(require_https=False), dict(host_header='other.test'),
                        dict(private_ca='true'), dict(tls_server_name='other.test')]:
            with self.assertRaises(ValueError):
                policy.validate_targets([self.target(**changes)], self.ca, 'ci-api')
        for cert, network in [('', 'ci-api'), (self.ca, ''), ('not-pem', 'ci-api')]:
            with self.assertRaises(ValueError):
                policy.validate_targets([self.target()], cert, network)

    def test_preserve(self):
        installed = {'modules': {'http_glpi': {'http': {'fail_if_not_ssl': True,
                     'tls_config': {'ca_file': '/etc/blackbox_exporter/ca/private-ca.crt'}}}}}
        self.assertTrue(policy.preserve_policy(installed, [self.target()], 'ci-api', 'ci-api'))
        for targets in [[], [self.target(require_https=False)], [self.target(private_ca=False)]]:
            with self.assertRaises(ValueError):
                policy.preserve_policy(installed, targets, 'ci-api', 'ci-api')
        with self.assertRaises(ValueError):
            policy.preserve_policy(installed, [self.target()], '', 'ci-api')

    def test_module_collision(self):
        with self.assertRaises(ValueError):
            policy.validate_targets([dict(name=n, url='http://legacy') for n in ['a-b', 'a_b']])


if __name__ == '__main__':
    unittest.main()
