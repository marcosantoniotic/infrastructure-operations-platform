#!/usr/bin/env python3
"""Real API acceptance INSIDE a fresh synthetic-ip-* fixture only.

Uses the existing disposable fixture builder, never an existing application DB.
No mocks of NetBox models or API responses. A forwarding write guard restricts
the actual reconciler to the exact newly created IDs. Hosts are disabled during
reconciliation; only synthetic history-witness setup briefly enables owned hosts.
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
import time
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
    'windows-active': {'group': 'Windows servers', 'templates': ['Windows by Zabbix agent active', 'ICMP Ping']},
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
        scheduled_sync=False, all_test_hosts_disabled_at_initial_snapshot=True,
        history_witness_setup_temporarily_enables_owned_hosts=True, ports_published=0, mocks=False))
    group_ids, template_ids = {}, {}
    for name, profile in PROFILES.items():
        found = zx('hostgroup.get', dict(output=['groupid'], filter={'name': [profile['group']]}))
        if not found:
            found = [{'groupid': zx('hostgroup.create', dict(name=profile['group']))['groupids'][0]}]
        assert len(found) == 1
        group_ids[name] = found[0]['groupid']
        template_ids[name] = []
        for template_name in profile.get('templates', [profile.get('template')]):
            templates = zx('template.get', dict(output=['templateid'], filter={'name': [template_name]}))
            assert len(templates) == 1, template_name
            template_ids[name].append(templates[0]['templateid'])
            items = zx('item.get', dict(output=['type', 'key_'], templateids=[templates[0]['templateid']]))
            assert items
            if template_name == 'ICMP Ping':
                assert all(i['type'] == '3' and i['key_'].startswith('icmpping') for i in items)
            else:
                assert any(i['type'] == '7' for i in items)
    windows_id = template_ids['windows-active'][0]
    rules = zx('discoveryrule.get', dict(output=['itemid', 'key_', 'type'], templateids=[windows_id],
        selectItems=['key_', 'type'], filter={'key_': ['service.discovery']}))
    assert len(rules) == 1 and rules[0]['type'] == '7'
    assert any(i['key_'].startswith('service.info[') and i['type'] == '7' for i in rules[0]['items'])
    win = zx('template.get', dict(output=['templateid'], templateids=[windows_id], selectMacros=['macro']))
    macro_names = {m['macro'] for m in win[0]['macros']}
    assert {'{$SERVICE.NAME.MATCHES}', '{$SERVICE.NAME.NOT_MATCHES}'} <= macro_names
    check('windows-services-capability', True, {'official_template': 'Windows by Zabbix agent active',
        'active_service_discovery': True, 'service_state_prototypes': True, 'host_macro_filters': True,
        'actual_windows_service_collection_tested': False, 'extra_ad_iis_sql_templates': False})
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
        assert set(template_ids[profile]) <= {t['templateid'] for t in host['parentTemplates']}
        assert host['interfaces'][0]['ip'] == record['ip']
        matrix.append(dict(kind=record['kind'], platform=record['slug'], profile=profile,
            group=PROFILES[profile]['group'], templates=PROFILES[profile].get('templates', [PROFILES[profile].get('template')])) )
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

    # Explicit GUI profile migration on the same six owned hosts; preserve IDs/history.
    field_env = dict(env, NETBOX_PROFILE_SOURCE='custom-field', NETBOX_PROFILE_FIELD='synthetic_monitoring_profile',
        NETBOX_PROFILE_FIELD_LABEL='Perfil de monitoramento', NETBOX_PROFILE_CHOICE_SET='synthetic-monitoring-profiles',
        NETBOX_PROFILE_VALUES=json.dumps({'linux':'linux-active','windows':'windows-active','icmp':'network-icmp'}),
        NETBOX_PROFILE_LABELS=json.dumps({'linux':'Linux','windows':'Windows','icmp':'ICMP'}))
    from extras.models import CustomField, CustomFieldChoiceSet
    counts = (CustomField.objects.count(), CustomFieldChoiceSet.objects.count())
    def prepare():
        capture = io.StringIO()
        with patch.dict(os.environ, dict(field_env, ZABBIX_API_TOKEN_FILE='/not-present-proof-schema-only')), \
             patch('sys.argv', ['sync', '--prepare-monitoring-field']), patch('sys.stdout', capture):
            assert sync['main']() == 0
        return json.loads(capture.getvalue().strip().splitlines()[-1])
    prepared = prepare(); assert prepared['created'] is True
    assert (CustomField.objects.count(), CustomFieldChoiceSet.objects.count()) == (counts[0]+1, counts[1]+1)
    again = prepare(); assert again['created'] is False and again['field_id'] == prepared['field_id']
    field = CustomField.objects.get(pk=prepared['field_id'])
    assert field.type == 'select' and field.default is None and not field.required
    assert set(field.object_types.values_list('app_label', 'model')) == {('dcim','device'),('virtualization','virtualmachine')}
    assert dict(field.choice_set.choices) == {'linux':'Linux','windows':'Windows','icmp':'ICMP'}
    assert all(nb('GET', r['path']+str(r['id'])+'/')['custom_fields'].get('synthetic_monitoring_profile') is None for r in records)
    check('prepare-selection-schema-idempotent', True, {'type':'select','object_types':2,
        'labels':['Linux','Windows','ICMP'],'objects_not_seeded':True,'token_not_needed':True})
    original_choices = copy.deepcopy(field.choice_set.extra_choices)
    try:
        CustomFieldChoiceSet.objects.filter(pk=prepared['choice_set_id']).update(extra_choices=[['linux','Changed']])
        try: prepare()
        except RuntimeError as error: assert 'custom field' in str(error)
        else: raise AssertionError('Conflicting existing schema was overwritten')
        assert CustomFieldChoiceSet.objects.get(pk=prepared['choice_set_id']).extra_choices == [['linux','Changed']]
    finally:
        CustomFieldChoiceSet.objects.filter(pk=prepared['choice_set_id']).update(extra_choices=original_choices)
    with patch.dict(os.environ, field_env):
        fault_config = dict(sync['load_field_selection'](PROFILES), name='synthetic_atomic_failure', choice_set='synthetic-atomic-failure')
    before_fault = (CustomField.objects.count(), CustomFieldChoiceSet.objects.count())
    with patch.dict(sync, validate_profile_field=lambda *args: (_ for _ in ()).throw(RuntimeError('synthetic schema fault'))):
        try: sync['prepare_profile_field'](fault_config)
        except RuntimeError as error: assert str(error)=='synthetic schema fault'
        else: raise AssertionError('Synthetic transaction fault did not propagate')
    assert (CustomField.objects.count(), CustomFieldChoiceSet.objects.count()) == before_fault
    assert not CustomField.objects.filter(name=fault_config['name']).exists()
    assert not CustomFieldChoiceSet.objects.filter(name=fault_config['choice_set']).exists()
    check('schema-conflict-and-atomic-rollback', True, {'conflict_not_overwritten':True,
        'injected_post_save_fault_rolled_back':True,'zabbix_writes':0})
    checkpoint = len(writes)
    def field_reconcile(apply=True, override=None):
        return reconcile(apply, dict(field_env, **(override or {})))
    try: field_reconcile()
    except RuntimeError as error: assert 'monitoring custom field' in str(error)
    else: raise AssertionError('Blank explicit profile was accepted')
    assert len(writes) == checkpoint
    for record in records:
        value = {'rhel':'linux','windows-server':'windows','routeros':'icmp'}[record['slug']]
        nb('PATCH', record['path']+str(record['id'])+'/', {'custom_fields':{'synthetic_monitoring_profile':value}})
    before_field_hosts = copy.deepcopy(hosts())
    check('explicit-field-dry-run', field_reconcile(False) == [], {'writes':0})
    field_calls = field_reconcile()
    assert len(field_calls) == 6 and all(c['method']=='host.update' and set(c['params'])=={'hostid','tags'} for c in field_calls)
    current = hosts()
    for prior in before_field_hosts:
        if prior['hostid'] not in owned_hosts.values():
            continue  # Non-owned volatile availability is handled by config_fingerprint below.
        newer = next(h for h in current if h['hostid']==prior['hostid'])
        for key in ['hostid','host','name','status','interfaces','hostgroups','parentTemplates','description']:
            assert newer.get(key) == prior.get(key)
        if prior['hostid'] in owned_hosts.values():
            assert any(t['tag']=='netbox_monitoring_source' and t['value']=='custom-field:synthetic_monitoring_profile' for t in newer['tags'])
    check('explicit-field-adoption', True, {'same_six_hosts':True,'tag_only_updates':6,'interfaces_templates_groups_preserved':True})
    check('explicit-field-idempotence', field_reconcile()==[], {'additional_writes':0})
    first_path = first['path']+str(first['id'])+'/'
    checkpoint = len(writes)
    nb('PATCH', first_path, {'custom_fields':{'synthetic_monitoring_profile':None}})
    try: field_reconcile()
    except RuntimeError as error: assert 'monitoring custom field' in str(error)
    else: raise AssertionError('Empty field was accepted')
    nb('PATCH', first_path, {'custom_fields':{'synthetic_monitoring_profile':'windows'}})
    try: field_reconcile()
    except RuntimeError as error: assert any(k in str(error) for k in ['group','template','profile'])
    else: raise AssertionError('Existing profile was silently migrated')
    nb('PATCH', first_path, {'custom_fields':{'synthetic_monitoring_profile':'linux'}})
    try: reconcile()
    except RuntimeError as error: assert 'custom-field source' in str(error)
    else: raise AssertionError('Custom-field source was silently removed')
    assert len(writes) == checkpoint
    check('field-migration-and-downgrade-guards', field_reconcile()==[], {'blank_and_profile_change_refused':True,'platform_downgrade_refused':True,'additional_writes':0})
    # Additive migration on actual APIs; no live agent or Windows OS is simulated.
    icmp_records = [r for r in records if r['slug'] == 'routeros']
    transition_env = dict(field_env, NETBOX_PROFILE_TRANSITIONS=json.dumps([
        {'from':'network-icmp','to':'windows-active'}]), NETBOX_PROFILE_READY='{}')
    def transition_run(expected=0, apply=True):
        previous = len(writes)
        with patch.dict(os.environ, transition_env), patch('sys.argv', ['sync'] + (['--apply'] if apply else [])):
            assert sync['main']() == expected
        return writes[previous:]
    preserved = {}
    for record in icmp_records:
        hid = owned_hosts[(record['type'], str(record['id']))]
        host = next(h for h in hosts() if h['hostid'] == hid)
        # Bootstrap setup only in this wholly synthetic fixture, never in the reconciler.
        tags = [{'tag':t['tag'],'value':t['value']} for t in host['tags']] + [{'tag':'local-transition-owner','value':run}]
        zx('host.update', dict(hostid=hid, tags=tags, macros=[{'macro':'{$SYNTHETIC.LOCAL}','value':'preserve'}],
            tls_accept=2, tls_psk_identity='synthetic-'+hid, tls_psk='ab'*32))
        item = zx('item.create', dict(hostid=hid, name='Synthetic history witness',
            key_='synthetic.profile.history', type=2, value_type=3, delay='0', history='30d', trends='30d'))['itemids'][0]
        # history.push needs an enabled trapper item. No media/integration exists here.
        zx('host.update', dict(hostid=hid, status=0))
        # Configuration cache is asynchronous. Keep every response; do not fake
        # history or treat an HTTP/JSON-RPC success as accepted item data.
        attempts=[]; deadline=time.monotonic()+90
        while True:
            pushed = zx('history.push', [{'itemid':item, 'clock':int(time.time()), 'value':'42'}])
            attempts.append(pushed);save('history-push-'+hid+'.private.json',attempts)
            errors=[row['error'] for row in pushed['data'] if row.get('error')]
            if not errors:
                assert len(pushed['data'])==1 and str(pushed['data'][0]['itemid'])==str(item)
                break
            # Only newly-created, confirmed owned entities, with admin API auth.
            # Any other failure is immediate; persistent cache/permission errors fail.
            assert all(message in {'No permissions to referred object or it does not exist.',
                'Host is not monitored.', 'Item is disabled.'} for message in errors), errors
            assert time.monotonic()<deadline, errors
            time.sleep(3)
        zx('host.update', dict(hostid=hid, status=1))
        preserved[hid] = dict(host=next(h for h in hosts() if h['hostid']==hid),
            items=zx('item.get',dict(output=['itemid','key_','templateid','history','trends'],hostids=[hid])),
            macros=zx('usermacro.get',dict(output=['macro','value'],hostids=[hid])), witness=item)
        nb('PATCH', record['path']+str(record['id'])+'/', {'custom_fields':{'synthetic_monitoring_profile':'windows'}})
    check('transition-readiness-blocked', transition_run(2)==[], {'target_hosts':2,'writes':0})
    transition_env['NETBOX_PROFILE_READY'] = json.dumps({r['type']+':'+str(r['id']):
        {'profile':'windows-active','hostid':owned_hosts[(r['type'],str(r['id']))]} for r in icmp_records})
    check('transition-dry-run', transition_run(apply=False)==[], {'writes':0})
    changed = transition_run()
    assert len(changed)==2 and all(c['method']=='host.update' and
        set(c['params'])=={'hostid','groups','templates','tags'} for c in changed)
    for hid, prior in preserved.items():
        after = next(h for h in hosts() if h['hostid']==hid)
        assert after['hostid']==prior['host']['hostid'] and after['interfaces']==prior['host']['interfaces']
        assert group_ids['windows-active'] in {g['groupid'] for g in after['hostgroups']}
        assert group_ids['network-icmp'] not in {g['groupid'] for g in after['hostgroups']}
        assert set(template_ids['windows-active']) <= {t['templateid'] for t in after['parentTemplates']}
        assert any(t['tag']=='local-transition-owner' and t['value']==run for t in after['tags'])
        items_after = zx('item.get',dict(output=['itemid','key_','templateid','history','trends'],hostids=[hid]))
        assert all(row in items_after for row in prior['items'])
        assert zx('usermacro.get',dict(output=['macro','value'],hostids=[hid]))==prior['macros']
        deadline=time.monotonic()+30
        while not zx('history.get',dict(output='extend',history=3,itemids=[prior['witness']])):
            assert time.monotonic()<deadline
            time.sleep(1)
        history=zx('history.get',dict(output='extend',history=3,itemids=[prior['witness']]))
        assert any(row['value']=='42' for row in history)
    check('transition-same-host-history', True, {'objects':2,'same_host_interface_item_ids':True,
        'old_item_retention_and_local_tags_macros_preserved':True,'real_history_value':42,
        'templates_unlinked_or_cleared':0,'actual_windows_agent_tested':False})
    check('transition-idempotence', transition_run()==[], {'writes':0})
    # Unsupported removal affects only its object. The second object's rename still reconciles.
    one,two=icmp_records
    nb('PATCH',one['path']+str(one['id'])+'/',{'custom_fields':{'synthetic_monitoring_profile':'icmp'}})
    nb('PATCH',two['path']+str(two['id'])+'/',{'name':two['name']+'-renamed'})
    transition_env['NETBOX_PROFILE_TRANSITIONS']=json.dumps([
        {'from':'network-icmp','to':'windows-active'},{'from':'windows-active','to':'network-icmp'}])
    partial=transition_run(2)
    assert len(partial)==1 and partial[0]['params']['hostid']==owned_hosts[(two['type'],str(two['id']))]
    check('transition-pending-isolated',True,{'removal_blocked':True,'unrelated_rename_applied':True,'pending_host_not_disabled':True})
    nb('PATCH',one['path']+str(one['id'])+'/',{'custom_fields':{'synthetic_monitoring_profile':'windows'}})
    check('transition-recovery',transition_run()==[],{'writes':0})
    checkpoint=len(writes)
    try: field_reconcile()
    except RuntimeError as error: assert 'installed profile reconciliation' in str(error)
    else: raise AssertionError('Installed reconciliation guard was bypassed')
    check('transition-feature-removal-guard',len(writes)==checkpoint,{'writes':0})
    # Exercise the actual NetBox edit form, not a drawing or replacement screenshot.
    from django.test import Client
    client = Client(HTTP_HOST='netbox.functional.example.test')
    client.force_login(get_user_model().objects.get(username='synthetic-admin'))
    vm = next(r for r in records if r['kind']=='vm')
    form = client.get('/virtualization/virtual-machines/'+str(vm['id'])+'/edit/', secure=True)
    assert form.status_code == 200
    html = form.content.decode()
    (out/'monitoring-field-form.private.html').write_text(html)
    assert 'cf_synthetic_monitoring_profile' in html and 'Perfil de monitoramento' in html
    # APISelect deliberately renders only selected choices. Exercise its actual
    # authenticated AJAX endpoint rather than requiring static option markup.
    choice_url = '/api/extras/custom-field-choice-sets/'+str(prepared['choice_set_id'])+'/choices/'
    assert choice_url in html
    choice_response = client.get(choice_url, secure=True)
    assert choice_response.status_code == 200
    assert {row['id']:row['display'] for row in choice_response.json()['results']} == {'linux':'Linux','windows':'Windows','icmp':'ICMP'}
    check('real-netbox-edit-form', True, {'http_status':200,'selection_present':True,'labels':['Linux','Windows','ICMP'],
        'ajax_choices_status':200,'rendered_by':'Django real view and DB; authenticated synthetic test client','screenshot_produced':False})
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
        custom_field={'type':'select','labels':['Linux','Windows','ICMP'],'prepared':True,'migration_tag_only':True},
        windows_services={'capability_verified':True,'actual_collection_tested':False},
        limitations=['No actual Linux/Windows agent or ICMP collector target was exercised',
                     'No LAB01/OPS access; not a deployment acceptance test']))
    token.delete()
    zx('user.logout', [])
    print('REAL_PLATFORM_API_MATRIX_PASS', flush=True)


if __name__ == '__main__':
    main()
