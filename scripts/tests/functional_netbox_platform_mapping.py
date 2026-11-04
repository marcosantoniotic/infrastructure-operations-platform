#!/usr/bin/env python3
"""Real API acceptance INSIDE a fresh synthetic-ip-* fixture only.

Uses the existing disposable fixture builder, never an existing application DB.
No mocks of NetBox models or API responses. A forwarding write guard restricts
the actual reconciler to the exact newly created IDs. All hosts stay disabled.
"""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
import logging
import os
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

if not __debug__:
    raise SystemExit('Refusing optimized Python: fixture safety assertions must remain enabled')

import requests

ROOT = Path('/fixture')
NB = 'https://netbox.functional.example.test/api/'
ZX = 'https://zabbix.functional.example.test/api_jsonrpc.php'
CA = '/tls/ca.crt'
PROFILES = {
    'linux-active': {'group': 'Linux servers', 'template': 'Linux by Zabbix agent active'},
    'windows-active': {'group': 'Windows servers', 'template': 'Windows by Zabbix agent active'},
    'network-icmp': {'group': 'Network devices', 'template': 'ICMP Ping'},
}
MAPPING = {'rhel': 'linux-active', 'windows-server': 'windows-active', 'routeros': 'network-icmp'}


def main():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    run = manifest['run_id']
    assert run.startswith('synthetic-ip-platform-') and os.geteuid() == 0
    assert os.environ.get('REQUESTS_CA_BUNDLE') == CA
    os.umask(0o077)
    out = ROOT / 'evidence'
    events, ledger, owned_hosts, writes = [], [], {}, []

    def save(name, value):
        p = out / name
        p.write_text(json.dumps(value, indent=2), encoding='utf-8')
        p.chmod(0o600)

    def check(name, condition, observed):
        event = dict(stage=name, result='PASS' if condition else 'FAIL', observed=observed,
                     utc=datetime.now(timezone.utc).isoformat())
        events.append(event); save('platform-events.json', events)
        print(json.dumps(event), flush=True)
        assert condition, name

    sys.path.insert(0, '/opt/netbox/netbox')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from users.models import Token
    from dcim.models import Device
    from virtualization.models import VirtualMachine
    assert Device.objects.count() == VirtualMachine.objects.count() == 0
    token = (
        Token.objects.create(user=get_user_model().objects.get(username='synthetic-admin'), description=run)
    )
    nb_auth = token.get_auth_header_prefix() + token.token
    z_auth = None

    def nb(method, path, body=None):
        response = requests.request(method, NB + path, json=body,
            headers={'Authorization': nb_auth}, verify=CA, timeout=30)
        response.raise_for_status()
        return response.json() if response.content else None

    def zx(method, params, authenticated=True):
        response = requests.post(ZX, json=dict(jsonrpc='2.0', method=method, params=params, id=1),
            headers={'Authorization': 'Bearer ' + z_auth} if authenticated else {}, verify=CA, timeout=30)
        response.raise_for_status(); payload = response.json()
        if 'error' in payload: raise RuntimeError(method + ': ' + json.dumps(payload['error']))
        return payload['result']

    def create(path, **body):
        assert body.get('description') == run
        row = nb('POST', path, body)
        ledger.append(dict(path=path, id=row['id']))
        save('platform-ownership.private.json', ledger)
        return row

    def hosts():
        return zx('host.get', dict(output=['hostid', 'host', 'name', 'status', 'description'],
            selectTags='extend', selectInterfaces='extend', selectHostGroups=['groupid'], selectParentTemplates=['templateid']))

    vendor_pwd = json.loads((ROOT / 'secrets/bootstrap.json').read_text())['admin_password']
    z_auth = zx('user.login', dict(username='Admin', password='zabbix'), False)
    admin = zx('user.get', dict(output=['userid'], filter={'username': ['Admin']}))
    assert len(admin) == 1
    zx('user.update', dict(userid=admin[0]['userid'], passwd=vendor_pwd, current_passwd='zabbix'))
    z_auth = zx('user.login', dict(username='Admin', password=vendor_pwd), False)
    (ROOT / 'secrets/zabbix-api-token').write_text(z_auth)
    baseline_hosts = hosts()
    assert not any(any(t['tag'] == 'source' and t['value'] == 'netbox' for t in h['tags']) for h in baseline_hosts)
    medias = zx('user.get', dict(output=['userid'], selectMedias='extend'))
    assert not any(u['medias'] for u in medias)
    alerts_before = zx('alert.get', dict(output=['alertid']))
    save('platform-execution.json', dict(utc=datetime.now(timezone.utc).isoformat(), revision=manifest['revision'],
        source_sha256=hashlib.sha256((ROOT / 'netbox-zabbix-sync.py').read_bytes()).hexdigest(),
        harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        netbox=str(settings.VERSION), zabbix=zx('apiinfo.version', {}, False), images=manifest['images'],
        topology=importlib.metadata.version('netbox-topology-views'), qrcode=importlib.metadata.version('netbox-qrcode'),
        scheduled_sync=False, all_test_hosts_disabled=True, ports_published=0, mocks=False))
    group_ids, template_ids = {}, {}
    for name, profile in PROFILES.items():
        found = zx('hostgroup.get', dict(output=['groupid'], filter={'name': [profile['group']]}))
        if not found:
            found = [{'groupid': zx('hostgroup.create', dict(name=profile['group']))['groupids'][0]}]
        assert len(found) == 1
        group_ids[name] = found[0]['groupid']
        templates = zx('template.get', dict(output=['templateid'], filter={'name': [profile['template']]}))
        assert len(templates) == 1, profile['template']
        template_ids[name] = templates[0]['templateid']
        items = zx('item.get', dict(output=['type', 'key_'], templateids=[templates[0]['templateid']]))
        assert items
        if name == 'network-icmp':
            assert all(i['type'] == '3' and i['key_'].startswith('icmpping') for i in items)
        else:
            assert any(i['type'] == '7' for i in items)
    legacy_group = zx('hostgroup.get', dict(output=['groupid'], filter={'name': ['Virtual machines']}))
    if not legacy_group:
        zx('hostgroup.create', dict(name='Virtual machines'))
    records = []
    site = create('dcim/sites/', name=run, slug=run, description=run)
    maker = create('dcim/manufacturers/', name=run, slug=run, description=run)
    dtype = create('dcim/device-types/', model=run, slug=run, manufacturer=maker['id'], description=run)
    role = create('dcim/device-roles/', name=run, slug=run, color='9e9e9e', description=run)
    tag = create('extras/tags/', name=run, slug=run, color='9e9e9e', description=run)
    create('extras/custom-fields/', name='synthetic_platform_hostid', label='Synthetic Platform Host ID',
           type='text', object_types=['dcim.device', 'virtualization.virtualmachine'], description=run)
    ctype = create('virtualization/cluster-types/', name=run, slug=run, description=run)
    cluster = create('virtualization/clusters/', name=run, type=ctype['id'], description=run)
    for index, slug in enumerate(MAPPING):
        platform = create('dcim/platforms/', name=slug, slug=slug, description=run)
        for kind in ('device', 'vm'):
            base = dict(name='synthetic-' + run[-8:] + '-' + kind + '-' + slug, platform=platform['id'], status='planned',
                        tags=[tag['id']], description=run, site=site['id'])
            path = 'dcim/devices/' if kind == 'device' else 'virtualization/virtual-machines/'
            if kind == 'device': base.update(device_type=dtype['id'], role=role['id'])
            else: base.update(cluster=cluster['id'])
            row = create(path, **base)
            ikey = 'device' if kind == 'device' else 'virtual_machine'
            ipath = 'dcim/interfaces/' if kind == 'device' else 'virtualization/interfaces/'
            interface = create(ipath, **{ikey: row['id'], 'name': 'test0', 'description': run,
                **({'type': 'virtual'} if kind == 'device' else {})})
            ip = '198.51.100.' + str(10 + index * 2 + (kind == 'vm'))
            address = create('ipam/ip-addresses/', address=ip + '/32',
                assigned_object_type='dcim.interface' if kind == 'device' else 'virtualization.vminterface',
                assigned_object_id=interface['id'], description=run)
            nb('PATCH', path + str(row['id']) + '/', dict(primary_ip4=address['id']))
            records.append(dict(kind=kind, path=path, id=row['id'], name=base['name'], slug=slug, ip=ip,
                interfaceid=interface['id'],
                type='dcim.device' if kind == 'device' else 'virtualization.virtualmachine'))
    sync = runpy.run_path(str(ROOT / 'netbox-zabbix-sync.py'))['main'].__globals__
    actual_api = sync['ZabbixAPI']

    class GuardedAPI(actual_api):
        def call(self, method, params):
            if method.endswith('.get'): return super().call(method, params)
            assert method in {'host.create', 'host.update', 'hostinterface.update'}
            if method == 'host.create':
                tags = {t['tag']: t['value'] for t in params['tags']}
                identity = (tags['netbox_object_type'], tags['netbox_id'])
                assert identity in {(r['type'], str(r['id'])) for r in records}
                assert identity not in owned_hosts and params['status'] == 1 and tags['netbox_site'] == run
            elif method == 'host.update':
                assert params['hostid'] in owned_hosts.values() and 'status' not in params
            else:
                assert params['interfaceid'] in {i['interfaceid'] for h in hosts() if h['hostid'] in owned_hosts.values() for i in h['interfaces']}
            result = super().call(method, params)
            if method == 'host.create': owned_hosts[identity] = result['hostids'][0]
            writes.append(dict(method=method, params=params))
            save('platform-rpc.private.json', writes)
            return result

    sync['ZabbixAPI'] = GuardedAPI
    env = dict(ZABBIX_API_TOKEN_FILE='/fixture/secrets/zabbix-api-token', ZABBIX_URL=ZX,
        ZABBIX_GROUP='Linux servers', ZABBIX_TEMPLATE='Linux by Zabbix agent active',
        NETBOX_INCLUDE_VMS='true', NETBOX_VM_GROUP='Virtual machines', NETBOX_VM_TEMPLATE='ICMP Ping',
        NETBOX_TAG_SLUG=run, NETBOX_SITE_SLUGS=run, NETBOX_ZABBIX_HOSTID_FIELD='synthetic_platform_hostid',
        NETBOX_PLATFORM_MAPPING_ENABLED='true', NETBOX_PLATFORM_MAP=json.dumps(MAPPING),
        NETBOX_PLATFORM_PROFILES=json.dumps(PROFILES))

    def reconcile(apply=True, override=None):
        before = len(writes)
        with patch.dict(os.environ, dict(env, **(override or {}))), patch('sys.argv', ['sync'] + (['--apply'] if apply else [])):
            assert sync['main']() == 0
        return writes[before:]

    check('dry-run', reconcile(False) == [], {'writes': 0})
    reconcile()
    matrix = []
    for record in records:
        host = next(h for h in hosts() if h['hostid'] == owned_hosts[(record['type'], str(record['id']))])
        profile = MAPPING[record['slug']]
        actual = nb('GET', record['path'] + str(record['id']) + '/')
        assert actual['primary_ip4']['address'] == record['ip'] + '/32'
        assert str(actual['custom_fields']['synthetic_platform_hostid']) == host['hostid']
        assert host['status'] == '1' and any(g['groupid'] == group_ids[profile] for g in host['hostgroups'])
        assert any(t['templateid'] == template_ids[profile] for t in host['parentTemplates'])
        assert host['interfaces'][0]['ip'] == record['ip']
        matrix.append(dict(kind=record['kind'], platform=record['slug'], profile=profile,
            group=PROFILES[profile]['group'], template=PROFILES[profile]['template']))
    check('matrix', len(owned_hosts) == 6, {'objects': matrix, 'all_disabled': True})
    check('idempotence', reconcile() == [], {'additional_writes': 0})
    first = records[0]; hostid = owned_hosts[(first['type'], str(first['id']))]
    before = next(h for h in hosts() if h['hostid'] == hostid)
    ifaceid = next(i['interfaceid'] for i in before['interfaces'] if i['main'] == '1' and i['type'] == '1')
    local = [{'tag': t['tag'], 'value': t['value']} for t in before['tags']] + [{'tag': 'local-owner', 'value': run}]
    zx('host.update', dict(hostid=hostid, tags=local, description='outside integration responsibility'))
    updated_ip = create('ipam/ip-addresses/', address='203.0.113.20/32', description=run,
        assigned_object_type='dcim.interface', assigned_object_id=first['interfaceid'])
    nb('PATCH', first['path'] + str(first['id']) + '/', dict(primary_ip4=updated_ip['id']))
    calls = reconcile()
    current_hosts = hosts()
    after = next(h for h in current_hosts if h['hostid'] == hostid)
    current_ip = nb('GET', first['path'] + str(first['id']) + '/')['primary_ip4']['address']
    after_interface = next(i for i in after['interfaces'] if i['interfaceid'] == ifaceid)
    matching = [h for h in current_hosts if sync['host_identity'](h) == (first['type'], str(first['id']))]
    check('ip-and-local-tag', [x['method'] for x in calls] == ['hostinterface.update']
        and calls[0]['params']['interfaceid'] == ifaceid and calls[0]['params']['ip'] == '203.0.113.20'
        and current_ip == '203.0.113.20/32' and after_interface['ip'] == '203.0.113.20'
        and after_interface['type'] == '1' and after_interface['main'] == '1' and len(matching) == 1
        and any(t['tag'] == 'local-owner' and t['value'] == run for t in after['tags'])
        and after['description'] == 'outside integration responsibility',
        {'same_host_and_interface': True, 'local_tag_preserved': True,
         'netbox_ip_after': current_ip, 'zabbix_ip_after': after_interface['ip'], 'matching_owned_hosts': len(matching)})
    checkpoint = len(writes)
    current_platform = nb('GET', first['path'] + str(first['id']) + '/')['platform']['id']
    nb('PATCH', first['path'] + str(first['id']) + '/', dict(platform=None))
    try:
        reconcile()
    except RuntimeError as error:
        assert 'platform' in str(error)
    else: raise AssertionError('Unmapped platform unexpectedly accepted')
    check('unknown-platform-before-writes', len(writes) == checkpoint, {'additional_writes': 0})
    nb('PATCH', first['path'] + str(first['id']) + '/', dict(platform=current_platform))
    other_platform = nb('GET', records[2]['path'] + str(records[2]['id']) + '/')['platform']['id']
    nb('PATCH', first['path'] + str(first['id']) + '/', dict(platform=other_platform))
    try:
        reconcile()
    except RuntimeError as error:
        assert 'group' in str(error) or 'profile' in str(error) or 'template' in str(error)
    else: raise AssertionError('Existing host platform was silently migrated')
    check('migration-refused-before-writes', len(writes) == checkpoint, {'additional_writes': 0})
    nb('PATCH', first['path'] + str(first['id']) + '/', dict(platform=current_platform))
    try:
        reconcile(override={'NETBOX_PLATFORM_MAPPING_ENABLED': 'false', 'NETBOX_PLATFORM_MAP': '{}', 'NETBOX_PLATFORM_PROFILES': '{}'})
    except RuntimeError as error:
        assert 'silently remove' in str(error)
    else: raise AssertionError('Mapping downgrade unexpectedly accepted')
    check('guard-and-reapply', len(writes) == checkpoint and reconcile() == [], {'additional_writes': 0})
    outside = [h for h in hosts() if h['hostid'] not in owned_hosts.values()]
    def config_fingerprint(values):
        values = copy.deepcopy(values)
        for host in values:
            for interface in host['interfaces']:
                for key in ('available', 'error', 'errors_from', 'disable_until'):
                    interface.pop(key, None)
            for key in ('interfaces', 'hostgroups', 'parentTemplates', 'tags'):
                host[key].sort(key=lambda value: json.dumps(value, sort_keys=True))
        return sorted(values, key=lambda value: value['hostid'])
    check('outside-and-alerts', config_fingerprint(outside) == config_fingerprint(baseline_hosts)
          and zx('alert.get', dict(output=['alertid'])) == alerts_before,
          {'non_owned_hosts_unchanged': True, 'no_notification_media': True})
    save('platform-result.json', dict(result='PASS', stages=events, matrix=matrix,
        cleanup='Dedicated fixture teardown by verified Docker project IDs; do not delete by host name',
        limitations=['No actual Linux/Windows agent or ICMP collector target was exercised',
                     'No LAB01/OPS access; not a deployment acceptance test']))
    token.delete()
    zx('user.logout', [])
    print('REAL_PLATFORM_API_MATRIX_PASS', flush=True)


if __name__ == '__main__':
    main()
