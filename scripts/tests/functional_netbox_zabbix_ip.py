#!/usr/bin/env python3
"""Real API acceptance in a NEW disposable fixture (not a production runner).

Execute as root *inside the fixture's NetBox container*. /fixture contains its
unique manifest, unchanged sync source and private evidence directory. No host
ports, external Docker networks, scheduled sync, real inventory or alert media.
This is not a connectivity/agent test. No API is mocked; the write guard wraps
the production JSON-RPC client, forwards permitted requests, and refuses any
mutation outside the device/host/interface created in this execution.
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
from zoneinfo import ZoneInfo

if not __debug__:
    raise SystemExit('Refusing optimized Python: fixture safety assertions must remain enabled')

import requests

ROOT = Path('/fixture')
OUT = ROOT / 'evidence'
MANIFEST = json.loads((ROOT / 'manifest.json').read_text())
RUN = MANIFEST['run_id']
NB = 'https://netbox.functional.example.test/api/'
ZX = 'https://zabbix.functional.example.test/api_jsonrpc.php'
A, B = '198.51.100.10', '203.0.113.20'
CA = '/tls/ca.crt'
SOURCE = ROOT / 'netbox-zabbix-sync.py'
EVENTS, LEDGER = [], []
z_token = None
nb_token = None
hostid = interfaceid = deviceid = None
phase = 'bootstrap'
rpc_writes = []
baseline_hosts = None
bootstrap_token = None


def now():
    return datetime.now(timezone.utc).isoformat()


def save(name, data):
    path = OUT / name
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding='utf-8')
    path.chmod(0o600)


def check(stage, expected, condition, observed):
    event = dict(time_utc=now(), time_local=datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
        stage=stage, expected=expected, observed=observed, result='PASS' if condition else 'FAIL')
    EVENTS.append(event)
    save('events.json', EVENTS)
    print(json.dumps(event), flush=True)
    if not condition:
        raise AssertionError(stage)


def nb(method, path, body=None, missing_ok=False):
    r = requests.request(method, NB + path, headers={'Authorization': nb_token},
        json=body, verify=CA, timeout=30)
    if missing_ok and r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json() if r.content else None


def all_nb(path):
    data = nb('GET', path + '?limit=1000')
    if data['next'] is not None:
        raise RuntimeError('Unexpected large fixture; refusing scope')
    return data['results']


def create(path, body, marker='description'):
    assert body[marker] == RUN
    result = nb('POST', path, body)
    LEDGER.append(dict(path=path, id=result['id'], marker=marker, value=RUN))
    save('ownership-ledger.json', LEDGER)
    return result


def zx(method, params, token=True):
    headers = {'Authorization': 'Bearer ' + z_token} if token else {}
    r = requests.post(ZX, json=dict(jsonrpc='2.0', method=method, params=params, id=1),
        headers=headers, verify=CA, timeout=30)
    r.raise_for_status()
    data = r.json()
    if 'error' in data:
        raise RuntimeError(method + ': ' + json.dumps(data['error']))
    return data['result']


def hosts():
    return zx('host.get', dict(output=['hostid', 'host', 'name', 'status', 'description'],
        selectTags='extend', selectInterfaces='extend', selectHostGroups=['groupid'],
        selectParentTemplates=['templateid']))


def snapshot(label):
    device = nb('GET', f'dcim/devices/{deviceid}/')
    h = next(h for h in hosts() if h['hostid'] == hostid)
    value = dict(device_id=device['id'], primary_ip=device['primary_ip4']['address'],
        stored_hostid=device['custom_fields'].get('synthetic_zabbix_hostid'), host=h)
    save(label + '.json', value)
    return value


def fingerprint(values):
    # host.get contains availability/error timestamps on interfaces: exclude those
    # runtime fields, retain all returned configuration for non-owned hosts.
    data = copy.deepcopy(values)
    for h in data:
        for i in h.get('interfaces', []):
            for key in ('available', 'error', 'errors_from', 'disable_until'):
                i.pop(key, None)
        # These API collections are unordered. Tag updates may change row order
        # without changing any value; retain every returned configuration field.
        for key in ('tags', 'interfaces', 'hostgroups', 'parentTemplates'):
            if key in h:
                h[key].sort(key=lambda item: json.dumps(item, sort_keys=True))
    data.sort(key=lambda h: str(h['hostid']))
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def has_tag(tags, wanted):
    # Match the tag's public input fields, not server-added read-only metadata.
    matches = [t for t in tags if t['tag'] == wanted['tag']]
    return len(matches) == 1 and matches[0]['value'] == wanted['value']


def check_comparator():
    baseline = [dict(hostid='synthetic-host', tags=[dict(tag='local', value='keep'), dict(tag='managed', value='planned')],
        interfaces=[dict(interfaceid='a', ip=A, port='10050'), dict(interfaceid='b', ip='192.0.2.99', port='10051')])]
    reordered = copy.deepcopy(baseline)
    reordered[0]['tags'].reverse()
    reordered[0]['interfaces'].reverse()
    assert fingerprint(baseline) == fingerprint(reordered)
    for key, value in (('ip', B), ('port', '9999')):
        changed = copy.deepcopy(baseline)
        changed[0]['interfaces'][0][key] = value
        assert fingerprint(baseline) != fingerprint(changed)
    changed = copy.deepcopy(baseline)
    changed[0]['tags'][0]['value'] = 'lost'
    assert fingerprint(baseline) != fingerprint(changed)
    changed = copy.deepcopy(baseline)
    changed[0]['interfaces'].pop()
    assert fingerprint(baseline) != fingerprint(changed)
    changed = copy.deepcopy(baseline)
    changed[0]['hostid'] = 'different-host'
    assert fingerprint(baseline) != fingerprint(changed)
    save('comparator-self-check.json', dict(order_ignored=True, ip_change_detected=True,
        port_change_detected=True, tag_value_change_detected=True, lost_interface_detected=True, host_identity_change_detected=True))


def reconcile(label, apply=True):
    global phase
    phase = label
    before = len(rpc_writes)
    from dcim.models import Device
    from virtualization.models import VirtualMachine
    scope = list(Device.objects.filter(tags__slug=RUN, site__slug=RUN).values_list('pk', flat=True))
    assert scope == [deviceid] and Device.objects.count() == 1
    assert VirtualMachine.objects.count() == 0
    env = dict(ZABBIX_API_TOKEN_FILE='/fixture/secrets/zabbix-api-token', ZABBIX_URL=ZX,
        ZABBIX_GROUP='Linux servers', ZABBIX_TEMPLATE='ICMP Ping', NETBOX_TAG_SLUG=RUN,
        NETBOX_ZABBIX_HOSTID_FIELD='synthetic_zabbix_hostid', NETBOX_INCLUDE_VMS='false',
        NETBOX_SITE_SLUGS=RUN, REQUESTS_CA_BUNDLE=CA, SSL_CERT_FILE=CA)
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    sync['LOG'].addHandler(handler)
    sync['LOG'].setLevel(logging.INFO)
    try:
        with patch.dict(os.environ, env), patch('sys.argv', ['sync'] + (['--apply'] if apply else [])):
            assert sync['main']() == 0
    finally:
        sync['LOG'].removeHandler(handler)
        (OUT / (label + '.log')).write_text(output.getvalue())
    writes = rpc_writes[before:]
    save(label + '-rpc.json', writes)
    return output.getvalue(), writes


def cleanup():
    global phase
    phase = 'cleanup'
    errors = []
    if hostid is not None:
        try:
            current = next((h for h in hosts() if h['hostid'] == hostid), None)
            if current:
                tags = {t['tag']: t['value'] for t in current['tags']}
                assert current['host'] == RUN and tags['source'] == 'netbox'
                assert tags['netbox_id'] == str(deviceid) and tags['netbox_object_type'] == 'dcim.device'
                assert json.loads((OUT / 'zabbix-ownership.json').read_text())['hostid'] == hostid
                zx('host.delete', [hostid])
            assert not any(h['hostid'] == hostid for h in hosts())
        except Exception as e:
            errors.append('Zabbix cleanup: ' + str(e))
    # References removed only from the exact device owned by this ledger.
    if deviceid is not None:
        try:
            d = nb('GET', f'dcim/devices/{deviceid}/', missing_ok=True)
            if d:
                assert d['description'] == RUN
                nb('PATCH', f'dcim/devices/{deviceid}/', dict(primary_ip4=None, primary_ip6=None))
        except Exception as e:
            errors.append('Primary reference cleanup: ' + str(e))
    for obj in reversed(LEDGER):
        try:
            path = f"{obj['path']}{obj['id']}/"
            current = nb('GET', path, missing_ok=True)
            if current:
                assert current[obj['marker']] == obj['value']
                nb('DELETE', path)
            assert nb('GET', path, missing_ok=True) is None
        except Exception as e:
            errors.append(f"NetBox cleanup {obj['path']}{obj['id']}: {e}")
    if baseline_hosts is not None:
        try:
            assert fingerprint(hosts()) == fingerprint(baseline_hosts)
        except Exception as e:
            errors.append('Baseline Zabbix configuration mismatch: ' + str(e))
    save('cleanup.json', dict(time=now(), errors=errors, owned_ids=LEDGER,
        synthetic_hostid=hostid, clean=not errors))
    return errors


def main():
    global nb_token, z_token, deviceid, hostid, interfaceid, baseline_hosts, sync, bootstrap_token
    assert RUN.startswith('synthetic-ip-')
    assert NB.endswith('.example.test/api/') and ZX.endswith('.example.test/api_jsonrpc.php')
    assert os.geteuid() == 0 and os.environ.get('REQUESTS_CA_BUNDLE') == CA
    os.umask(0o077)
    check_comparator()
    save('execution.json', dict(started_utc=now(), timezone='America/Sao_Paulo',
        revision=MANIFEST['revision'], run_id=RUN, sync_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        mode='real NetBox REST + real Zabbix JSON-RPC; unmodified sync ORM; guarded one-shot --apply',
        address_a=A, address_b=B, scheduled_sync=False, host_enabled=False, published_ports=0))
    # A running container is not yet an initialized application. Do not bootstrap
    # identities while migrations or the vendor superuser setup are in progress.
    requests.get(NB.replace('/api/', '/login/'), verify=CA, timeout=30).raise_for_status()
    assert zx('apiinfo.version', {}, token=False).startswith('7.4.')
    sys.path.insert(0, '/opt/netbox/netbox')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netbox.settings')
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from users.models import Token
    user = get_user_model().objects.get(username='synthetic-admin')
    token = (Token.objects.create(user=user, description=RUN))
    bootstrap_token = token
    save('bootstrap-identity.json', dict(token_id=token.pk, user_id=user.pk, run_id=RUN))
    nb_token = (token.get_auth_header_prefix() + token.token)
    private = json.loads((ROOT / 'secrets/bootstrap.json').read_text())
    try:
        auth = zx('user.login', {'username': 'Admin', 'password': 'zabbix'}, token=False)
        current_password = 'zabbix'
    except RuntimeError:
        auth = zx('user.login', {'username': 'Admin', 'password': private['admin_password']}, token=False)
        current_password = private['admin_password']
    z_token = auth
    # Rotate the vendor bootstrap password in this fresh, private database only.
    admin = zx('user.get', {'output': ['userid'], 'filter': {'username': ['Admin']}})
    assert len(admin) == 1
    zx('user.update', dict(userid=admin[0]['userid'], passwd=private['admin_password'], current_passwd=(current_password)))
    z_token = zx('user.login', {'username': 'Admin', 'password': private['admin_password']}, token=False)
    (ROOT / 'secrets/zabbix-api-token').write_text(z_token)
    save('versions.json', dict(netbox=str(settings.VERSION),
        zabbix=zx('apiinfo.version', {}, token=False),
        topology=importlib.metadata.version('netbox-topology-views'),
        qrcode=importlib.metadata.version('netbox-qrcode'), images=MANIFEST['images']))
    baseline_counts = {p: len(all_nb(p)) for p in ('dcim/devices/', 'virtualization/virtual-machines/',
        'ipam/ip-addresses/', 'dcim/sites/', 'dcim/manufacturers/', 'dcim/device-types/',
        'dcim/device-roles/', 'extras/tags/', 'extras/custom-fields/')}
    baseline_hosts = hosts()
    save('baseline.json', dict(netbox_counts=baseline_counts, zabbix_hosts=baseline_hosts,
        zabbix_fingerprint=fingerprint(baseline_hosts), cleanup_plan='exact ledger IDs + marker/ownership, reverse dependency order; no name-only deletion'))
    assert not any(baseline_counts.values())
    assert not any(any(t['tag'] == 'source' and t['value'] == 'netbox' for t in h['tags']) for h in baseline_hosts)
    media = zx('user.get', {'output': ['userid'], 'selectMedias': 'extend'})
    media_count = sum(len(u.get('medias', [])) for u in media)
    alerts_before = len(zx('alert.get', {'output': ['alertid']}))
    check('preflight', 'empty NetBox fixture, no managed Zabbix hosts or notification media',
        media_count == 0, dict(netbox_counts=baseline_counts,
        managed_hosts=0, real_pending=0, scheduled_sync=False, notification_media=media_count,
        alerts=alerts_before))
    result = 'FAIL'
    failure = None
    try:
        site = create('dcim/sites/', dict(name=RUN, slug=RUN, description=RUN))
        manufacturer = create('dcim/manufacturers/', dict(name=RUN, slug=RUN, description=RUN))
        dtype = create('dcim/device-types/', dict(model=RUN, slug=RUN, manufacturer=manufacturer['id'], description=RUN))
        role = create('dcim/device-roles/', dict(name=RUN, slug=RUN, color='9e9e9e', description=RUN))
        tag = create('extras/tags/', dict(name=RUN, slug=RUN, color='9e9e9e', description=RUN))
        create('extras/custom-fields/', dict(name='synthetic_zabbix_hostid', label='Synthetic Zabbix Host ID',
            type='text', object_types=['dcim.device'], description=RUN))
        device = create('dcim/devices/', dict(name=RUN, site=site['id'], device_type=dtype['id'],
            role=role['id'], status='planned', tags=[tag['id']], description=RUN))
        deviceid = device['id']
        interface = create('dcim/interfaces/', dict(device=deviceid, name='synthetic-agent', type='virtual', description=RUN))
        ip_a = create('ipam/ip-addresses/', dict(address=A + '/32', assigned_object_type='dcim.interface',
            assigned_object_id=interface['id'], description=RUN))
        nb('PATCH', f'dcim/devices/{deviceid}/', dict(primary_ip4=ip_a['id']))
        check('A', 'one selected synthetic device with primary IP A; status planned',
            nb('GET', f'dcim/devices/{deviceid}/')['primary_ip4']['address'] == A + '/32',
            dict(device_id=deviceid, primary_ip=A, selected_tag=RUN, status='planned'))
        sync = runpy.run_path(str(SOURCE))['main'].__globals__
        original_api = sync['ZabbixAPI']

        class GuardedAPI(original_api):
            def call(self, method, params):
                if method.endswith('.get'):
                    return super().call(method, params)
                assert method in ('host.create', 'host.update', 'hostinterface.update')
                if method == 'host.create':
                    assert hostid is None and params['host'] == RUN and params['status'] == 1
                    tags = {t['tag']: t['value'] for t in params['tags']}
                    assert tags['netbox_id'] == str(deviceid) and tags['netbox_site'] == RUN
                    assert not any(h['host'] == RUN for h in hosts())
                elif method == 'host.update':
                    assert str(params['hostid']) == str(hostid) and hostid is not None
                else:
                    assert str(params['interfaceid']) == str(interfaceid) and interfaceid is not None
                current = next((h for h in hosts() if h['hostid'] == hostid), None)
                if current is not None:
                    assert current['host'] == RUN and current['status'] == '1'
                    assert sync['host_identity'](current) == ('dcim.device', str(deviceid))
                result = super().call(method, params)
                record = dict(time=now(), phase=phase, method=method, params=params, result=result)
                rpc_writes.append(record)
                save('rpc-writes.json', rpc_writes)
                if method == 'host.create':
                    save('zabbix-ownership.json', dict(hostid=result['hostids'][0], deviceid=deviceid, run_id=RUN))
                return result

        sync['ZabbixAPI'] = GuardedAPI
        dry_log, dry_writes = reconcile('B-dry-run', apply=False)
        check('B-preflight', 'dry-run plans one creation, no writes', not dry_writes and 'changes=1' in dry_log,
            dict(writes=len(dry_writes), log=dry_log.strip()))
        log, writes = reconcile('B-create')
        matching = [h for h in hosts() if h['host'] == RUN]
        # Recover ID from the mutation ledger even if a subsequent check fails.
        hostid = json.loads((OUT / 'zabbix-ownership.json').read_text())['hostid']
        assert len(matching) == 1
        agent = next(i for i in matching[0]['interfaces'] if i['type'] == '1' and i['main'] == '1')
        interfaceid = agent['interfaceid']
        initial = snapshot('C-initial')
        check('B-C', 'exactly one disabled host; primary agent A; host ID persisted',
            matching[0]['hostid'] == hostid and matching[0]['status'] == '1' and agent['ip'] == A
            and str(initial['stored_hostid']) == str(hostid),
            dict(device_id=deviceid, hostid=hostid, interfaceid=interfaceid, ip=A, duplicates=0, status=1))
        local_tag = dict(tag='local-test-owner', value=RUN)
        # API output includes read-only metadata (e.g. automatic), not accepted
        # in host.update input. Preserve tag/value, not response-only fields.
        local_tags = [dict(tag=t['tag'], value=t['value']) for t in matching[0]['tags']]
        zx('host.update', dict(hostid=hostid, tags=local_tags + [local_tag], description=RUN + ': local description'))
        secondary = zx('hostinterface.create', dict(hostid=hostid, type=1, main=0, useip=1,
            ip='192.0.2.99', dns='', port='10051'))['interfaceids'][0]
        before = snapshot('D-local-state')
        check('D', 'unmanaged tag, description and secondary interface established',
            has_tag(before['host']['tags'], local_tag) and before['host']['description'] == RUN + ': local description'
            and any(i['interfaceid'] == secondary and i['main'] == '0' and i['port'] == '10051'
                for i in before['host']['interfaces']),
            dict(local_tag=local_tag, secondary_interfaceid=secondary, description=before['host']['description']))
        ip_b = create('ipam/ip-addresses/', dict(address=B + '/32', assigned_object_type='dcim.interface',
            assigned_object_id=interface['id'], description=RUN))
        # Only this PATCH changes the device's primary IP; no other device fields.
        nb('PATCH', f'dcim/devices/{deviceid}/', dict(primary_ip4=ip_b['id']))
        dry_before = snapshot('E-before-apply')
        check('E', 'NetBox primary B; Zabbix still A before reconciliation',
            dry_before['primary_ip'] == B + '/32' and next(i for i in dry_before['host']['interfaces']
                if i['interfaceid'] == interfaceid)['ip'] == A,
            dict(netbox_primary=B, zabbix_primary=A))
        log, writes = reconcile('F-change')
        after = snapshot('G-after')
        current_hosts = hosts()
        match = [h for h in current_hosts if sync['host_identity'](h) == ('dcim.device', str(deviceid))]
        expected = copy.deepcopy(before['host'])
        next(i for i in expected['interfaces'] if i['interfaceid'] == interfaceid).update(ip=B)
        # Runtime availability fields are not integration-owned configuration.
        same_config = fingerprint([after['host']]) == fingerprint([expected])
        check('F-G', 'same host/interface, B, no duplicate, local state and other interface preserved',
            after['primary_ip'] == B + '/32' and len(match) == 1 and after['host']['hostid'] == hostid
            and same_config and [w['method'] for w in writes] == ['hostinterface.update']
            and writes[0]['params']['interfaceid'] == interfaceid,
            dict(device_id=deviceid, hostid=hostid, interfaceid=interfaceid, ip_before=A, ip_after=B,
                owned_host_count=len(match), local_tag_preserved=has_tag(after['host']['tags'], local_tag),
                all_other_returned_host_configuration_preserved=same_config, rpc=writes))
        device_timestamp = nb('GET', f'dcim/devices/{deviceid}/')['last_updated']
        log, writes = reconcile('H-idempotence')
        repeated = snapshot('H-repeated')
        unchanged_timestamp = nb('GET', f'dcim/devices/{deviceid}/')['last_updated'] == device_timestamp
        check('H', 'repeat: zero writes, zero changes, unchanged device and Zabbix configuration',
            not writes and 'changes=0' in log and fingerprint([repeated['host']]) == fingerprint([after['host']])
            and unchanged_timestamp,
            dict(rpc_writes=len(writes), log=log.strip(), device_timestamp_unchanged=unchanged_timestamp))
        # Supplemental tag-merge regression: both planned and offline map to a
        # disabled host. This exercises host.update WITHOUT enabling any check.
        nb('PATCH', f'dcim/devices/{deviceid}/', dict(status='offline'))
        tag_log, tag_writes = reconcile('J-managed-tag-change')
        tag_after = snapshot('J-after')
        expected_tags = copy.deepcopy(after['host'])
        next(t for t in expected_tags['tags'] if t['tag'] == 'netbox_status')['value'] = 'offline'
        check('J-supplemental', 'managed tag update preserves local tag/description/interfaces; host stays disabled',
            [w['method'] for w in tag_writes] == ['host.update']
            and fingerprint([tag_after['host']]) == fingerprint([expected_tags])
            and tag_after['host']['status'] == '1',
            dict(local_tag_preserved=has_tag(tag_after['host']['tags'], local_tag), hostid=hostid,
                 interfaceid=interfaceid, status=tag_after['host']['status'], rpc=tag_writes))
        _, repeat_tag_writes = reconcile('J-repeat')
        check('J-idempotence', 'tag merge repeat has zero writes', not repeat_tag_writes,
            dict(rpc_writes=len(repeat_tag_writes)))
        current_hosts = hosts()
        outside_unchanged = fingerprint([h for h in current_hosts if h['hostid'] != hostid]) == fingerprint(baseline_hosts)
        alerts_after = len(zx('alert.get', {'output': ['alertid']}))
        check('outside-scope', 'all non-owned hosts unchanged; no real inventory in fixture',
            outside_unchanged and alerts_after == alerts_before,
            dict(non_owned_configuration_unchanged=outside_unchanged, real_objects=0,
                 alerts_before=alerts_before, alerts_after=alerts_after))
        result = 'PASS'
    except Exception as error:
        failure = dict(type=type(error).__name__, message=str(error))
        save('failure.json', failure)
        raise
    finally:
        # On a host.create response followed by failure, retain ownership by ID.
        if hostid is None and (OUT / 'zabbix-ownership.json').exists():
            hostid = json.loads((OUT / 'zabbix-ownership.json').read_text())['hostid']
        errors = cleanup()
        if not errors:
            try:
                counts = {p: len(all_nb(p)) for p in baseline_counts}
                assert counts == baseline_counts
                check('I', 'run-owned objects removed by ledger ID; baseline restored', True,
                    dict(netbox_counts=counts, baseline_zabbix_fingerprint=fingerprint(hosts()), cleanup_errors=0))
            except Exception as e:
                errors.append(str(e))
        token.delete()
        try:
            assert zx('user.logout', []) is True
            z_token = None
            (ROOT / 'secrets/zabbix-api-token').unlink()
        except Exception as e:
            errors.append('Synthetic session cleanup: ' + str(e))
        save('result.json', dict(result=result if not errors else 'FAIL', failure=failure,
            cleanup_errors=errors, finished_utc=now(), run_id=RUN, events=len(EVENTS),
            synthetic_api_credentials_revoked=not errors))
        if errors:
            raise RuntimeError('Cleanup failed; inspect private ledger: ' + '; '.join(errors))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Setup failures precede inventory creation, but may already have issued
        # an ephemeral credential. Revoke only the saved ID and verified owner.
        credential_cleanup = []
        if bootstrap_token is not None and bootstrap_token.pk is not None:
            try:
                assert bootstrap_token.description == RUN
                assert bootstrap_token.user.username == 'synthetic-admin'
                credential_cleanup.append({'netbox_token_id_revoked': bootstrap_token.pk})
                bootstrap_token.delete()
            except Exception as cleanup_error:
                credential_cleanup.append({'error': str(cleanup_error)})
        if z_token is not None:
            try:
                zx('user.logout', [])
                credential_cleanup.append({'zabbix_session_revoked': True})
            except Exception as cleanup_error:
                credential_cleanup.append({'error': str(cleanup_error)})
        save('setup-failure-cleanup.json', credential_cleanup)
        if not (OUT / 'result.json').exists():
            save('result.json', dict(result='FAIL', phase=phase, error_type=type(error).__name__,
                error=str(error), time=now(), credential_cleanup=credential_cleanup))
        raise
