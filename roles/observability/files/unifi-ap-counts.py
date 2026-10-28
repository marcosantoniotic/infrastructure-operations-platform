#!/usr/bin/env python3
"""Read UniFi AP counts over internal HTTPS with chain/name verification.

Optional OCSP is enforced after verified handshake, before application bytes.
"""
import http.client
import http.cookiejar
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.parse
import urllib.error
import urllib.request

CONFIG_PATH = Path('/etc/iop-unifi-ap-counts.json')


def connection_classes(config):
    hostname = config['hostname']
    address = str(ipaddress.ip_address(config['internal_address']))
    port = int(config.get('port', 443))
    policy = None
    if config.get('ocsp_policy_file'):
        from unifi_ocsp import Policy
        policy = Policy(json.loads(Path(config['ocsp_policy_file']).read_text()))

    class InternalHTTPSConnection(http.client.HTTPSConnection):
        def connect(self):
            if self.host != hostname or self.port != port:
                raise ValueError('Unexpected UniFi TLS destination')
            if self._context.verify_mode != ssl.CERT_REQUIRED or not self._context.check_hostname:
                raise ValueError('Verified TLS is mandatory')
            raw = socket.create_connection((address, port), self.timeout, self.source_address)
            try:
                self.sock = self._context.wrap_socket(raw, server_hostname=hostname)
                if policy:
                    policy.check(self.sock.getpeercert(binary_form=True))
            except Exception as error:
                if policy and isinstance(error, ssl.SSLError):
                    try:
                        policy.record('tls', False)
                    except Exception:
                        pass
                if self.sock is not None:
                    self.sock.close()
                raw.close()
                raise

    class InternalHTTPSHandler(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(InternalHTTPSConnection, req, context=self._context)

    class InternalRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            origin = hostname if port == 443 else hostname + ':' + str(port)
            if policy or urllib.parse.urlsplit(newurl)[:2] != ('https', origin):
                raise ValueError('Unexpected UniFi redirect destination')
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return InternalHTTPSHandler, InternalRedirectHandler


def collect(config):
    if config.get('url') and config.get('username'):
        env = {'UP_UNIFI_DEFAULT_URL': config['url'], 'UP_UNIFI_DEFAULT_USER': config['username'],
               'UP_UNIFI_DEFAULT_VERIFY_SSL': 'true'}
    elif config.get('ocsp_policy_file'):
        raise ValueError('Protected collector requires explicit configuration, no Docker socket')
    else:
        inspected = json.loads(subprocess.check_output(['docker', 'inspect', 'observability-unifi-poller-1']))[0]
        env = dict(item.split('=', 1) for item in inspected['Config']['Env'] if '=' in item)

    def setting(name, default=None):
        return env.get('UP_UNIFI_DEFAULT_' + name, env.get('UP_UNIFI_CONTROLLER_0_' + name, default))

    url = setting('URL').rstrip('/')
    authority = config['hostname'] + (':' + str(config['port']) if config.get('port', 443) != 443 else '')
    if url != 'https://' + authority or setting('VERIFY_SSL', 'true').lower() != 'true':
        raise ValueError('UniFi chain/name TLS verification required')
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cafile=config['ca_file'])
    https_handler, redirect_handler = connection_classes(config)
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        https_handler(context=ctx), redirect_handler(), urllib.request.ProxyHandler({}))
    login = urllib.request.Request(url + '/api/auth/login', json.dumps({
        'username': setting('USER'),
        'password': Path(config['password_file']).read_text().strip(),
    }).encode(), {'Content-Type': 'application/json'})
    with opener.open(login, timeout=15) as response:
        response.read()

    def get(path):
        with opener.open(url + path, timeout=15) as response:
            obj = json.load(response)
        if obj.get('meta', {}).get('rc') != 'ok':
            raise RuntimeError('Controller request unsuccessful')
        return obj['data']

    result = ['# TYPE iop_unifi_ap_counts_success gauge', 'iop_unifi_ap_counts_success 1',
              '# TYPE iop_unifi_ap_counts_timestamp_seconds gauge',
              f'iop_unifi_ap_counts_timestamp_seconds {int(time.time())}']
    for metric in ['iop_unifi_ap_users', 'iop_unifi_ap_guests', 'iop_unifi_ap_online']:
        result.append('# TYPE ' + metric + ' gauge')
    for site in get('/proxy/network/api/stat/sites'):
        site_key = site['name']
        site_name = f"{site.get('desc', site_key)} ({site_key})"
        for device in get('/proxy/network/api/s/' + urllib.parse.quote(site_key, safe='') + '/stat/device'):
            if device.get('type') != 'uap':
                continue
            tags = ','.join(f'{k}={json.dumps(str(v), ensure_ascii=True)}' for k, v in
                            [('site_name', site_name), ('name', device['name']), ('source', url)])
            for metric, field in [('iop_unifi_ap_users', 'user-num_sta'), ('iop_unifi_ap_guests', 'guest-num_sta')]:
                value = int(device[field])
                if value < 0:
                    raise ValueError('Invalid client count')
                result.append(f'{metric}{{{tags}}} {value}')
            result.append(f'iop_unifi_ap_online{{{tags}}} {int(device["state"] == 1)}')
    return '\n'.join(result) + '\n'


def main():
    config = json.loads(CONFIG_PATH.read_text())
    dest = Path(config['destination'])
    try:
        text = collect(config)
    except Exception as error:
        text = '# TYPE iop_unifi_ap_counts_success gauge\niop_unifi_ap_counts_success 0\n'
        if isinstance(error, urllib.error.URLError) and isinstance(error.reason, Exception):
            error = error.reason
        reason = getattr(error, 'reason', 'tls' if isinstance(error, ssl.SSLError) else 'collection')
        allowed = {'tls', 'collection', 'revoked', 'unknown', 'signature', 'responder', 'identity',
                   'time', 'dns', 'timeout', 'http', 'malformed', 'cache_expired', 'unavailable', 'clock', 'state', 'config'}
        reason = reason if reason in allowed else 'collection'
        if reason == 'tls' and config.get('ocsp_policy_file'):
            try:
                from unifi_ocsp import Policy
                Policy(json.loads(Path(config['ocsp_policy_file']).read_text())).record('tls', False)
            except Exception:
                pass  # Preserve collection failure even if metrics cannot be written.
        text += '# TYPE iop_unifi_ap_counts_failure gauge\n' + f'iop_unifi_ap_counts_failure{{reason="{reason}"}} 1\n'
        print('UniFi AP count collection failed:', reason)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.unifi-counts-', dir=dest.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
        os.chmod(temporary, 0o644)
        os.replace(temporary, dest)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    if 'iop_unifi_ap_counts_success 1' not in text:
        raise SystemExit(1)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval', type=int, default=0)
    args = parser.parse_args()
    if args.interval and not 10 <= args.interval <= 3600:
        parser.error('interval must be between 10 and 3600 seconds')
    while True:
        try:
            main()
        except SystemExit as error:
            if not args.interval or error.code != 1:
                raise
        if not args.interval:
            break
        time.sleep(args.interval)
