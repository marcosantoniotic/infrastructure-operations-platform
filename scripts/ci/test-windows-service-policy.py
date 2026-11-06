#!/usr/bin/env python3
"""Reuse the wholly fictitious, owned TLS API fixture. No environment inventory.

Explicit opt-in and a new Linux workspace remain mandatory. The reusable runner
owns teardown by IDs/labels. This acceptance uses synthetic active-agent PSK data,
NOT a real Windows agent/WMI provider/eventlog reader.
"""
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    runner = root / 'scripts/ci/test-netbox-platform-mapping.py'
    code = runner.read_text()
    old = "shutil.copy2(root/'scripts/tests/functional_netbox_platform_mapping.py', work/'functional-platform.py')"
    assert code.count(old) == 1
    code = code.replace(old, "shutil.copy2(root/'scripts/tests/functional_windows_service_policy.py', work/'functional-platform.py')\n        shutil.copy2(root/'roles/windows_service_policy/files/windows_service_policy.py', work/'windows_service_policy.py')")
    # The policy needs Zabbix, not a NetBox DB. Keep its Python image as an idle
    # runner but do not initialize Django/Postgres/Redis or reuse their datasets.
    anchor = "document = yaml.safe_load((work/'compose.yml').read_text())"
    assert code.count(anchor) == 1
    code = code.replace(anchor, anchor + "\n        document['services'] = {k:v for k,v in document['services'].items() if k in {'netbox','mysql','zabbix-server','zabbix-web','proxy'}}\n        runner_service = document['services']['netbox']\n        runner_service['entrypoint'] = ['/opt/netbox/venv/bin/python','-c','import time;time.sleep(3600)']\n        runner_service['command'] = []\n        runner_service['depends_on'] = {}\n        runner_service['user'] = '0'")
    probe = "r=requests.get('https://netbox.functional.example.test/login/',verify='/tls/ca.crt',timeout=3);r.raise_for_status()\n"
    assert code.count(probe) == 1; code = code.replace(probe, '')
    assert code.count('assert len(rows)==8') == 1; code = code.replace('assert len(rows)==8', 'assert len(rows)==5')
    assert code.count('timeout=600)') == 1; code = code.replace('timeout=600)', 'timeout=1200)')
    exec(compile(code, str(runner), 'exec'), {'__file__': str(runner), '__name__': '__main__'})


if __name__ == '__main__': main()
