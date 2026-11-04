#!/usr/bin/env python3
"""Create, test and tear down a wholly fictitious API stack. No external inventory.

Requires explicit IOP_DISPOSABLE_PLATFORM_TEST=1, a NEW workspace and Docker.
No host ports, external networks, existing volumes or production credentials.
Private workspace/evidence remains for inspection; only owned Docker IDs removed.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import secrets
from pathlib import Path
import shutil
import subprocess
import sys
import time

if not __debug__:
    raise SystemExit('Refusing optimized Python: safety assertions must remain enabled')

import yaml


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--revision', required=True)
    args = p.parse_args()
    assert os.environ.get('IOP_DISPOSABLE_PLATFORM_TEST') == '1'
    assert sys.platform == 'linux'
    root = Path(__file__).resolve().parents[2]
    work = args.workspace.resolve()
    assert not work.exists() and str(work).startswith(('/tmp/', '/home/vagrant/'))
    work.parent.mkdir(parents=True, exist_ok=True)
    run = 'synthetic-ip-platform-' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') + '-' + secrets.token_hex(4)
    os.umask(0o077)

    def capture(command, **kw):
        return subprocess.check_output(command, text=True, stderr=subprocess.PIPE, **kw).strip()

    def state():
        ids = capture(['docker', 'ps', '-aq']).split()
        if not ids: return {}
        rows = json.loads(capture(['docker', 'inspect', *ids]))
        return {x['Id']: [x['State']['Running'], x['State']['StartedAt']] for x in rows}

    baseline = state()
    assert not capture(['docker','ps','-aq','--filter','label=com.docker.compose.project='+run])
    for kind in ('network','volume'):
        assert not capture(['docker',kind,'ls','-q','--filter','label=com.docker.compose.project='+run])
    subprocess.run([sys.executable, str(root/'scripts/tests/fixtures/netbox_zabbix_ip_prepare.py'),
                    str(work), '--run-id', run, '--revision', args.revision], check=True)
    (work/'evidence/baseline-container-state.private.json').write_text(json.dumps(baseline))
    compose = ['docker', 'compose', '--project-directory', str(work), '-f', str(work/'compose.yml')]
    started = False
    success = False

    def command(label, argv, timeout=1200, env=None):
        print('ISOLATED_STAGE '+label, flush=True)
        with (work/'evidence'/(label+'.private.log')).open('wb') as log:
            result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, env=env)
        if result.returncode:
            raise RuntimeError('Isolated stage failed: '+label+'; private log retained')

    try:
        render = work/'rendered'
        environment = dict(os.environ, CI_ARTIFACT_DIR=str(render), ANSIBLE_NOCOLOR='1')
        command('render', ['ansible-playbook', '-i', 'localhost,', 'scripts/ci/render-validation-artifacts.yml'], env=environment)
        context = render/'netbox'
        shutil.copy2(root/'roles/netbox/templates/topology-role-unknown.svg', context/'topology-role-unknown.svg')
        (context/'topology-role-unknown.svg').chmod(0o644)
        image = 'iop-isolated/netbox:'+run
        command('build', ['docker', 'build', '-t', image, str(context)], timeout=1800)
        document = yaml.safe_load((work/'compose.yml').read_text())
        document['services']['netbox']['image'] = image
        assert document['networks']['test']['internal'] is True
        assert all(not x.get('ports') and not any(n.get('external') for n in document['networks'].values())
                   for x in document['services'].values())
        assert all(not x.get('external') for x in document['volumes'].values())
        assert all(x['labels']['iop.synthetic.run']==run and x['restart']=='no' for x in document['services'].values())
        (work/'compose.yml').write_text(yaml.safe_dump(document, sort_keys=False))
        manifest = json.loads((work/'manifest.json').read_text())
        manifest['images']['netbox'] = image
        (work/'manifest.json').write_text(json.dumps(manifest, indent=2))
        shutil.copy2(root/'roles/netbox_zabbix_sync/templates/netbox-zabbix-sync.py.j2', work/'netbox-zabbix-sync.py')
        shutil.copy2(root/'scripts/tests/functional_netbox_platform_mapping.py', work/'functional-platform.py')
        command('compose-config', [*compose, 'config', '--quiet'])
        # Mark before up: even a partial startup must be cleaned, by labels/IDs.
        started = True
        command('up', [*compose, 'up', '-d'], timeout=1800)
        probe = """import requests
r=requests.get('https://netbox.functional.example.test/login/',verify='/tls/ca.crt',timeout=3);r.raise_for_status()
r=requests.post('https://zabbix.functional.example.test/api_jsonrpc.php',json={'jsonrpc':'2.0','method':'apiinfo.version','params':{},'id':1},verify='/tls/ca.crt',timeout=3);r.raise_for_status();assert r.json().get('result','').startswith('7.4.')
"""
        deadline = time.monotonic()+900
        attempt = 0
        while True:
            ready = subprocess.run([*compose, 'exec', '-T', 'netbox', '/opt/netbox/venv/bin/python', '-c', probe], capture_output=True)
            if ready.returncode == 0: break
            assert time.monotonic()<deadline, 'Application initialization pending; no TLS bypass'
            attempt += 1
            if attempt % 5 == 0: print('ISOLATED_WAIT_APPLICATIONS '+str(attempt), flush=True)
            time.sleep(5)
        ids = capture([*compose, 'ps', '-aq']).split()
        rows = json.loads(capture(['docker','inspect',*ids]))
        assert len(rows)==8 and all(not x['HostConfig']['PortBindings'] for x in rows)
        network = json.loads(capture(['docker','network','inspect',run+'_test']))[0]
        assert network['Internal'] and network['Labels']['iop.synthetic.run']==run
        (work/'evidence/images.private.json').write_text(json.dumps([
            {'id': x['Id'], 'image': x['Config']['Image'], 'image_id': x['Image']} for x in rows], indent=2))
        command('functional', [*compose, 'exec', '-T', '--user', '0', 'netbox',
                              '/opt/netbox/venv/bin/python', '/fixture/functional-platform.py'], timeout=600)
        report = json.loads((work/'evidence/platform-result.json').read_text())
        assert report['result']=='PASS'
        print(json.dumps(report), flush=True)
        success = True
    finally:
        if started:
            ids = capture([*compose, 'ps', '-aq']).split()
            rows = json.loads(capture(['docker','inspect',*ids])) if ids else []
            assert all(x['Config']['Labels'].get('iop.synthetic.run')==run
                       and x['Config']['Labels'].get('com.docker.compose.project')==run for x in rows)
            assert not set(ids)&set(baseline)
            for kind, field in [('network','Networks'), ('volume','Volumes')]:
                owned = capture(['docker',kind,'ls','-q','--filter','label=com.docker.compose.project='+run]).split()
                for name in owned:
                    labels = json.loads(capture(['docker',kind,'inspect',name]))[0].get('Labels', {})
                    assert labels.get('iop.synthetic.run')==run
            command('teardown', [*compose,'down','--volumes','--remove-orphans'], timeout=300)
            assert not capture(['docker','ps','-aq','--filter','label=com.docker.compose.project='+run])
            for kind in ('network', 'volume'):
                assert not capture(['docker',kind,'ls','-q','--filter','label=com.docker.compose.project='+run])
            assert state()==baseline
            (work/'evidence/platform-resource-cleanup.json').write_text(json.dumps(dict(
                owned_container_ids_removed=ids, non_owned_containers_unchanged=True,
                project=run, test_volumes_removed=True, success=success), indent=2))
            print('ISOLATED_OWNED_RESOURCES_REMOVED', flush=True)
    assert success


if __name__ == '__main__':
    main()
