"""Disposable Docker integration only. Never reads a private inventory or backup.

Run exclusively on the ephemeral GitHub runner. No published ports, webhooks,
ticket creation, OPS addresses or LAB VM changes. Runtime secrets/keys stay in /tmp.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import yaml

ROOT = Path(__file__).resolve().parents[2]


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise SystemExit('Run only on an ephemeral GitHub-hosted runner, never on a laboratory/OPS host')
    fixture = Path(tempfile.mkdtemp(prefix='iop-https-', dir='/tmp'))
    project = fixture.name
    passwords = [secrets.token_hex(24) for _ in range(3)]

    def run(args, *, check=True, stdin=None):
        result = subprocess.run(args, input=stdin, text=True, capture_output=True, cwd=ROOT)
        if check and result.returncode:
            detail = result.stderr[-2500:]
            for password in passwords:
                detail = detail.replace(password, '[redacted]')
            raise RuntimeError(f'Fixture command failed ({args[0]}): {detail}')
        return result

    def dc(*args, **kwargs):
        return run(['docker', 'compose', '-p', project, '-f', str(fixture / 'compose.yaml'), *args], **kwargs)

    def client(code, *, check=True):
        return dc('run', '--rm', '--no-deps', 'bridge', 'python', '-c', code, check=check)

    def sql(query):
        return dc('exec', '-T', 'db', 'sh', '-c',
                  'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb -uroot -N -B -e "$1"', 'sh', query).stdout.strip()

    # Fresh test PKI; no keys/certificates are reused from any environment.
    for name in ('ca', 'untrusted'):
        run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '2',
             '-subj', f'/CN=IOP-disposable-{name}', '-addext', 'basicConstraints=critical,CA:TRUE',
             '-addext', 'keyUsage=critical,keyCertSign,cRLSign', '-keyout', str(fixture / f'{name}.key'),
             '-out', str(fixture / f'{name}.crt')])
    run(['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=glpi.test',
         '-keyout', str(fixture / 'server.key'), '-out', str(fixture / 'server.csr')])
    (fixture / 'extensions').write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:glpi.test\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n')
    run(['openssl', 'x509', '-req', '-in', str(fixture / 'server.csr'), '-CA', str(fixture / 'ca.crt'),
         '-CAkey', str(fixture / 'ca.key'), '-CAcreateserial', '-days', '2', '-sha256',
         '-extfile', str(fixture / 'extensions'), '-out', str(fixture / 'server.crt')])
    run(['openssl', 'verify', '-x509_strict', '-verify_hostname', 'glpi.test',
         '-CAfile', str(fixture / 'ca.crt'), str(fixture / 'server.crt')])
    run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '2',
         '-subj', '/CN=IOP-disposable-missing-usage', '-addext', 'basicConstraints=critical,CA:TRUE',
         '-keyout', str(fixture / 'missing-usage.key'), '-out', str(fixture / 'missing-usage.crt')])
    run(['openssl', 'x509', '-req', '-in', str(fixture / 'server.csr'), '-CA', str(fixture / 'missing-usage.crt'),
         '-CAkey', str(fixture / 'missing-usage.key'), '-CAcreateserial', '-days', '2',
         '-extfile', str(fixture / 'extensions'), '-out', str(fixture / 'missing-usage-leaf.crt')])
    assert run(['openssl', 'verify', '-x509_strict', '-CAfile', str(fixture / 'missing-usage.crt'),
                str(fixture / 'missing-usage-leaf.crt')], check=False).returncode != 0
    values = {}
    for role in ('observability', 'glpi', 'zabbix_glpi_bridge', 'traefik'):
        values.update(yaml.safe_load((ROOT / f'roles/{role}/defaults/main.yml').read_text()))
    legacy = [dict(name='legacy', url='http://plain:8080')]
    values.update(fixture_dir=str(fixture), glpi_database_password=passwords[0],
                  glpi_database_root_password=passwords[1], glpi_crontab_enabled=False,
                  glpi_php_security_hardening=True, glpi_https_cookie_hardening=True,
                  glpi_trusted_proxy_subnet='0.0.0.0/0',  # replaced with actual isolated backend CIDR below
                  observability_blackbox_targets=legacy)

    def render():
        (fixture / 'vars.json').write_text(json.dumps(values))
        return run(['ansible-playbook', '-i', 'localhost,', 'scripts/ci/render-glpi-https.yml',
                    '-e', '@' + str(fixture / 'vars.json')]).stdout

    render()
    legacy_config = (fixture / 'blackbox.yml').read_text()
    legacy_compose = yaml.safe_load((fixture / 'observability.yaml').read_text())
    assert not yaml.safe_load(legacy_config)['modules']['http_legacy']['http']['fail_if_not_ssl']
    assert 'blackbox_tls' not in legacy_compose['networks']
    (fixture / 'legacy.yml').write_text(legacy_config)
    ca = (fixture / 'ca.crt').read_text()
    values.update(iop_internal_api_tls_network=project + '_api', iop_internal_api_tls_aliases=['glpi.test'],
                  iop_internal_api_ca_certificate=ca, observability_blackbox_private_ca_certificate=ca,
                  observability_blackbox_tls_network=project + '_api',
                  observability_blackbox_targets=legacy + [dict(name='glpi', url='https://glpi.test/',
                                                               require_https=True, private_ca=True)],
                  zabbix_glpi_bridge_glpi_url='https://glpi.test/api.php',
                  zabbix_glpi_bridge_zabbix_url='https://glpi.test/unused',
                  zabbix_glpi_bridge_glpi_user='glpi')
    render()
    second = render()
    assert 'changed=0' in second, 'Second template pass was not idempotent'
    secure_compose = yaml.safe_load((fixture / 'observability.yaml').read_text())
    assert secure_compose['volumes'] == legacy_compose['volumes']
    for name, service in legacy_compose['services'].items():
        assert service.get('ports') == secure_compose['services'][name].get('ports')
        if name != 'blackbox-exporter':
            assert service == secure_compose['services'][name], 'Unrelated monitoring service changed'
    assert './blackbox/private-ca.crt:/etc/blackbox_exporter/ca/private-ca.crt:ro,Z' in secure_compose['services']['blackbox-exporter']['volumes']
    (fixture / 'secure.yml').write_text((fixture / 'blackbox.yml').read_text())
    # Additional negative-control module uses an unrelated, equally valid CA.
    blackbox = yaml.safe_load((fixture / 'blackbox.yml').read_text())
    blackbox['modules']['http_untrusted'] = json.loads(json.dumps(blackbox['modules']['http_glpi']))
    blackbox['modules']['http_untrusted']['http']['tls_config']['ca_file'] = '/etc/blackbox_exporter/ca/untrusted.crt'
    (fixture / 'blackbox.yml').write_text(yaml.safe_dump(blackbox))
    (fixture / 'internal-api-ca.crt').write_text(ca)
    (fixture / 'private-ca.crt').write_text(ca)
    (fixture / 'custom-php.ini').write_text('; Disposable fixture only\n')
    (fixture / 'secrets').mkdir()
    for name, value in [('glpi_database_password', passwords[0]), ('glpi_database_root_password', passwords[1]),
                        ('glpi_user_password', 'glpi'), ('glpi_oauth_secret', passwords[2]),
                        ('glpi_oauth_client_id', 'pending'), ('bridge_webhook_token', passwords[2]),
                        ('zabbix_api_token', passwords[2])]:
        (fixture / 'secrets' / name).write_text(value)
    glpi = yaml.safe_load((fixture / 'glpi.yaml').read_text())
    bridge = yaml.safe_load((fixture / 'bridge.yaml').read_text())['services']['zabbix-glpi-bridge']
    bridge['volumes'] = [v for v in bridge['volumes'] if '/var/lib/zabbix-glpi-bridge' not in v]
    bridge['volumes'].append('./untrusted.crt:/run/ca/untrusted.crt:ro')
    bridge['networks'] = ['api']
    bridge['restart'] = 'no'
    bridge['environment']['NO_PROXY'] = '*'
    db, app = glpi['services']['db'], glpi['services']['glpi']
    db['environment'] = dict(MARIADB_DATABASE='glpi', MARIADB_USER='glpi',
                             MARIADB_PASSWORD=passwords[0], MARIADB_ROOT_PASSWORD=passwords[1])
    db['volumes'] = ['database:/var/lib/mysql']
    db['networks'] = ['backend']
    app.pop('ports', None)
    app['networks'] = ['backend']
    app['volumes'] = [v for v in app['volumes'] if 'php-security.ini' not in v and 'proxy-https.conf' not in v]
    document = dict(services={
        'db': db, 'glpi': app, 'bridge': bridge,
        'traefik': dict(image=values['traefik_image'],
                        command=['--entrypoints.web.address=:80', '--entrypoints.websecure.address=:443',
                                 '--providers.file.filename=/etc/traefik/dynamic.yml'],
                        volumes=['./dynamic.yml:/etc/traefik/dynamic.yml:ro', './server.crt:/certs/server.crt:ro',
                                 './server.key:/certs/server.key:ro'],
                        networks={'api': {'aliases': ['glpi.test', 'wrong.test']}, 'backend': {}}),
        'plain': dict(image=values['zabbix_glpi_bridge_image'], command=['python', '-m', 'http.server', '8080'], networks=['api']),
        'blackbox-exporter': dict(image=values['observability_blackbox_image'],
                                 command=['--config.file=/etc/blackbox_exporter/blackbox.yml'],
                                 volumes=['./blackbox.yml:/etc/blackbox_exporter/blackbox.yml:ro',
                                          './private-ca.crt:/etc/blackbox_exporter/ca/private-ca.crt:ro',
                                          './untrusted.crt:/etc/blackbox_exporter/ca/untrusted.crt:ro'],
                                 read_only=True, cap_drop=['ALL'], networks=['api'])},
        networks={'api': {'internal': True}, 'backend': {'internal': True}},
        volumes={name: {} for name in ['database', 'glpi_config', 'glpi_files', 'glpi_logs', 'glpi_marketplace']})
    dynamic = dict(http=dict(routers={'glpi': dict(rule='Host(`glpi.test`)', entryPoints=['websecure'],
                                                  service='glpi', tls={})},
                             services={'glpi': dict(loadBalancer=dict(servers=[dict(url='http://glpi:80')]))}),
                   tls=dict(certificates=[dict(certFile='/certs/server.crt', keyFile='/certs/server.key')]))
    dynamic['http']['routers']['downgrade'] = dict(rule='Host(`glpi.test`) && PathPrefix(`/downgrade`)',
                                                  entryPoints=['websecure'], service='glpi', tls={},
                                                  middlewares=['downgrade'], priority=100)
    dynamic['http']['middlewares'] = {'downgrade': {'redirectRegex': {
        'regex': '^https://glpi[.]test/.*', 'replacement': 'http://plain:8080/', 'permanent': False}}}
    (fixture / 'dynamic.yml').write_text(yaml.safe_dump(dynamic))
    (fixture / 'compose.yaml').write_text(yaml.safe_dump(document))
    try:
        dc('config', '--quiet')
        dc('run', '--rm', '--no-deps', 'blackbox-exporter', '--config.file=/etc/blackbox_exporter/blackbox.yml', '--config.check')
        dc('up', '-d', '--wait', 'db', 'glpi', 'traefik', 'plain', 'blackbox-exporter')
        for attempt in range(90):
            if dc('exec', '-T', 'glpi', 'php', '/var/www/glpi/bin/console', 'database:check_schema_integrity',
                  '--no-interaction', check=False).returncode == 0:
                break
            time.sleep(3)
        else:
            raise RuntimeError('Fresh GLPI fixture did not finish installing')
        backend = json.loads(run(['docker', 'network', 'inspect', project + '_backend']).stdout)[0]
        values['glpi_trusted_proxy_subnet'] = backend['IPAM']['Config'][0]['Subnet']
        (fixture / 'guard/blackbox').mkdir(parents=True)
        (fixture / 'guard/blackbox/blackbox.yml').write_text((fixture / 'secure.yml').read_text())
        (fixture / 'guard/compose.yaml').write_text(yaml.safe_dump(secure_compose))

        def guard(extra=None, expected=True):
            candidate = dict(values, observability_project_dir=str(fixture / 'guard'))
            candidate.update(extra or {})
            (fixture / 'guard-vars.json').write_text(json.dumps(candidate))
            result = run(['ansible-playbook', '-i', 'localhost,', 'scripts/ci/test-blackbox-guard.yml',
                          '-e', '@' + str(fixture / 'guard-vars.json')], check=False)
            assert (result.returncode == 0) == expected, 'Actual Ansible guard returned an unexpected result'
            if expected:
                assert 'changed=0' in result.stdout
        guard()
        guard()
        guard(dict(observability_blackbox_targets=legacy), expected=False)
        guard(dict(observability_blackbox_tls_network=''), expected=False)
        for change in [dict(url='http://glpi.test/'), dict(tls_insecure=True), dict(private_ca=False)]:
            target = dict(values['observability_blackbox_targets'][1], **change)
            guard(dict(observability_blackbox_targets=legacy + [target]), expected=False)
        print('PASS: actual Ansible guards, downgrade refusals and read-only second pass')
        run(['docker', 'run', '--rm', '--entrypoint', '/bin/promtool', '-v', f'{fixture}:/fixture:ro',
             '-v', f'{fixture}/alerts.yml:/etc/prometheus/alerts.yml:ro',
             values['observability_prometheus_image'], 'check', 'config', '/fixture/prometheus.yml'])
        dc('cp', str(fixture / 'provision-glpi-oauth.php'), 'glpi:/tmp/provision.php')
        dc('cp', str(fixture / 'secrets/glpi_oauth_secret'), 'glpi:/tmp/oauth-secret')
        dc('exec', '-T', 'glpi', 'php', '/var/www/glpi/bin/console', 'security:change_oauth_key', '--no-interaction')
        identifier = dc('exec', '-T', 'glpi', 'php', '/tmp/provision.php', 'IOP disposable OAuth', '/tmp/oauth-secret').stdout.strip()
        (fixture / 'secrets/glpi_oauth_client_id').write_text(identifier)
        baseline = sql('SELECT COUNT(*) FROM glpi.glpi_tickets;')
        db_id = dc('ps', '-q', 'db').stdout.strip()

        def oauth():
            dc('run', '--rm', '--no-deps', 'bridge', 'python', '/usr/local/libexec/zabbix-glpi-bridge.py', 'check-glpi-oauth')

        def probe(module, url, expected):
            code = ('import urllib.request,urllib.parse; '
                    f'u="http://blackbox-exporter:9115/probe?"+urllib.parse.urlencode({{"module":{module!r},"target":{url!r}}}); '
                    'm=urllib.request.urlopen(u).read().decode(); '
                    f'assert "probe_success {expected}" in m, m')
            client(code)

        oauth()
        probe('http_glpi', 'https://glpi.test/', 1)
        probe('http_untrusted', 'https://glpi.test/', 0)
        probe('http_glpi', 'https://wrong.test/', 0)
        probe('http_glpi', 'http://plain:8080/', 0)
        probe('http_glpi', 'https://glpi.test/downgrade', 0)
        probe('http_legacy', 'http://plain:8080/', 1)
        # Actual bridge client must reject trust and hostname failures under Python 3.13.
        for cert, url in [('/run/ca/internal-api-ca.crt', 'https://wrong.test/api.php'),
                          ('/run/ca/untrusted.crt', 'https://glpi.test/api.php')]:
            result = client(f'import os,sys;sys.path.insert(0,"/usr/local/libexec");'
                            f'os.environ["SSL_CERT_FILE"]={cert!r};os.environ["GLPI_URL"]={url!r};'
                            'exec(open("/usr/local/libexec/zabbix-glpi-bridge.py").read().split("def main()")[0]);GLPI().authenticate()', check=False)
            assert result.returncode != 0, 'Bridge accepted an untrusted/mismatched endpoint'
            assert 'CERTIFICATE_VERIFY_FAILED' in result.stderr, 'Negative control failed for a non-TLS reason'
        redirect = client('exec(open("/usr/local/libexec/zabbix-glpi-bridge.py").read().split("def main()")[0]);'
                          'json_request("https://glpi.test/downgrade")', check=False)
        assert redirect.returncode != 0 and 'origin change refused' in redirect.stderr
        html = client('exec(open("/usr/local/libexec/zabbix-glpi-bridge.py").read().split("def main()")[0]);'
                      'json_request("http://plain:8080/")', check=False)
        assert html.returncode != 0 and 'maintenance mode' in html.stderr
        print('PASS: OAuth HTTPS, private CA, hostname/HTTP rejection and legacy collection')
        # Cookies are enabled only after both API and probe have passed.
        render()
        (fixture / 'blackbox.yml').write_text(yaml.safe_dump(blackbox))
        app['volumes'] += ['./php-security.ini:/usr/local/etc/php/conf.d/zzz-iop-security.ini:ro',
                           './proxy-https.conf:/etc/apache2/conf-enabled/zz-iop-proxy-https.conf:ro']
        (fixture / 'compose.yaml').write_text(yaml.safe_dump(document))
        dc('up', '-d', '--no-deps', '--force-recreate', 'glpi')
        time.sleep(5)
        oauth()
        probe('http_glpi', 'https://glpi.test/', 1)
        client('import urllib.request; r=urllib.request.urlopen("https://glpi.test/"); '
               'cookies=r.headers.get_all("Set-Cookie", []); '
               'assert any("secure" in c.lower() and "httponly" in c.lower() for c in cookies), cookies')
        # Back up the fresh fixture with maintenance enabled, restore to a distinct
        # database and change the mode only on that restored copy. No OPS backup.
        dc('exec', '-T', 'glpi', 'php', '/var/www/glpi/bin/console', 'maintenance:enable', '--no-interaction')
        dump = dc('exec', '-T', 'db', 'sh', '-c',
                  'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb-dump -uroot --single-transaction glpi').stdout
        sql("CREATE DATABASE glpi_restored; GRANT ALL ON glpi_restored.* TO 'glpi'@'%';")
        dc('exec', '-T', 'db', 'sh', '-c',
           'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb -uroot glpi_restored', stdin=dump)
        configuration = dc('exec', '-T', 'glpi', 'cat', '/var/glpi/config/config_db.php').stdout
        restored = ''.join(line.replace('glpi', 'glpi_restored') if 'dbdefault' in line else line
                           for line in configuration.splitlines(keepends=True))
        assert restored != configuration, 'Restored database selection was not explicit'
        (fixture / 'restored-db.php').write_text(restored)
        dc('cp', str(fixture / 'restored-db.php'), 'glpi:/var/glpi/config/config_db.php')
        dc('up', '-d', '--no-deps', '--force-recreate', 'glpi')
        time.sleep(5)
        result = dc('run', '--rm', '--no-deps', 'bridge', 'python', '/usr/local/libexec/zabbix-glpi-bridge.py', 'check-glpi-oauth', check=False)
        print('INFO: Restored-copy maintenance OAuth rejected=' + str(result.returncode != 0))
        dc('exec', '-T', 'glpi', 'php', '/var/www/glpi/bin/console', 'maintenance:disable', '--no-interaction')
        oauth()
        assert sql("SELECT value FROM glpi.glpi_configs WHERE name='maintenance_mode' AND context='core';") == '1'
        assert sql("SELECT value FROM glpi_restored.glpi_configs WHERE name='maintenance_mode' AND context='core';") == '0'
        # Explicit rollback of the probe file on the disposable copy, then forward again.
        (fixture / 'blackbox.yml').write_text(legacy_config)
        dc('up', '-d', '--no-deps', '--force-recreate', 'blackbox-exporter')
        probe('http_legacy', 'http://plain:8080/', 1)
        (fixture / 'blackbox.yml').write_text(yaml.safe_dump(blackbox))
        dc('up', '-d', '--no-deps', '--force-recreate', 'blackbox-exporter')
        probe('http_glpi', 'https://glpi.test/', 1)
        ids = dc('ps', '-q', 'glpi', 'blackbox-exporter', 'db').stdout
        dc('up', '-d', '--no-deps', 'glpi', 'blackbox-exporter', 'db')
        assert ids == dc('ps', '-q', 'glpi', 'blackbox-exporter', 'db').stdout
        assert db_id == dc('ps', '-q', 'db').stdout.strip()
        assert baseline == sql('SELECT COUNT(*) FROM glpi.glpi_tickets;'), 'Ticket count changed'
        assert baseline == sql('SELECT COUNT(*) FROM glpi_restored.glpi_tickets;'), 'Restored ticket count changed'
        for service in document['services'].values():
            assert not service.get('ports'), 'Fixture publishes additional ports'
        assert json.loads(run(['docker', 'network', 'inspect', project + '_api']).stdout)[0]['Internal']
        print('PASS: cookie compatibility, maintenance diagnosis, rollback, idempotence, unchanged database and ticket count')
    finally:
        # Deletes only this generated project on the ephemeral runner; never global prune.
        dc('down', '--volumes', '--remove-orphans', check=False)


if __name__ == '__main__':
    main()
