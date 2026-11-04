"""Offline platform selection and refusal contracts; APIs/models are mocked."""
import copy
import json
import os
import types
import unittest
from unittest.mock import patch

import test_netbox_vm_sync as legacy

API, obj = legacy.API, legacy.obj

PROFILES = {
    'linux-active': {'group': 'Linux servers', 'template': 'Linux by Zabbix agent active'},
    'windows-active': {'group': 'Windows servers', 'template': 'Windows by Zabbix agent active'},
    'network-icmp': {'group': 'Network devices', 'template': 'ICMP Ping'},
}
MAPPING = {'rhel': 'linux-active', 'windows-server': 'windows-active', 'routeros': 'network-icmp'}


class ProfileAPI(API):
    groups = {'Linux servers': '2', 'Virtual machines': '6', 'Windows servers': '7', 'Network devices': '8'}
    templates = {'Linux active': '21', 'Linux by Zabbix agent active': '21',
                 'Windows by Zabbix agent active': '22', 'ICMP Ping': '23'}

    def call(self, method, params):
        if method == 'discoveryrule.get':
            return []
        if method == 'item.get':
            return [{'type': '3' if params['templateids'] == ['23'] else '7'}]
        if method in {'hostgroup.get', 'template.get'}:
            values, key = (self.groups, 'groupid') if method == 'hostgroup.get' else (self.templates, 'templateid')
            value = params['filter']['name'][0]
            return [{key: values[value]}] if value in values else []
        return super().call(method, params)


class PlatformTests(unittest.TestCase):
    run_sync = legacy.SyncTests.run_sync

    def setUp(self):
        legacy.SyncTests.setUp(self)
        self.api = ProfileAPI()
        self.env.update(NETBOX_PLATFORM_MAPPING_ENABLED='true',
                        NETBOX_PLATFORM_MAP=json.dumps(MAPPING), NETBOX_PLATFORM_PROFILES=json.dumps(PROFILES))
        self.vms[0].platform = types.SimpleNamespace(slug='rhel')

    def test_device_and_vm_matrix_uses_platform_not_object_kind(self):
        self.vms.clear()
        for index, platform in enumerate(MAPPING, 1):
            for objects, kind in [(self.devices, 'dcim.device'), (self.vms, 'virtualization.virtualmachine')]:
                record = obj(index, kind, kind.replace('.', '-') + '-' + platform)
                record.platform = types.SimpleNamespace(slug=platform)
                objects.append(record)
        self.run_sync()
        self.assertEqual(len(self.api.hosts), 6)
        for host in self.api.hosts:
            tags = {t['tag']: t['value'] for t in host['tags']}
            profile = PROFILES[MAPPING[tags['netbox_platform']]]
            self.assertEqual(host['hostgroups'], [{'groupid': self.api.groups[profile['group']]}])
            self.assertEqual(host['parentTemplates'], [{'templateid': self.api.templates[profile['template']]}])
            self.assertEqual(tags['netbox_monitoring_profile'], MAPPING[tags['netbox_platform']])
        self.api.writes.clear()
        self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_unknown_late_object_blocks_entire_batch_before_writes(self):
        self.vms.append(obj(2, name='unknown-platform'))
        with self.assertRaisesRegex(RuntimeError, 'platform'): self.run_sync()
        self.assertEqual(self.api.writes, [])
        self.assertTrue(all(not v.custom_field_data for v in self.vms))

    def test_unknown_platform_has_no_linux_fallback(self):
        self.vms[0].platform.slug = 'unmapped'
        with self.assertRaisesRegex(RuntimeError, 'platform'): self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_unknown_outside_selected_site_does_not_block(self):
        self.vms.append(obj(2, site='outside', name='not-selected'))
        self.run_sync()
        self.assertEqual(len(self.api.hosts), 1)

    def test_vm_opt_in_still_required(self):
        self.env['NETBOX_INCLUDE_VMS'] = 'false'
        self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_dry_run_has_no_api_or_custom_field_writes(self):
        self.run_sync(False)
        self.assertEqual(self.api.writes, [])
        self.assertEqual(self.vms[0].custom_field_data, {})

    def test_missing_template_blocks_before_writes(self):
        profiles = copy.deepcopy(PROFILES); profiles['windows-active']['template'] = 'missing'
        self.env['NETBOX_PLATFORM_PROFILES'] = json.dumps(profiles)
        with self.assertRaisesRegex(RuntimeError, 'exactly one'): self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_snmp_template_refused_before_first_host_or_metadata_write(self):
        call = self.api.call
        self.api.call = lambda method, params: ([{'type': '20'}] if method == 'item.get'
            and params['templateids'] == ['23'] else call(method, params))
        with self.assertRaisesRegex(RuntimeError, 'unsupported interface'): self.run_sync()
        self.assertEqual(self.api.writes, [])
        self.assertEqual(self.vms[0].custom_field_data, {})

    def test_snmp_discovery_and_prototype_are_also_refused(self):
        call = self.api.call
        for rule in ({'type': '20'}, {'type': '7', 'items': [{'type': '20'}]}):
            with self.subTest(rule=rule):
                self.api.call = lambda method, params: ([rule] if method == 'discoveryrule.get'
                    and params['templateids'] == ['23'] else call(method, params))
                with self.assertRaisesRegex(RuntimeError, 'unsupported interface'): self.run_sync()
                self.assertEqual(self.api.writes, [])

    def test_existing_legacy_vm_requires_explicit_migration(self):
        for key in ['NETBOX_PLATFORM_MAPPING_ENABLED', 'NETBOX_PLATFORM_MAP', 'NETBOX_PLATFORM_PROFILES']:
            self.env.pop(key)
        self.run_sync()
        before = copy.deepcopy(self.api.hosts)
        self.env.update(NETBOX_PLATFORM_MAPPING_ENABLED='true', NETBOX_PLATFORM_MAP=json.dumps(MAPPING),
                        NETBOX_PLATFORM_PROFILES=json.dumps(PROFILES))
        self.api.writes.clear()
        with self.assertRaisesRegex(RuntimeError, 'group'): self.run_sync()
        self.assertEqual(self.api.writes, [])
        self.assertEqual(self.api.hosts, before)

    def test_existing_matching_host_adopts_profile_without_replacing_extras(self):
        self.vms.clear()
        device = obj(5, 'dcim.device'); device.platform = types.SimpleNamespace(slug='rhel')
        self.devices.append(device)
        self.env['NETBOX_PLATFORM_MAPPING_ENABLED'] = 'false'
        self.env['NETBOX_PLATFORM_MAP'] = self.env['NETBOX_PLATFORM_PROFILES'] = '{}'
        self.run_sync()
        host = self.api.hosts[0]
        host['hostgroups'].append({'groupid': 'extra'})
        host['parentTemplates'].append({'templateid': 'extra'})
        host['tags'].append({'tag': 'local-owner', 'value': 'keep'})
        self.env.update(NETBOX_PLATFORM_MAPPING_ENABLED='true', NETBOX_PLATFORM_MAP=json.dumps(MAPPING),
                        NETBOX_PLATFORM_PROFILES=json.dumps(PROFILES))
        self.api.writes.clear(); self.run_sync()
        self.assertEqual([m for m, p in self.api.writes], ['host.update'])
        self.assertEqual(set(self.api.writes[0][1]), {'hostid', 'tags'})
        self.assertIn({'groupid': 'extra'}, host['hostgroups'])
        self.assertIn({'templateid': 'extra'}, host['parentTemplates'])
        self.assertIn({'tag': 'local-owner', 'value': 'keep'}, host['tags'])

    def test_platform_change_does_not_retemplate_existing_host(self):
        self.run_sync(); before = copy.deepcopy(self.api.hosts)
        self.vms[0].platform.slug = 'windows-server'; self.api.writes.clear()
        with self.assertRaisesRegex(RuntimeError, 'group'): self.run_sync()
        self.assertEqual(self.api.writes, [])
        self.assertEqual(self.api.hosts, before)

    def test_platform_alias_same_profile_only_updates_managed_tag(self):
        self.env['NETBOX_PLATFORM_MAP'] = json.dumps(dict(MAPPING, linux='linux-active'))
        self.run_sync(); host = self.api.hosts[0]
        groups, templates = copy.deepcopy(host['hostgroups']), copy.deepcopy(host['parentTemplates'])
        self.vms[0].platform.slug = 'linux'; self.api.writes.clear()
        self.run_sync()
        self.assertEqual([m for m, p in self.api.writes], ['host.update'])
        self.assertEqual(set(self.api.writes[0][1]), {'hostid', 'tags'})
        self.assertEqual((host['hostgroups'], host['parentTemplates']), (groups, templates))

    def test_profile_alias_change_refused_even_with_same_group_and_template(self):
        self.run_sync()
        profiles = copy.deepcopy(PROFILES); profiles['new-linux'] = profiles['linux-active']
        mapping = dict(MAPPING, rhel='new-linux')
        self.env.update(NETBOX_PLATFORM_MAP=json.dumps(mapping), NETBOX_PLATFORM_PROFILES=json.dumps(profiles))
        self.api.writes.clear()
        with self.assertRaisesRegex(RuntimeError, 'profile differs'): self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_silent_mapping_removal_refused(self):
        self.run_sync(); self.api.writes.clear()
        for key in ['NETBOX_PLATFORM_MAPPING_ENABLED', 'NETBOX_PLATFORM_MAP', 'NETBOX_PLATFORM_PROFILES']:
            self.env.pop(key)
        with self.assertRaisesRegex(RuntimeError, 'silently remove'): self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_unknown_owned_profile_preflight_prevents_partial_create(self):
        self.run_sync(); self.api.hosts[0]['tags'].append({'tag': 'local-owner', 'value': 'keep'})
        self.vms[0].tags = []
        next(t for t in self.api.hosts[0]['tags'] if t['tag'] == 'netbox_monitoring_profile')['value'] = 'retired'
        self.vms.append(obj(2)); self.vms[1].platform = types.SimpleNamespace(slug='rhel')
        self.api.writes.clear()
        with self.assertRaisesRegex(RuntimeError, 'unknown monitoring profile'): self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_profile_tag_removed_disables_only_owned_in_scope_host(self):
        self.run_sync(); self.vms[0].tags = []; self.api.writes.clear()
        self.run_sync()
        self.assertEqual(self.api.writes, [('host.update', {'hostid': '100', 'status': 1})])

    def test_mapped_ip_change_keeps_identity_tags_extra_interface_and_macros(self):
        self.vms[0].platform.slug = 'routeros'
        self.run_sync(); host = self.api.hosts[0]
        host['tags'].append({'tag': 'local-owner', 'value': 'keep'})
        host['macros'] = [{'macro': '{$LOCAL}', 'value': 'keep'}]
        host['interfaces'].append({'interfaceid': 'extra', 'type': 2, 'main': 1,
                                    'ip': '192.0.2.99', 'port': '161'})
        before = copy.deepcopy(host)
        self.vms[0].primary_ip4.address.ip = '203.0.113.20'
        self.api.writes.clear(); self.run_sync()
        self.assertEqual(self.api.writes, [('hostinterface.update', {'interfaceid': '100',
            'ip': '203.0.113.20', 'useip': 1, 'dns': '', 'port': '10050'})])
        self.assertEqual(host['hostid'], before['hostid'])
        for key in ('tags', 'macros', 'parentTemplates', 'hostgroups'):
            self.assertEqual(host[key], before[key])
        self.assertEqual(host['interfaces'][1], before['interfaces'][1])

    def test_interface_drift_or_ambiguity_refused_before_writes(self):
        self.run_sync(); original = copy.deepcopy(self.api.hosts[0])
        for change in ('missing', 'duplicate', 'port', 'dns'):
            with self.subTest(change=change):
                host = copy.deepcopy(original)
                if change == 'missing': host['interfaces'] = []
                elif change == 'duplicate': host['interfaces'].append(dict(host['interfaces'][0]))
                elif change == 'port': host['interfaces'][0]['port'] = '10051'
                else: host['interfaces'][0]['useip'] = 0
                self.api.hosts = [host]; self.api.writes.clear()
                with self.assertRaisesRegex(RuntimeError, 'interface'): self.run_sync()
                self.assertEqual(self.api.writes, [])

    def test_invalid_policy_never_reaches_setup_or_api(self):
        bad = [
            {'NETBOX_PLATFORM_MAPPING_ENABLED': 'yes'},
            {'NETBOX_PLATFORM_MAP': '[]'},
            {'NETBOX_PLATFORM_MAP': '{}'},
            {'NETBOX_PLATFORM_PROFILES': '{}'},
            {'NETBOX_PLATFORM_MAP': '{"rhel":"linux-active","rhel":"windows-active"}'},
            {'NETBOX_PLATFORM_MAP': '{"rhel":"missing"}'},
            {'NETBOX_PLATFORM_PROFILES': '{"linux-active":{"group":"x","template":"y","port":"161"}}'},
            {'NETBOX_PLATFORM_PROFILES': '{"linux-active":{"group":"x","template":"${UNSAFE}"}}'},
            {'NETBOX_PLATFORM_MAPPING_ENABLED': 'false'},
        ]
        self.g['setup_netbox'] = lambda: self.fail('Invalid policy reached Django')
        for env in bad:
            with self.subTest(env=env), patch.dict(self.env, env):
                with self.assertRaises(RuntimeError): self.run_sync()
                self.assertEqual(self.api.writes, [])

    def test_validation_command_needs_no_django_token_or_api(self):
        self.g['setup_netbox'] = lambda: self.fail('Validation reached Django')
        with patch.dict(os.environ, self.env), patch('sys.argv', ['sync', '--validate-platform-config']):
            self.assertEqual(self.g['main'](), 0)
        self.assertEqual(self.api.writes, [])


if __name__ == '__main__':
    unittest.main()
