#!/usr/bin/env python3
"""Build a NEW, self-contained, fictitious API fixture. Never points at an existing stack.

Run on the explicitly approved disposable Docker host, not a production host.
The output directory must not exist. No ports, external networks or external volumes.
Secrets/CA are test-only, private, and are never included in public evidence.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import yaml

IMAGES = {
    'netbox': 'iop-isolated/netbox:4.6.10-topology-4.5.1-qrcode-0.0.21',
    'postgres': 'postgres:18-alpine', 'redis': 'valkey/valkey:9.0-alpine',
    'mysql': 'mysql:8.4.10-oraclelinux9',
    'zabbix-server': 'zabbix/zabbix-server-mysql:alpine-7.4.13',
    'zabbix-web': 'zabbix/zabbix-web-nginx-mysql:alpine-7.4.13',
    'proxy': 'traefik:v3.7.13',
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('directory', type=Path)
    p.add_argument('--run-id', required=True)
    p.add_argument('--revision', required=True)
    p.add_argument('--subnet', help='Optional dedicated subnet; otherwise Docker allocates a free one')
    args = p.parse_args()
    if not args.run_id.startswith('synthetic-ip-') or not args.run_id.replace('-', '').isalnum():
        raise SystemExit('Refusing non-synthetic run ID')
    os.umask(0o077)
    root = args.directory.resolve()
    root.mkdir(mode=0o700, exist_ok=False)
    for name in ('secrets', 'tls', 'evidence'):
        (root / name).mkdir(mode=0o700)

    def write(name, value):
        (root / name).write_text(value, encoding='utf-8')

    values = {n: secrets.token_urlsafe(40) for n in ('db', 'redis', 'mysql', 'mysqlroot', 'admin', 'secret', 'pepper', 'zadmin')}
    write('secrets/mysql', values['mysql'])
    write('secrets/mysqlroot', values['mysqlroot'])
    write('secrets/bootstrap.json', json.dumps({'admin_password': values['zadmin']}))
    write('manifest.json', json.dumps({'run_id': args.run_id, 'revision': args.revision, 'images': IMAGES}, indent=2))
    env = dict(ALLOWED_HOSTS='netbox.functional.example.test localhost',
        CSRF_TRUSTED_ORIGINS='https://netbox.functional.example.test',
        MEDIA_ROOT='/opt/netbox/netbox/media', DB_HOST='postgres', DB_NAME='netbox', DB_USER='netbox',
        DB_PASSWORD=values['db'], POSTGRES_DB='netbox', POSTGRES_USER='netbox', POSTGRES_PASSWORD=values['db'],
        REDIS_HOST='redis', REDIS_PASSWORD=values['redis'], REDIS_CACHE_HOST='redis-cache',
        REDIS_CACHE_PASSWORD=values['redis'], SECRET_KEY=values['secret'], API_TOKEN_PEPPER_1=values['pepper'],
        SUPERUSER_NAME='synthetic-admin', SUPERUSER_EMAIL='synthetic-admin@example.test',
        SUPERUSER_PASSWORD=values['admin'], SKIP_SUPERUSER='false', METRICS_ENABLED='false')
    write('.env', '\n'.join(f'{k}={v}' for k, v in env.items()) + '\n')
    write('cookie-security.py', 'SESSION_COOKIE_SECURE = True\nCSRF_COOKIE_SECURE = True\n')
    for name in ('secrets/mysql', 'secrets/mysqlroot', 'cookie-security.py'):
        (root / name).chmod(0o444)

    def openssl(*a):
        subprocess.run(['openssl', *a], cwd=root / 'tls', check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '5', '-sha256',
        '-keyout', 'ca.key', '-out', 'ca.crt', '-subj', '/CN=Synthetic IP Sync Test CA',
        '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
    openssl('req', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'leaf.key', '-out', 'leaf.csr',
        '-subj', '/CN=netbox.functional.example.test')
    write('tls/leaf.ext', 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:netbox.functional.example.test,DNS:zabbix.functional.example.test\n')
    openssl('x509', '-req', '-in', 'leaf.csr', '-CA', 'ca.crt', '-CAkey', 'ca.key', '-CAcreateserial',
        '-out', 'leaf.crt', '-days', '5', '-sha256', '-extfile', 'leaf.ext')
    openssl('verify', '-x509_strict', '-CAfile', 'ca.crt', 'leaf.crt')
    (root / 'tls/ca.crt').chmod(0o444)
    write('dynamic.yml', yaml.safe_dump({
        'tls': {'certificates': [{'certFile': '/tls/leaf.crt', 'keyFile': '/tls/leaf.key'}]},
        'http': {'routers': {name: {'rule': f'Host(`{name}.functional.example.test`)',
            'entryPoints': ['websecure'], 'tls': {}, 'service': name} for name in ('netbox', 'zabbix')},
            'services': {name: {'loadBalancer': {'servers': [{'url': url}]}} for name, url in (
                ('netbox', 'http://netbox:8080'), ('zabbix', 'http://zabbix-web:8080'))}}}))
    secret_mounts = ['./secrets/mysql:/run/secrets/mysql:ro,Z', './secrets/mysqlroot:/run/secrets/mysqlroot:ro,Z']
    db_env = dict(DB_SERVER_HOST='mysql', MYSQL_DATABASE='zabbix', MYSQL_USER='zabbix',
                  MYSQL_PASSWORD_FILE='/run/secrets/mysql', MYSQL_ROOT_PASSWORD_FILE='/run/secrets/mysqlroot')
    services = {
        'postgres': dict(image=IMAGES['postgres'], env_file=['.env'], volumes=['postgres:/var/lib/postgresql'],
            healthcheck=dict(test=['CMD-SHELL', 'pg_isready -U netbox -d netbox'], interval='5s', retries=30)),
        'redis': dict(image=IMAGES['redis'], env_file=['.env'], command=['sh', '-c', 'exec valkey-server --requirepass "$${REDIS_PASSWORD}"']),
        'redis-cache': dict(image=IMAGES['redis'], env_file=['.env'], command=['sh', '-c', 'exec valkey-server --requirepass "$${REDIS_CACHE_PASSWORD}"']),
        'netbox': dict(image=IMAGES['netbox'], env_file=['.env'],
            environment={'REQUESTS_CA_BUNDLE': '/tls/ca.crt', 'SSL_CERT_FILE': '/tls/ca.crt'},
            volumes=['media:/opt/netbox/netbox/media', './cookie-security.py:/etc/netbox/config/zz-iop-cookie-security.py:ro,Z',
                     './tls/ca.crt:/tls/ca.crt:ro,Z', '.:/fixture:rw,Z'],
            depends_on={'postgres': {'condition': 'service_healthy'}, 'redis': {'condition': 'service_started'}, 'redis-cache': {'condition': 'service_started'}}),
        'mysql': dict(image=IMAGES['mysql'], environment={
            'MYSQL_DATABASE': 'zabbix', 'MYSQL_USER': 'zabbix', 'MYSQL_PASSWORD_FILE': '/run/secrets/mysql',
            'MYSQL_ROOT_PASSWORD_FILE': '/run/secrets/mysqlroot'},
            command=['--character-set-server=utf8mb4', '--collation-server=utf8mb4_bin', '--log-bin-trust-function-creators=1'],
            volumes=['mysql:/var/lib/mysql', *secret_mounts],
            healthcheck=dict(test=['CMD-SHELL', 'mysqladmin ping --silent --host=127.0.0.1 --user=root --password="$$(cat /run/secrets/mysqlroot)"'], interval='5s', retries=60)),
        'zabbix-server': dict(image=IMAGES['zabbix-server'], environment=db_env, volumes=secret_mounts,
            depends_on={'mysql': {'condition': 'service_healthy'}}),
        'zabbix-web': dict(image=IMAGES['zabbix-web'], environment={**db_env, 'ZBX_SERVER_HOST': 'zabbix-server',
            'ZBX_SERVER_NAME': 'Synthetic IP sync only', 'PHP_TZ': 'America/Sao_Paulo'}, volumes=secret_mounts,
            depends_on={'mysql': {'condition': 'service_healthy'}, 'zabbix-server': {'condition': 'service_started'}}),
        'proxy': dict(image=IMAGES['proxy'], command=['--entrypoints.websecure.address=:443',
            '--providers.file.filename=/config/dynamic.yml', '--log.level=WARN'],
            volumes=['./tls:/tls:ro,Z', './dynamic.yml:/config/dynamic.yml:ro,Z']),
    }
    for name, service in services.items():
        service['networks'] = {'test': {'aliases': ['netbox.functional.example.test', 'zabbix.functional.example.test']} if name == 'proxy' else {}}
        service['labels'] = {'iop.synthetic.run': args.run_id}
        service['restart'] = 'no'
    network = {'internal': True, 'labels': {'iop.synthetic.run': args.run_id}}
    if args.subnet:
        network['ipam'] = {'config': [{'subnet': args.subnet}]}
    compose = dict(name=args.run_id, services=services,
        networks={'test': network},
        volumes={n: {'labels': {'iop.synthetic.run': args.run_id}} for n in ('postgres', 'mysql', 'media')})
    write('compose.yml', yaml.safe_dump(compose, sort_keys=False))
    print(json.dumps({'prepared': args.run_id, 'ports_published': 0, 'external_networks': 0, 'external_volumes': 0}))


if __name__ == '__main__':
    main()
