"""Offline checks of the immutable, sanitized real-API record; no API calls.

These tests check consistency/provenance, not a new functional run. Historical
evidence stays immutable when production code evolves; a new run gets a new file.
"""
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / 'docs/evidence/netbox-zabbix-ip-functional-20261028.json'
EXPECTED_SHA256 = '02bcfa3910e0dfe75deb086c7ec5b4900c0315298741dec1a7f437fc746091cf'


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof = json.loads(RECORD.read_text(encoding='utf-8'))
        cls.snapshots = cls.proof['snapshots']

    def test_historical_record_integrity(self):
        self.assertEqual(hashlib.sha256(RECORD.read_bytes()).hexdigest(), EXPECTED_SHA256)
        self.assertRegex(self.proof['execution']['sync_sha256'], r'^[0-9a-f]{64}$')
        self.assertEqual(self.proof['execution']['revision'], 'dcfb850c0ec94fecd32095a2f6a96ecfd10c3b9d')

    def test_same_device_host_and_main_interface(self):
        first = self.snapshots['C-initial']
        primary_ids = set()
        for snapshot in self.snapshots.values():
            self.assertEqual(snapshot['netbox_device_id'], first['netbox_device_id'])
            self.assertEqual(snapshot['zabbix_hostid'], first['zabbix_hostid'])
            self.assertEqual(str(snapshot['netbox_stored_hostid']), first['zabbix_hostid'])
            self.assertEqual(snapshot['zabbix_status'], '1')
            primary = [i for i in snapshot['interfaces'] if i['type'] == '1' and i['main'] == '1']
            self.assertEqual(len(primary), 1)
            primary_ids.add(primary[0]['interfaceid'])
        self.assertEqual(len(primary_ids), 1)

    def test_ip_transition_and_real_rpc_result(self):
        self.assertEqual(self.snapshots['C-initial']['netbox_primary'], '198.51.100.10/32')
        gap = self.snapshots['E-before-apply']
        self.assertEqual(gap['netbox_primary'], '203.0.113.20/32')
        self.assertEqual(next(i for i in gap['interfaces'] if i['main'] == '1')['ip'], '198.51.100.10')
        after = self.snapshots['G-after']
        primary = next(i for i in after['interfaces'] if i['main'] == '1')
        self.assertEqual(after['netbox_primary'], '203.0.113.20/32')
        self.assertEqual(primary['ip'], '203.0.113.20')
        calls = self.proof['ip_change_rpc']
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['method'], 'hostinterface.update')
        self.assertEqual(calls[0]['params']['interfaceid'], primary['interfaceid'])
        self.assertEqual(calls[0]['params']['ip'], primary['ip'])
        self.assertEqual(calls[0]['result']['interfaceids'], [primary['interfaceid']])

    def test_unmanaged_state_and_idempotence(self):
        baseline = self.snapshots['D-local-state']
        secondary = [i for i in baseline['interfaces'] if i['main'] == '0']
        self.assertEqual(len(secondary), 1)
        for name in ('G-after', 'H-repeated', 'J-after'):
            after = self.snapshots[name]
            self.assertEqual(after['unmanaged_local_tag'], baseline['unmanaged_local_tag'])
            self.assertTrue(after['local_description_present'])
            self.assertEqual([i for i in after['interfaces'] if i['main'] == '0'], secondary)
        self.assertEqual(self.proof['idempotence_rpc'], [])
        stages = {e['stage']: e for e in self.proof['events']}
        self.assertEqual(stages['F-G']['observed']['owned_host_count'], 1)
        self.assertEqual(stages['H']['observed']['rpc_writes'], 0)
        self.assertEqual(stages['J-idempotence']['observed']['rpc_writes'], 0)

    def test_pass_events_isolation_and_cleanup(self):
        self.assertEqual(self.proof['result'], 'PASS')
        self.assertEqual(len(self.proof['events']), 12)
        self.assertTrue(all(e['result'] == 'PASS' for e in self.proof['events']))
        self.assertTrue(self.proof['cleanup']['objects_removed_by_id'])
        self.assertTrue(self.proof['cleanup']['credentials_revoked'])
        self.assertEqual(self.proof['cleanup']['errors'], [])
        self.assertEqual(self.proof['isolation']['published_ports'], 0)
        self.assertTrue(self.proof['isolation']['internal_network'])
        self.assertEqual(self.proof['resource_cleanup']['test_containers_removed'], 8)
        self.assertEqual(self.proof['resource_cleanup']['test_volumes_removed'], 5)
        outside = next(e for e in self.proof['events'] if e['stage'] == 'outside-scope')['observed']
        self.assertTrue(outside['non_owned_configuration_unchanged'])
        self.assertEqual((outside['real_objects'], outside['alerts_before'], outside['alerts_after']), (0, 0, 0))

    def test_only_documentation_addresses_and_no_credential_keys(self):
        reserved = [ipaddress.ip_network(n) for n in ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24')]
        for value in re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', RECORD.read_text(encoding='utf-8')):
            self.assertTrue(any(ipaddress.ip_address(value) in network for network in reserved), value)

        def inspect(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & {'password', 'passwd', 'token', 'authorization', 'cookie', 'private_key'})
                for item in value.values():
                    inspect(item)
            elif isinstance(value, list):
                for item in value:
                    inspect(item)
        inspect(self.proof)

    def test_fixture_tools_refuse_optimized_python_before_setup(self):
        for path in ('scripts/tests/functional_netbox_zabbix_ip.py',
                     'scripts/tests/fixtures/netbox_zabbix_ip_public.py'):
            with self.subTest(path=path):
                result = subprocess.run([sys.executable, '-O', str(ROOT / path)],
                    capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Refusing optimized Python', result.stderr)
                self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
