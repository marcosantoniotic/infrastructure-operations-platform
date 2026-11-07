"""Offline additive migration tests. Mocks are not agent/collection evidence."""
import copy
import json
import unittest

import test_netbox_vm_sync as legacy
import test_netbox_monitoring_field as field_tests


class TransitionAPI(field_tests.RichAPI):
    collision = False

    def call(self, method, params):
        if method == 'host.get' and params.get('hostids'):
            return [h for h in super().call(method, params) if h['hostid'] in params['hostids']]
        if method == 'item.get' and params.get('hostids'):
            return [{'key_': 'agent.22' if self.collision else 'icmp', 'itemid': 'old-item'}]
        if method == 'discoveryrule.get' and params.get('hostids'):
            return []
        if method == 'host.update':
            assert not set(params) & {'templates_clear', 'macros', 'tls_accept', 'tls_connect', 'interfaces'}
            result = super().call(method, params)
            host = next(h for h in self.hosts if h['hostid'] == params['hostid'])
            if 'groups' in params:
                host['hostgroups'] = host.pop('groups')
            if 'templates' in params:
                host['parentTemplates'] = host.pop('templates')
            return result
        return super().call(method, params)


class TransitionTests(unittest.TestCase):
    run_sync = legacy.SyncTests.run_sync

    def setUp(self):
        field_tests.MonitoringFieldTests.setUp(self)
        self.api = TransitionAPI()
        self.vms[0].custom_field_data['monitoring_profile'] = 'icmp'
        self.run_sync()
        self.host = self.api.hosts[0]
        self.host.update(tls_accept='2', macros=[{'macro': '{$LOCAL}', 'value': 'keep'}], description='keep')
        self.host['tags'].append({'tag': 'local', 'value': 'keep'})
        self.host['hostgroups'].append({'groupid': '999'})
        self.host['parentTemplates'].append({'templateid': '998'})
        self.api.writes.clear()
        self.env['NETBOX_PROFILE_TRANSITIONS'] = json.dumps([{'from': 'network-icmp', 'to': 'windows-active'}])
        self.env['NETBOX_PROFILE_READY'] = json.dumps({'virtualization.virtualmachine:1': {'profile': 'windows-active', 'hostid': '100'}})
        self.vms[0].custom_field_data['monitoring_profile'] = 'windows'

    def test_additive_same_host_preserves_local_state_and_idempotence(self):
        before = copy.deepcopy(self.host)
        self.assertEqual(self.run_sync(), 0)
        self.assertEqual(self.host['hostid'], before['hostid'])
        self.assertEqual(self.host['interfaces'], before['interfaces'])
        self.assertEqual(self.host['macros'], before['macros'])
        self.assertEqual(self.host['description'], before['description'])
        self.assertEqual(self.host['tls_accept'], '2')
        self.assertEqual({g['groupid'] for g in self.host['hostgroups']}, {'7', '999'})
        self.assertEqual({t['templateid'] for t in self.host['parentTemplates']}, {'22', '23', '998'})
        self.assertIn({'tag': 'local', 'value': 'keep'}, self.host['tags'])
        self.assertEqual([m for m, _ in self.api.writes], ['host.update'])
        self.api.writes.clear()
        self.assertEqual(self.run_sync(), 0)
        self.assertEqual(self.api.writes, [])

    def test_dry_run_no_writes(self):
        before = copy.deepcopy(self.host)
        self.assertEqual(self.run_sync(False), 0)
        self.assertEqual(self.api.writes, [])
        self.assertEqual(self.host, before)

    def test_no_readiness_or_wrong_identity_blocks_only_target(self):
        for value in [{}, {'virtualization.virtualmachine:1': {'profile': 'windows-active', 'hostid': '999'}}]:
            self.env['NETBOX_PROFILE_READY'] = json.dumps(value)
            before = copy.deepcopy(self.host)
            self.assertEqual(self.run_sync(), 2)
            self.assertEqual(self.api.writes, [])
            self.assertEqual(self.host, before)

    def test_plaintext_channel_refused(self):
        for value in ['1', '3', '5', '7', None]:
            self.host['tls_accept'] = value
            self.assertEqual(self.run_sync(), 2)
            self.assertEqual(self.api.writes, [])

    def test_colliding_local_item_blocks_without_adoption(self):
        self.api.collision = True
        self.assertEqual(self.run_sync(), 2)
        self.assertEqual(self.api.writes, [])

    def test_passive_agent_transition_not_enabled_as_shortcut(self):
        call = self.api.call
        def passive(method, params):
            if method == 'item.get' and params.get('templateids') == ['22']:
                return [{'type': '0', 'key_': 'agent.22', 'itemid': 'item-22'}]
            return call(method, params)
        self.api.call = passive
        self.assertEqual(self.run_sync(), 2)
        self.assertEqual(self.api.writes, [])

    def test_removal_is_not_automatic(self):
        self.run_sync()
        self.api.writes.clear()
        self.vms[0].custom_field_data['monitoring_profile'] = 'icmp'
        self.env['NETBOX_PROFILE_TRANSITIONS'] = json.dumps([{'from': 'windows-active', 'to': 'network-icmp'}])
        self.assertEqual(self.run_sync(), 2)
        self.assertEqual(self.api.writes, [])

    def test_pending_does_not_block_other_hosts_or_disable_pending_as_orphan(self):
        other = legacy.obj(2)
        other.custom_field_data['monitoring_profile'] = 'icmp'
        self.vms.append(other)
        self.env['NETBOX_PROFILE_READY'] = '{}'
        self.assertEqual(self.run_sync(), 2)
        self.assertEqual([m for m, _ in self.api.writes], ['host.create'])
        self.assertEqual(self.host['status'], '0')

    def test_invalid_selection_pending_not_orphan(self):
        self.vms[0].custom_field_data['monitoring_profile'] = None
        self.assertEqual(self.run_sync(), 2)
        self.assertEqual(self.api.writes, [])

    def test_previous_drift_not_repaired_silently(self):
        self.host['parentTemplates'] = []
        self.assertEqual(self.run_sync(), 2)
        self.assertEqual(self.api.writes, [])

    def test_missing_netbox_backreference_blocks(self):
        self.vms[0].custom_field_data.pop('zabbix_hostid')
        self.assertEqual(self.run_sync(), 2)
        self.assertEqual(self.api.writes, [])

    def test_concurrent_edit_is_not_overwritten(self):
        call = self.api.call
        def race(method, params):
            if method == 'host.get' and params.get('hostids'):
                self.host['hostgroups'].append({'groupid': '997'})
            return call(method, params)
        self.api.call = race
        self.assertEqual(self.run_sync(), 2)
        self.assertEqual(self.api.writes, [])

    def test_feature_removal_after_transition_refused(self):
        self.run_sync()
        self.api.writes.clear()
        self.env.update(NETBOX_PROFILE_TRANSITIONS='[]', NETBOX_PROFILE_READY='{}')
        with self.assertRaisesRegex(RuntimeError, 'installed profile reconciliation'):
            self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_malformed_policy_refused_before_any_write(self):
        for raw in ['true', '{}', '[{}]', '[{"from":"network-icmp","to":"missing"}]',
                    '[{"from":"network-icmp","to":"network-icmp"}]']:
            self.env['NETBOX_PROFILE_TRANSITIONS'] = raw
            with self.assertRaises(RuntimeError):
                self.run_sync()
            self.assertEqual(self.api.writes, [])


if __name__ == '__main__':
    unittest.main()
