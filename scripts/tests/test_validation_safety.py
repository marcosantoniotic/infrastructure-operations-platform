import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('safety', ROOT/'filter_plugins/validation_safety.py')
safety = importlib.util.module_from_spec(spec)
spec.loader.exec_module(safety)


class SafetyTests(unittest.TestCase):
    def test_cidr(self):
        for good in ['198.51.100.0/24', '127.0.0.1/32']:
            self.assertTrue(safety.trusted_proxy_cidr(good))
        for bad in ['', None, '0.0.0.0/0', '198.51.100.1/24', '198.51.100.0/99', '::1/128', 'invalid']:
            self.assertFalse(safety.trusted_proxy_cidr(bad))

    def test_default_security_absent(self):
        self.assertFalse(any(safety.installed_features({'services': {'glpi': {}}}, 'glpi').values()))

    def test_old_and_new_mounts(self):
        for target in ['zzz-lab01-security.ini', 'zzz-iop-security.ini']:
            c = {'services': {'glpi': {'volumes': ['./php-security.ini:/etc/'+target+':ro']}}}
            self.assertTrue(safety.installed_features(c, 'glpi')['php_security'])
        c = {'services': {'netbox': {'volumes': [{'source': './cookie-security.py', 'target': '/etc/zz-iop-cookie-security.py'}]}}}
        self.assertTrue(safety.installed_features(c, 'netbox')['netbox_cookies'])

    def test_external_volume_identity(self):
        self.assertEqual(safety.external_volume_name({}), '')
        self.assertEqual(safety.external_volume_name({'external': True, 'name': 'ci-existing-volume'}), 'ci-existing-volume')
        self.assertEqual(safety.external_volume_name({'external': {'name': 'ci-existing-volume'}}), 'ci-existing-volume')
        self.assertEqual(safety.external_volume_name({'external': True}), 'mysql_data')
        for bad in [True, {'external': 'true'}, {'external': {'unexpected': True}}]:
            with self.assertRaises(ValueError):
                safety.external_volume_name(bad)


if __name__ == '__main__':
    unittest.main()
