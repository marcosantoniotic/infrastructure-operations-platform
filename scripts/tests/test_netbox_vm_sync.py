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
        if method == 'host.get': return copy.deepcopy(self.hosts)
        self.writes.append((method, copy.deepcopy(params)))
        if method == 'host.create':
            h = copy.deepcopy(params); h['hostid'] = str(100 + len(self.hosts))
            h['status'] = str(h['status']); h['hostgroups'] = h.pop('groups')
            h['parentTemplates'] = h.pop('templates')
            for i in h['interfaces']: i['interfaceid'] = h['hostid']
            self.hosts.append(h)
            return {'hostids': [h['hostid']]}
        if method == 'host.update':
            h = next(h for h in self.hosts if h['hostid'] == params['hostid'])
            h.update(params); h['status'] = str(h['status']); return {}
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


if __name__ == '__main__': unittest.main()
