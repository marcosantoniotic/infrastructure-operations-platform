#!/usr/bin/env python3
"""Allowlisted public extract of PASS evidence; never exports credentials/baselines."""
import argparse
import hashlib
import json
from pathlib import Path

if not __debug__:
    raise SystemExit('Refusing optimized Python: fixture safety assertions must remain enabled')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('private_root', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    evidence = args.private_root / 'evidence'

    def load(name):
        return json.loads((evidence / name).read_text())

    result = load('result.json')
    assert result['result'] == 'PASS' and not result['cleanup_errors']
    execution = load('execution.json')
    run = execution['run_id']
    assert run.startswith('synthetic-ip-')
    events = load('events.json')
    assert all(e['result'] == 'PASS' for e in events)
    snapshots = {}
    hashes = {}
    for name in ('C-initial', 'D-local-state', 'E-before-apply', 'G-after', 'H-repeated', 'J-after'):
        raw = load(name + '.json')
        h = raw['host']
        assert h['host'] == run and h['name'] == run and h['status'] == '1'
        assert raw['primary_ip'] in ('198.51.100.10/32', '203.0.113.20/32')
        interfaces = []
        for i in h['interfaces']:
            assert i['ip'] in ('198.51.100.10', '203.0.113.20', '192.0.2.99')
            interfaces.append({k: i[k] for k in ('interfaceid', 'type', 'main', 'useip', 'ip', 'port', 'dns')})
        local = [t['value'] for t in h['tags'] if t['tag'] == 'local-test-owner']
        assert local in ([], [run])
        snapshots[name] = dict(netbox_device_id=raw['device_id'], netbox_primary=raw['primary_ip'],
            netbox_stored_hostid=raw['stored_hostid'], zabbix_hostid=h['hostid'],
            synthetic_identity=run, zabbix_status=h['status'], interfaces=interfaces,
            unmanaged_local_tag=local, local_description_present=h['description'] == run + ': local description')
        hashes[name + '.json'] = hashlib.sha256((evidence / (name + '.json')).read_bytes()).hexdigest()
    change = load('F-change-rpc.json')
    assert len(change) == 1 and change[0]['method'] == 'hostinterface.update'
    assert change[0]['params']['ip'] == '203.0.113.20'
    repeat = load('H-idempotence-rpc.json')
    assert repeat == []
    isolation = load('isolation-after.json')
    assert isolation['existing_containers_unchanged'] and isolation['internal_network']
    assert isolation['published_ports'] == 0
    for name in ('events.json', 'F-change-rpc.json', 'H-idempotence-rpc.json', 'cleanup.json', 'result.json', 'execution.json'):
        hashes[name] = hashlib.sha256((evidence / name).read_bytes()).hexdigest()
    public = dict(schema=1, provenance='allowlisted extract of real isolated API evidence; no UI screenshots',
        result='PASS', execution=execution, versions=load('versions.json'), events=events,
        snapshots=snapshots, ip_change_rpc=change, idempotence_rpc=repeat,
        cleanup=dict(objects_removed_by_id=True, credentials_revoked=result['synthetic_api_credentials_revoked'],
            errors=result['cleanup_errors']), isolation=dict(internal_network=True, published_ports=0,
            unchanged_existing_containers=len(isolation['existing_containers']),
            new_test_containers=len(isolation['test_containers'])),
        comparator_self_check=load('comparator-self-check.json'), private_raw_sha256=hashes,
        limitations=['No agent/collection/recovery test', 'Disabled synthetic host only',
            'No LAB01 or OPS access', 'No minimum-privilege token test', 'No deployment or publication'],
        finished_utc=result['finished_utc'])
    resource_result = evidence / 'resource-cleanup-result.json'
    if resource_result.exists():
        resource = json.loads(resource_result.read_text())
        assert resource['clean'] and resource['ownership_verified'] and resource['shared_volumes'] == 0
        public['resource_cleanup'] = dict(test_containers_removed=len(resource['containers']),
            test_volumes_removed=len(resource['volumes']), test_network_removed=True,
            shared_volumes=0, finished_utc=resource['finished'])
        public['private_raw_sha256']['resource-cleanup-result.json'] = hashlib.sha256(resource_result.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(public, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    args.output.chmod(0o600)
    print(json.dumps(dict(public_extract=str(args.output.name), result=public['result'],
        sha256=hashlib.sha256(args.output.read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
