#!/usr/bin/env python3
"""Real Ansible role/files/guards; synthetic HTTP and inert Compose only.

Linux disposable runners only. No inventories, credentials, Docker daemon or
network destinations from a real environment are used. The test role substitutes
only the Compose deployment task, source UID/GID and an explicitly injected fail.
All preparation, journal, URI, guard and shared validation tasks remain real.
"""
import argparse
import base64
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading

import yaml

ROOT = Path(__file__).resolve().parents[2]
STUB = '''#!/usr/bin/env python3
import json,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
p=root/'control.json';c=json.loads(p.read_text())
if sys.argv[1:2]==['deploy']:
 c['deploy_calls']=c.get('deploy_calls',0)+1;c['api_owned']=True
else:
 expected=['compose','--project-directory',str(root/'project'),'-f',str(root/'project/compose.yaml'),'-f',str(root/'project/compose.override.yaml'),'config','--quiet']
 assert sys.argv[1:]==expected, 'Unexpected inert Docker invocation'
 if c.get('fail_config'):raise SystemExit(17)
p.write_text(json.dumps(c))
print('Inert Compose fixture; no daemon contacted')
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args()
    work = args.workspace.resolve()
    assert sys.platform == 'linux' and __debug__
    assert os.environ.get('IOP_DISPOSABLE_PLATFORM_TEST') == '1'
    assert str(work).startswith('/tmp/') and not work.exists()
    os.umask(0o077)
    work.mkdir(mode=0o700)
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                    '-keyout', str(work/'fixture.key'), '-out', str(work/'fixture.crt'),
                    '-days', '1', '-subj', '/CN=Grafana Role Fixture',
                    '-addext', 'basicConstraints=critical,CA:TRUE',
                    '-addext', 'keyUsage=critical,keyCertSign,cRLSign'],
                   check=True, capture_output=True)
    reader_value = secrets.token_urlsafe(32)
    admin = secrets.token_urlsafe(32)
    active = {}

    class API(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            case = active['case']
            path = case/'control.json'
            c = json.loads(path.read_text())
            expected = 'Basic '+base64.b64encode(('fixture-admin:'+admin).encode()).decode()
            assert self.headers.get('Authorization') == expected
            c.setdefault('requests', []).append(self.path)
            path.write_text(json.dumps(c))
            code, body = 404, {'message': 'not found'}
            if self.path.endswith('/settings'):
                body = {'signature': c.get('signature', 'valid'), 'info': {'version': c.get('version', '6.10.2')}}
                code = 200
            elif self.path.endswith('/health'):
                code, body = 200, {'status': c.get('health', 'OK')}
            elif self.path == '/api/datasources/uid/iop-zabbix-readonly':
                if c.get('adopt_source') or (case/'project/grafana/provisioning/datasources/zabbix.yaml').exists():
                    code, body = 200, {'type': 'alexanderzobnin-zabbix-datasource',
                        'url': 'https://zabbix.example.test/api_jsonrpc.php',
                        'jsonData': {'username': 'fixture-reader', 'tlsSkipVerify': False, 'tlsAuthWithCACert': True}}
                    if c.get('incompatible_source'):
                        body['jsonData']['tlsSkipVerify'] = True
            elif self.path == '/api/folders/iop-profiles':
                if c.get('api_owned') or c.get('foreign_folder'):
                    code, body = 200, {'uid': 'iop-profiles'}
            elif '/api/dashboards/uid/iop-profiles-' in self.path:
                if c.get('api_owned') or c.get('foreign_dashboard'):
                    code, body = 200, {'dashboard': {'uid': self.path.rsplit('/', 1)[-1]}}
            blob = json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

    server = ThreadingHTTPServer(('127.0.0.1', 0), API)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    evidence = []

    def control(case, **changes):
        p = case/'control.json'
        value = json.loads(p.read_text())
        value.update(changes)
        p.write_text(json.dumps(value))

    def fingerprint(project):
        return {str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in project.rglob('*') if p.is_file()}

    def case(name, **settings):
        p = work/name
        project = p/'project'
        for directory in ['grafana/provisioning/datasources', 'grafana/provisioning/dashboards', 'grafana/dashboards']:
            (project/directory).mkdir(parents=True, mode=0o700)
        (project/'compose.yaml').write_text('services: {grafana: {image: fixture-only}}\n')
        for i in range(6):
            (project/f'grafana/dashboards/prior-{i}.json').write_text(json.dumps({'uid': 'prior-'+str(i)}))
        (project/'grafana/provisioning/datasources/prometheus.yml').write_text('fixture-preserved-source')
        (project/'volume-sentinel').write_text('fixture-preserved-data')
        (p/'bin').mkdir(mode=0o700)
        (p/'bin/docker').write_text(STUB)
        (p/'bin/docker').chmod(0o700)
        (p/'control.json').write_text(json.dumps(settings))
        fixture_roles = p/'roles'
        shutil.copytree(ROOT/'roles/grafana_profiles', fixture_roles/'grafana_profiles')
        shutil.copytree(ROOT/'technical-dashboards', p/'technical-dashboards')
        prepare = yaml.safe_load((fixture_roles/'grafana_profiles/tasks/prepare.yml').read_text())
        for task in prepare:
            if task['name'] == 'Provision the dedicated source without pruning other sources':
                task['ansible.builtin.copy']['owner'] = str(os.getuid())
                task['ansible.builtin.copy']['group'] = str(os.getgid())
        prepare_path = fixture_roles/'grafana_profiles/tasks/prepare.yml'
        prepare_path.write_text(yaml.safe_dump(prepare, sort_keys=False, allow_unicode=True))
        main_tasks = yaml.safe_load((fixture_roles/'grafana_profiles/tasks/main.yml').read_text())
        deployment = next(t for t in main_tasks if 'community.docker.docker_compose_v2' in t)
        assert deployment['community.docker.docker_compose_v2']['services'] == ['grafana']
        assert deployment['community.docker.docker_compose_v2']['dependencies'] is False
        deployment.pop('community.docker.docker_compose_v2')
        deployment.update({'ansible.builtin.command': {'argv': [str(p/'bin/docker'), 'deploy']}, 'changed_when': False})
        (fixture_roles/'grafana_profiles/tasks/main.yml').write_text(yaml.safe_dump(main_tasks, sort_keys=False))
        config = '[defaults]\nroles_path = '+str(fixture_roles)+'\nfilter_plugins = '+str(ROOT/'filter_plugins')+'\nhost_key_checking = True\nretry_files_enabled = False\n'
        (p/'ansible.cfg').write_text(config)
        variables = {'grafana_profiles_enabled': True, 'grafana_profiles_change_approved': True,
            'grafana_profiles_backup_confirmed': True, 'grafana_profiles_project_dir': str(project),
            'grafana_profiles_plugin_image': 'sha256:'+'a'*64, 'grafana_profiles_tls_network': 'fixture_tls',
            'grafana_profiles_api_url': 'https://zabbix.example.test/api_jsonrpc.php',
            'grafana_profiles_ca_certificate': (work/'fixture.crt').read_text(),
            'grafana_profiles_reader_username': 'fixture-reader', 'grafana_profiles_reader_password': reader_value,
            'grafana_profiles_admin_url': 'http://127.0.0.1:'+str(server.server_port),
            'grafana_profiles_admin_user': 'fixture-admin', 'grafana_profiles_admin_password': admin,
            'ansible_python_interpreter': sys.executable}
        (p/'vars.json').write_text(json.dumps(variables))
        (p/'baseline.json').write_text(json.dumps(fingerprint(project)))
        return p

    def run(p, success=True, general=False, variables=None):
        active['case'] = p
        values = json.loads((p/'vars.json').read_text())
        values.update(variables or {})
        (p/'run-vars.json').write_text(json.dumps(values))
        if general:
            general_tasks = yaml.safe_load((ROOT/'roles/observability/tasks/main.yml').read_text())
            prepare = next(t for t in general_tasks if t.get('name') == 'Prepare the opted in Grafana profile overlay')
            validate = next(t for t in general_tasks if t.get('name') == 'Validate opted in Grafana profiles after the observability deployment')
            tasks = [prepare, {'name': 'Inert general deployment boundary', 'ansible.builtin.command': {'argv': [str(p/'bin/docker'), 'deploy']}, 'changed_when': False}, validate]
        else:
            tasks = [{'ansible.builtin.include_role': {'name': 'grafana_profiles'}}]
        play = [{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'become': False, 'tasks': tasks}]
        (p/'play.json').write_text(json.dumps(play))
        env = dict(os.environ, ANSIBLE_CONFIG=str(p/'ansible.cfg'), PATH=str(p/'bin')+os.pathsep+os.environ['PATH'], ANSIBLE_NOCOLOR='1')
        r = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(p/'play.json'), '-e', '@'+str(p/'run-vars.json')], cwd=p, env=env, capture_output=True, text=True, timeout=120)
        log = r.stdout+r.stderr
        (p/('run-'+str(len(list(p.glob('run-*.log'))))+'.log')).write_text(log)
        if (r.returncode == 0) != success:
            raise AssertionError(p.name+' unexpected result\n'+log[-6000:])
        baseline = json.loads((p/'baseline.json').read_text())
        now = fingerprint(p/'project')
        assert all(now.get(n) == h for n,h in baseline.items()), p.name+' changed preexisting data'
        evidence.append({'case': p.name, 'path': 'general-validation-include' if general else 'dedicated-role', 'expected_success': success, 'passed': True})
        print(p.name, 'PASS', flush=True)
        return log

    def phase(p):
        return json.loads((p/'project/grafana-profiles-state.json').read_text())['phase']

    try:
        p = case('clean-and-idempotent')
        run(p); assert phase(p) == 'validated'
        first = fingerprint(p/'project')
        assert 'changed=0' in run(p) and fingerprint(p/'project') == first

        p = case('partial-artifact-resume')
        path = p/'roles/grafana_profiles/tasks/prepare.yml'
        original = path.read_text()
        tasks = yaml.safe_load(original)
        for i,t in enumerate(tasks):
            if t['name'] == 'Provision the dedicated source without pruning other sources':
                tasks[i] = {'name': 'Injected failure after directory creation', 'ansible.builtin.fail': {'msg': 'Synthetic interruption'}}
        path.write_text(yaml.safe_dump(tasks, sort_keys=False))
        run(p, False); assert phase(p) == 'preparing'
        assert (p/'project/grafana/profile-dashboards').is_dir()
        path.write_text(original)
        run(p); assert phase(p) == 'validated'

        p = case('compose-failure-resume', fail_config=True)
        run(p, False); assert phase(p) == 'preparing'
        control(p, fail_config=False); run(p); assert phase(p) == 'validated'

        for name, setting, general in [('bad-signature-dedicated', {'signature': 'invalid'}, False),
                                       ('wrong-version-general', {'version': '0.0.0'}, True),
                                       ('unhealthy-source-general', {'health': 'ERROR'}, True)]:
            p = case(name, **setting)
            run(p, False, general); assert phase(p) == 'preparing'
            control(p, signature='valid', version='6.10.2', health='OK')
            run(p, general=general); assert phase(p) == 'validated'

        p = case('source-adoption', adopt_source=True)
        run(p, False); assert not (p/'project/grafana-profiles-state.json').exists()
        run(p, variables={'grafana_profiles_adopt_existing': True}); assert phase(p) == 'validated'

        for name, settings, artifact in [
            ('foreign-override', {}, 'compose.override.yaml'),
            ('foreign-provider', {}, 'grafana/provisioning/dashboards/profiles.yaml'),
            ('foreign-directory', {}, 'grafana/profile-dashboards/foreign.txt'),
            ('foreign-folder', {'foreign_folder': True}, None),
            ('foreign-dashboard', {'foreign_dashboard': True}, None),
            ('incompatible-source', {'adopt_source': True, 'incompatible_source': True}, None),
        ]:
            p = case(name, **settings)
            if artifact:
                target = p/'project'/artifact;target.parent.mkdir(parents=True, exist_ok=True);target.write_text('foreign fixture')
                (p/'baseline.json').write_text(json.dumps(fingerprint(p/'project')))
            original = fingerprint(p/'project')
            run(p, False, variables={'grafana_profiles_adopt_existing': True})
            assert fingerprint(p/'project') == original and not (p/'project/grafana-profiles-state.json').exists()
    finally:
        server.shutdown(); server.server_close()
    result = {'result': 'PASS', 'ansible_runs': len(evidence), 'cases': evidence,
              'actual_ansible_files_guards_and_uri_tasks': True, 'compose_and_api_inert': True,
              'source_ownership_substituted_to_fixture_uid_gid': True,
              'real_tls_or_plugin_runtime_test': False, 'prior_six_dashboards_source_and_data_preserved': True,
              'real_environment_access': False}
    (work/'evidence.sanitized.json').write_text(json.dumps(result, indent=2))
    # Other Ansible steps can own CI_ARTIFACT_DIR as root. Do not broaden those
    # permissions: keep fixtures private and export only sanitized job output.
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        target = Path(summary).resolve()
        assert target.is_relative_to(Path(os.environ['RUNNER_TEMP']).resolve())
        with target.open('a') as stream:
            stream.write('## Isolated Grafana role matrix\n\n```json\n'+json.dumps(result, indent=2)+'\n```\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
