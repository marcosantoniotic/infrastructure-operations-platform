"""Official signed Grafana plugin in a new, disposable API fixture only.

Browser review is optional (IOP_TECHNICAL_VISUAL_TEST=1), bounded and manual.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
code = (ROOT / 'scripts/ci/test-netbox-platform-mapping.py').read_text()

def replace_once(old, new):
    global code
    if code.count(old) != 1:
        raise RuntimeError('Disposable runner contract changed; review before execution')
    code = code.replace(old, new)

extra = """        import re, jinja2
        # NEW synthetic DB only: no crash-durability acceptance is claimed.
        document['services']['postgres']['command'] = ['postgres', '-c', 'fsync=off', '-c', 'synchronous_commit=off', '-c', 'full_page_writes=off']
        grafana_context = work / 'grafana-image'
        grafana_context.mkdir(mode=0o700)
        (grafana_context / 'Dockerfile').write_text('FROM grafana/grafana:13.1.6\\nUSER root\\nRUN grafana cli --pluginsDir /opt/plugins plugins install alexanderzobnin-zabbix-app 6.10.2\\nENV GF_PATHS_PLUGINS=/opt/plugins\\nUSER 472\\n')
        grafana_image = 'iop-isolated/grafana-technical-groups:' + run
        command('grafana-build', ['docker', 'build', '-t', grafana_image, str(grafana_context)], timeout=1200)
        password = (secrets.token_urlsafe(36))
        (work / 'secrets/grafana-admin').write_text(password)
        document['services']['grafana'] = {'image': grafana_image, 'environment': {'GF_SECURITY_ADMIN_PASSWORD': password, 'GF_USERS_ALLOW_SIGN_UP': 'false', 'GF_ANALYTICS_REPORTING_ENABLED': 'false', 'GF_ANALYTICS_CHECK_FOR_UPDATES': 'false'}, 'volumes': ['grafana:/var/lib/grafana'], 'networks': {'test': {}}, 'labels': {'iop.synthetic.run': run}, 'restart': 'no'}
        document['volumes']['grafana'] = {'labels': {'iop.synthetic.run': run}}
        shutil.copytree(root / 'technical-dashboards', work / 'group-dashboards')
        (work / 'baseline-dashboards').mkdir()
        template_env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        template_env.filters['bool'] = lambda value: str(value).lower() in ('true', 'yes', '1')
        template_env.tests['match'] = lambda value, pattern: bool(re.match(pattern, value))
        for name in ['application-tls-health', 'backup-health', 'dns-service-health', 'glpi-itsm-health', 'infrastructure-host-containers', 'zabbix-glpi-bridge']:
            rendered = template_env.from_string((root / 'roles/observability/templates' / (name + '.json.j2')).read_text()).render(observability_blackbox_targets=[], observability_adguard_metrics_enabled=False)
            (work / 'baseline-dashboards' / (name + '.json')).write_text(rendered)
        shutil.copy2(root / 'scripts/tests/technical_grafana.py', work / 'technical_grafana.py')
"""
anchor = "        assert document['networks']['test']['internal'] is True"
replace_once(anchor, extra + anchor)
replace_once('assert len(rows)==8', 'assert len(rows)==9')
replace_once("root/'scripts/tests/functional_netbox_platform_mapping.py'", "root/'scripts/tests/functional_netbox_technical_groups.py'")
replace_once("'--user', '0', 'netbox',", "'--user', '0', '-e', 'IOP_TECHNICAL_VISUAL_TEST=' + os.environ.get('IOP_TECHNICAL_VISUAL_TEST', '0'), 'netbox',")
replace_once('timeout=600)', 'timeout=1200)')
exec(compile(code, str(ROOT / 'scripts/ci/test-netbox-platform-mapping.py'), 'exec'),
     {'__file__': str(ROOT / 'scripts/ci/test-netbox-platform-mapping.py'), '__name__': '__main__'})
