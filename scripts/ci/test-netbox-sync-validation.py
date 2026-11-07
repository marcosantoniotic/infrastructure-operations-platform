#!/usr/bin/env python3
"""Run the actual final Ansible task with an inert Docker executable.

No Docker daemon, inventory, API, credential or application data is used.
The test copy substitutes only the executable and shortens retries/delay.
Conditions, register, arguments and change semantics remain the real task's.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]
TASK_NAME = 'Validate NetBox-Zabbix synchronization with a dry run'

class UniqueLoader(yaml.SafeLoader):
    pass

def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError('Duplicate YAML key: ' + str(key))
        result[key] = loader.construct_object(value_node, deep=deep)
    return result

UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)

STUB = '''#!/usr/bin/env python3
import json, sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
config = json.loads((root/'fixture.json').read_text())
expected = ['compose', '--project-directory', str(root), 'run', '--rm',
            'netbox-zabbix-sync', '/opt/netbox/venv/bin/python',
            '/usr/local/libexec/netbox-zabbix-sync.py']
if sys.argv[1:] != expected:
    raise SystemExit(97)
path = root/'calls.json'
calls = json.loads(path.read_text())
code = config['codes'][min(len(calls), len(config['codes'])-1)]
calls.append(code)
path.write_text(json.dumps(calls))
print('Inert fixture return code ' + str(code))
raise SystemExit(code)
'''

CASES = [
    ('strict-zero', False, [0], False, 1, False, False),
    ('optin-zero', True, [0], False, 1, False, False),
    ('optin-pending', True, [2], False, 1, False, False),
    ('strict-pending-refused', False, [2], True, 2, False, False),
    ('strict-error', False, [1], True, 2, False, False),
    ('optin-error', True, [1], True, 2, False, False),
    ('unexpected-error', True, [17], True, 2, False, False),
    ('transient-error-recovery', False, [1, 0], False, 2, False, False),
    ('disabled-inert', False, [97], False, 0, True, False),
    ('check-mode-inert', True, [97], False, 0, False, True),
]

def load_task():
    tasks = yaml.load((ROOT/'roles/netbox_zabbix_sync/tasks/main.yml').read_text(), Loader=UniqueLoader)
    matches = [task for task in tasks if task.get('name') == TASK_NAME]
    assert len(matches) == 1
    task = matches[0]
    assert task['register'] == 'netbox_zabbix_sync_validation'
    assert task['retries'] == 10 and task['delay'] == 10
    assert task['failed_when'].replace(' not in ', ' in ') == task['until']
    assert 'ansible.builtin.command' in task and task['changed_when'] is False
    return task

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args()
    assert __debug__ and sys.platform == 'linux'
    assert os.environ.get('IOP_DISPOSABLE_PLATFORM_TEST') == '1'
    work = args.workspace.resolve()
    assert str(work).startswith('/tmp/') and not work.exists()
    os.umask(0o077)
    work.mkdir(parents=True, mode=0o700)
    task = load_task()
    evidence = []
    for name, optin, codes, failure, count, disabled, check_mode in CASES:
        case = work/name; (case/'bin').mkdir(parents=True, mode=0o700)
        (case/'fixture.json').write_text(json.dumps({'codes':codes}))
        (case/'calls.json').write_text('[]')
        docker = case/'bin/docker'; docker.write_text(STUB); docker.chmod(0o700)
        actual = copy.deepcopy(task)
        # Absolute executable prevents any fallback to a real Docker CLI.
        command = actual['ansible.builtin.command']['cmd']
        assert command.startswith('docker compose ')
        actual['ansible.builtin.command']['cmd'] = str(docker)+command[len('docker'):]
        # Preserve conditions, register, arguments and change semantics.
        actual.update(retries=1, delay=0)
        skipped = disabled or check_mode
        expected_rc = codes[min(count-1, len(codes)-1)] if count else None
        assertions = [
            'test_failed == expected_failure',
            'netbox_zabbix_sync_validation is defined',
            'not netbox_zabbix_sync_validation.changed',
            "lookup('file', fixture_root + '/calls.json') | from_json | length == expected_count",
        ]
        if skipped:
            assertions += ['netbox_zabbix_sync_validation.skipped | bool']
        else:
            assertions += ['netbox_zabbix_sync_validation.rc == expected_rc']
        play = [{
            'name':'Inert real-task return contract '+name,
            'hosts':'localhost', 'connection':'local', 'gather_facts':False, 'become':False,
            'vars':{
                'fixture_root':str(case), 'expected_failure':failure,
                'expected_count':count, 'expected_rc':expected_rc,
                'netbox_zabbix_sync_enabled':not disabled,
                'netbox_zabbix_sync_project_dir':str(case),
                'netbox_zabbix_sync_profile_transitions':[{'from':'icmp','to':'windows'}] if optin else [],
            },
            'tasks':[
                {'ansible.builtin.set_fact':{'test_failed':False}},
                {'block':[actual], 'rescue':[
                    {'ansible.builtin.assert':{'that':"ansible_failed_task.name == '"+TASK_NAME+"'"}},
                    {'ansible.builtin.set_fact':{'test_failed':True}},
                ]},
                {'name':'Assert observed execution and retry semantics',
                 'ansible.builtin.assert':{'that':assertions}},
            ],
        }]
        path = case/'test.yml'; path.write_text(yaml.safe_dump(play, sort_keys=False))
        cmd = ['ansible-playbook', '-i', 'localhost,', str(path)]
        if check_mode: cmd.append('--check')
        run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=90)
        (case/'ansible.private.log').write_text(run.stdout+'\n'+run.stderr)
        calls = json.loads((case/'calls.json').read_text())
        if run.returncode or len(calls) != count:
            raise RuntimeError('Real-task contract failed: '+name+'; private fixture log retained')
        event = {'case':name, 'result':'PASS', 'expected_failure':failure,
                 'codes_observed':calls, 'calls':len(calls)}
        evidence.append(event); print(json.dumps(event), flush=True)
        (work/'result.sanitized.json').write_text(json.dumps(evidence, indent=2))
    print('REAL_ANSIBLE_DRY_RUN_RETURN_MATRIX_PASS', flush=True)

if __name__ == '__main__':
    main()
