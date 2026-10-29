"""Offline reconciliation contract: no network, Django or credentials required."""
import copy
import os
from pathlib import Path
import runpy
import tempfile
import types
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2] / 'roles/netbox_zabbix_sync/templates/netbox-zabbix-sync.py.j2'


class Query(list):
    def filter(self, **kw):
        return Query(x for x in self if kw.get('tags__slug') in x.tags)
    def select_related(self, *a): return self
    def distinct(self): return self
    def order_by(self, *a): return self


def obj(pk, kind='virtualization.virtualmachine', name='example', site='test', ip='192.0.2.10'):
    x = types.SimpleNamespace(pk=pk, _meta=types.SimpleNamespace(label_lower=kind), name=name,
        site=types.SimpleNamespace(slug=site), role=None, platform=None, status='active',
        primary_ip4=types.SimpleNamespace(address=types.SimpleNamespace(ip=ip)) if ip else None,
        primary_ip6=None, custom_field_data={}, tags=['zabbix'])
    x.save = lambda **kw: None
    return x


class API:
    def __init__(self, *a): self.hosts = []; self.writes = []
    def call(self, method, params):
        if method == 'hostgroup.get':
            return [{'groupid': '6' if params['filter']['name'] == ['Virtual machines'] else '2'}]
        if method == 'template.get': return [{'templateid': '99'}]
        if method == 'host.get':
            output = copy.deepcopy(self.hosts)
            for h in output:
                for tag in h.get('tags', []):
                    tag.setdefault('automatic', '0')  # Zabbix 7.4 read-only output
            return output
        self.writes.append((method, copy.deepcopy(params)))
        if method == 'host.create':
            h = copy.deepcopy(params); h['hostid'] = str(100 + len(self.hosts))
            h['status'] = str(h['status']); h['hostgroups'] = h.pop('groups')
            h['parentTemplates'] = h.pop('templates')
            for i in h['interfaces']: i['interfaceid'] = h['hostid']
            self.hosts.append(h)
            return {'hostids': [h['hostid']]}
        if method == 'host.update':
            if any(set(t) - {'tag', 'value'} for t in params.get('tags', [])):
                raise RuntimeError('host.update: unexpected read-only tag parameter')
            h = next(h for h in self.hosts if h['hostid'] == params['hostid'])
            h.update(params); h['status'] = str(h['status']); return {}
        if method == 'hostinterface.update':
            interface = next(i for h in self.hosts for i in h['interfaces']
                             if i['interfaceid'] == params['interfaceid'])
            interface.update(params)
            return {'interfaceids': [interface['interfaceid']]}
        raise AssertionError(method)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.g = runpy.run_path(str(SOURCE))['main'].__globals__
        self.api = API(); self.vms = Query([obj(1)])
        self.devices = Query([])
        self.g.update(setup_netbox=lambda: None, ZabbixAPI=lambda *a: self.api,
            Device=types.SimpleNamespace(objects=self.devices),
            VirtualMachine=types.SimpleNamespace(objects=self.vms),
            ensure_custom_field=lambda *a: None)
        self.fixture_file = tempfile.NamedTemporaryFile(delete=False)
        self.fixture_file.write(b'offline-test-only'); self.fixture_file.close()
        self.addCleanup(Path(self.fixture_file.name).unlink)
        self.env = dict(ZABBIX_API_TOKEN_FILE=self.fixture_file.name, ZABBIX_URL='https://example.invalid',
            ZABBIX_GROUP='Linux servers', ZABBIX_TEMPLATE='Linux active', NETBOX_TAG_SLUG='zabbix',
            NETBOX_ZABBIX_HOSTID_FIELD='zabbix_hostid', NETBOX_INCLUDE_VMS='true',
            NETBOX_VM_GROUP='Virtual machines', NETBOX_VM_TEMPLATE='ICMP Ping', NETBOX_SITE_SLUGS='test')

    def run_sync(self, apply=True):
        with patch.dict(os.environ, self.env), patch('sys.argv', ['sync'] + (['--apply'] if apply else [])):
            return self.g['main']()

    def test_vm_create_and_idempotence(self):
        self.run_sync(); self.assertEqual(self.api.hosts[0]['host'], 'netbox-vm-1')
        self.assertEqual(self.vms[0].custom_field_data['zabbix_hostid'], '100')
        self.api.writes.clear(); self.run_sync(); self.assertEqual(self.api.writes, [])

    def test_default_keeps_vms_disabled(self):
        del self.env['NETBOX_INCLUDE_VMS']; self.run_sync(); self.assertEqual(self.api.writes, [])

    def test_typed_ids_do_not_collide(self):
        self.devices.append(obj(1, 'dcim.device', 'device-example'))
        self.run_sync(); self.assertEqual(len(self.api.hosts), 2)

    def test_legacy_device_keeps_host_id(self):
        self.vms.clear(); self.devices.append(obj(7, 'dcim.device', 'legacy-device'))
        self.run_sync(); h = self.api.hosts[0]
        h['tags'] = [t for t in h['tags'] if t['tag'] != 'netbox_object_type']
        self.api.writes.clear(); self.run_sync()
        self.assertEqual((len(self.api.hosts), h['hostid']), (1, '100'))
        self.assertFalse(any(m == 'host.create' for m,p in self.api.writes))

    def test_duplicate_ownership_refused_before_writes(self):
        self.run_sync(); duplicate = copy.deepcopy(self.api.hosts[0]); duplicate['hostid'] = '999'
        self.api.hosts.append(duplicate); self.api.writes.clear()
        with self.assertRaisesRegex(RuntimeError, 'Multiple'): self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_dry_run_no_writes(self):
        self.run_sync(False); self.assertEqual(self.api.writes, [])
        self.assertEqual(self.vms[0].custom_field_data, {})

    def test_global_collision_preflight_no_partial_writes(self):
        self.vms.append(obj(2))
        self.api.hosts.append(dict(hostid='8', host='netbox-vm-2', tags=[]))
        with self.assertRaisesRegex(RuntimeError, 'collision'): self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_new_objects_cannot_share_planned_technical_name(self):
        self.devices.append(obj(9, 'dcim.device', 'netbox-vm-1'))
        with self.assertRaisesRegex(RuntimeError, 'collision'): self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_unknown_managed_object_type_cannot_be_disabled(self):
        self.api.hosts.append(dict(hostid='8', host='foreign-object', status='0',
            hostgroups=[{'groupid':'2'}], tags=[{'tag':'source','value':'netbox'},
            {'tag':'netbox_id','value':'1'}, {'tag':'netbox_site','value':'test'},
            {'tag':'netbox_object_type','value':'unsupported.model'}]))
        with self.assertRaisesRegex(RuntimeError, 'Unsupported'): self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_conflicting_custom_field_refused(self):
        self.vms[0].custom_field_data['zabbix_hostid'] = 'other'
        with self.assertRaisesRegex(RuntimeError, 'Conflicting'): self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_rename_preserves_id_and_external_tags(self):
        self.run_sync(); self.vms[0].name = 'renamed'
        self.api.hosts[0]['tags'].append(dict(tag='owner', value='keep'))
        self.run_sync(); h = self.api.hosts[0]
        self.assertEqual((h['hostid'], h['host'], h['name']), ('100', 'netbox-vm-1', 'renamed'))
        self.assertIn(dict(tag='owner', value='keep'), h['tags'])

    def test_tag_removed_disables_no_delete(self):
        self.run_sync(); self.vms[0].tags = []; self.run_sync()
        self.assertEqual(self.api.hosts[0]['status'], '1')
        self.assertFalse(any(m == 'host.delete' for m, p in self.api.writes))

    def test_site_scope_preserves_other_hosts(self):
        self.run_sync(); self.env['NETBOX_SITE_SLUGS'] = 'another'; self.api.writes.clear()
        self.run_sync(); self.assertEqual(self.api.writes, [])

    def test_existing_vm_refuses_silent_downgrade(self):
        self.run_sync(); self.env['NETBOX_INCLUDE_VMS'] = 'false'; self.api.writes.clear()
        with self.assertRaisesRegex(RuntimeError, 'silently'): self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_missing_ip_not_created(self):
        self.vms[0].primary_ip4 = None; self.run_sync(); self.assertEqual(self.api.writes, [])

    def test_template_mismatch_refused(self):
        self.run_sync(); self.api.hosts[0]['parentTemplates'] = []; self.api.writes.clear()
        with self.assertRaisesRegex(RuntimeError, 'template'): self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_device_primary_ip_updates_same_agent_interface_only(self):
        self.vms.clear()
        device = obj(7, 'dcim.device', 'synthetic-ip-change', ip='198.51.100.10')
        device.status = 'planned'
        self.devices.append(device)
        self.run_sync()
        host = self.api.hosts[0]
        host['description'] = 'outside sync responsibility'
        host['tags'].append({'tag': 'local-test-owner', 'value': 'keep'})
        agent_id = host['interfaces'][0]['interfaceid']
        secondary = dict(interfaceid='secondary', type=2, main=1, ip='192.0.2.99', port='161')
        host['interfaces'].insert(0, secondary)
        before = copy.deepcopy(host)
        device.primary_ip4.address.ip = '203.0.113.20'
        self.api.writes.clear()
        self.run_sync()
        self.assertEqual(self.api.writes, [('hostinterface.update', {
            'interfaceid': agent_id, 'ip': '203.0.113.20', 'useip': 1, 'dns': '', 'port': '10050'})])
        self.assertEqual(len(self.api.hosts), 1)
        self.assertEqual(host['hostid'], before['hostid'])
        self.assertEqual(host['tags'], before['tags'])
        self.assertEqual(host['description'], before['description'])
        self.assertEqual(host['interfaces'][0], before['interfaces'][0])
        self.assertEqual(device.custom_field_data['zabbix_hostid'], host['hostid'])
        self.api.writes.clear()
        self.run_sync()
        self.assertEqual(self.api.writes, [])

    def test_primary_ip_change_dry_run_preserves_interface(self):
        self.run_sync()
        before = copy.deepcopy(self.api.hosts)
        self.vms[0].primary_ip4.address.ip = '203.0.113.20'
        self.api.writes.clear()
        self.run_sync(False)
        self.assertEqual(self.api.writes, [])
        self.assertEqual(self.api.hosts, before)

    def test_managed_tag_change_drops_readonly_metadata_not_local_tag(self):
        self.vms[0].status = 'planned'
        self.run_sync()
        self.api.hosts[0]['tags'].append(dict(tag='local-test-owner', value='keep'))
        self.vms[0].status = 'offline'  # both map to disabled host, but tag changes
        self.api.writes.clear()
        self.run_sync()
        self.assertEqual([m for m, p in self.api.writes], ['host.update'])
        tags = self.api.writes[0][1]['tags']
        self.assertIn(dict(tag='local-test-owner', value='keep'), tags)
        self.assertTrue(all(set(t) == {'tag', 'value'} for t in tags))


if __name__ == '__main__': unittest.main()
