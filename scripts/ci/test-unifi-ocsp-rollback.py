"""Safe CONFIG rollback on disposable fixture, never reset a revocation journal."""
import fcntl
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

assert socket.gethostname() == 'iop-netbox-security-test' and os.geteuid() == 0
parser = argparse.ArgumentParser()
parser.add_argument('--project', choices=['/tmp/iop-unifi-ocsp-acceptance-v2', '/tmp/iop-unifi-ocsp-pr91-acceptance'],
                    default='/tmp/iop-unifi-ocsp-acceptance-v2')
parser.add_argument('--fixture', type=Path,
                    default=Path('/home/automation/unifi-ocsp-isolated-20261028/.validation/ocsp-private/ansible-fixture'))
args = parser.parse_args()
root, fixture = Path(args.project), args.fixture.resolve()
assert 'ocsp-private' in fixture.parts and fixture.is_relative_to('/home/automation')
assert root.is_dir() and json.loads((fixture / 'manifest.json').read_text())['fictitious_only']
command = ['docker', 'compose', '--project-directory', str(root)]


def execute(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


def restart():
    execute(*command, 'up', '-d', '--no-deps', '--force-recreate', '--no-build', '--pull', 'never',
            'unifi-poller', 'unifi-ap-counts')


def states():
    return {name: json.loads((root / 'unifi-ocsp' / (name + '-state') / 'state.json').read_text())
            for name in ['unpoller', 'ap']}


def responder_mode(value):
    path = fixture / 'responder-mode.txt'
    path.write_text(value)
    metadata = fixture.stat()
    os.chown(path, metadata.st_uid, metadata.st_gid)


def clear_good_cache():
    for name in ['unpoller', 'ap']:
        path = root / 'unifi-ocsp' / (name + '-state') / 'state.json'
        with open(str(path) + '.lock', 'r+b') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            data = json.loads(path.read_text())
            data['cache'] = {}  # Explicit test-only eviction, NEVER clear revoked.
            temporary = path.with_name('test-cache-eviction.json')
            temporary.write_text(json.dumps(data))
            temporary.chmod(0o600)
            metadata = path.stat()
            os.chown(temporary, metadata.st_uid, metadata.st_gid)
            os.replace(temporary, path)


backup = root / ('protected-config-before-test-' + str(time.time_ns()))
backup.mkdir(mode=0o700, exist_ok=False)
shutil.copy2(root / 'compose.yaml', backup / 'compose.yaml')
for name in ['unpoller', 'ap']:
    shutil.copy2(root / 'unifi-ocsp' / name / 'policy.json', backup / (name + '-policy.json'))
    policy = json.loads((backup / (name + '-policy.json')).read_text())
    policy['responder_address'] = '127.0.0.2'  # No server; no non-loopback destination.
    (root / 'unifi-ocsp' / name / 'policy.json').write_text(json.dumps(policy))
clear_good_cache()
restart()
time.sleep(5)
failure = (root / 'metrics/unifi_ap_counts.prom').read_text()
assert 'iop_unifi_ap_counts_success 0' in failure
before = states()
for name in ['unpoller', 'ap']:
    shutil.copy2(backup / (name + '-policy.json'), root / 'unifi-ocsp' / name / 'policy.json')
shutil.copy2(backup / 'compose.yaml', root / 'compose.yaml')
execute(*command, 'config', '--quiet')
restart()
for _ in range(20):
    if 'iop_unifi_ap_counts_success 1' in (root / 'metrics/unifi_ap_counts.prom').read_text():
        break
    time.sleep(1)
else:
    raise AssertionError('Protected configuration rollback did not recover collection')
assert all(states()[name]['revoked'] == before[name]['revoked'] for name in before)

# Record real, correctly signed REVOKED in BOTH collectors.
responder_mode('revoked')
previous_denials = states()
clear_good_cache()
restart()
for _ in range(30):
    revoked = states()
    if all(len(revoked[name]['revoked']) > len(previous_denials[name]['revoked']) for name in revoked):
        break
    time.sleep(1)
else:
    raise AssertionError('Both collectors must retain confirmed revocation')

# Even a restored protected Compose + subsequent GOOD cannot override the deny.
responder_mode('good')
shutil.copy2(backup / 'compose.yaml', root / 'compose.yaml')
restart()
time.sleep(5)
after = states()
assert all(after[name]['revoked'] == revoked[name]['revoked'] for name in revoked)
assert 'iop_unifi_ap_counts_success 0' in (root / 'metrics/unifi_ap_counts.prom').read_text()
assert 'reason="revoked"' in (root / 'metrics/unifi_ap_counts.prom').read_text()
for name in ['unpoller', 'ap']:
    metric = (root / ('metrics/unifi_ocsp_' + name + '.prom')).read_text()
    assert 'reason="revoked"} 1' in metric and 'last_check_success' in metric
logs = execute(*command, 'logs', '--tail', '20', 'unifi-poller')
assert 'unifi_ocsp_revoked' in logs
assert hashlib.sha256((root / 'compose.yaml').read_bytes()).digest() == hashlib.sha256((backup / 'compose.yaml').read_bytes()).digest()
result = {'configuration_only_rollback': True, 'transient_failure_recovery': True,
          'no_database_or_volume_restore': True, 'both_revocation_journals_preserved': True,
          'good_cannot_override_confirmed_revocation': True, 'stock_binary_not_restored': True}
(backup / 'result.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result))
# Leave revoked fixture collectors stopped, retaining every journal and backup.
execute(*command, 'stop', 'unifi-poller', 'unifi-ap-counts')
