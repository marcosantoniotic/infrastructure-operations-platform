"""WSGI transport-peer boundary replacing netbox-docker's broad proxy wrapper.

REMOTE_ADDR is deliberately retained for audit. Do not wrap this application in
another proxy-header middleware: the input peer must be Granian's socket peer.
"""
import ipaddress
import json
import os
import re


def address(value):
    if not isinstance(value, str) or '%' in value or '/' in value:
        raise ValueError('An exact IP address is required')
    ip = ipaddress.ip_address(value)
    return ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped else ip


def peers(values):
    if not isinstance(values, list) or not values:
        raise ValueError('A nonempty list of exact transport peers is required')
    result = []
    for value in values:
        ip = address(value)
        if ip.is_unspecified or ip.is_multicast:
            raise ValueError('Unspecified/multicast peers are forbidden')
        if str(ip) in result:
            raise ValueError('Duplicate normalized proxy peer')
        result.append(str(ip))
    return result


def authority(value):
    if not isinstance(value, str) or not value or re.search(r'[\s,/%\\@#?]', value):
        raise ValueError('Malformed or ambiguous authority')
    match = re.fullmatch(r'(\[[0-9a-fA-F:]+\]|[A-Za-z0-9.-]+)(?::([0-9]{1,5}))?', value)
    if not match:
        raise ValueError('Malformed authority')
    host, port = match.groups()
    if host.startswith('['):
        host = '[' + str(ipaddress.IPv6Address(host[1:-1])) + ']'
    elif any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
             for label in host.rstrip('.').split('.')):
        raise ValueError('Malformed DNS host')
    if port and not 1 <= int(port) <= 65535:
        raise ValueError('Invalid port')
    return host.lower(), int(port) if port else None


def forwarded(key):
    return key.startswith('HTTP_X_FORWARDED_') or key in {
        'HTTP_FORWARDED', 'HTTP_X_FORWARDED', 'HTTP_X_REAL_IP', 'HTTP_X_SCHEME',
        'HTTP_X_URL_SCHEME', 'HTTP_FRONT_END_HTTPS', 'HTTP_X_ORIGINAL_HOST',
        'HTTP_X_HOST', 'HTTP_X_ORIGINAL_URL', 'HTTP_X_REWRITE_URL',
    }


class ProxyBoundary:
    def __init__(self, application, trusted_peers):
        self.application = application
        self.trusted = frozenset(peers(trusted_peers))

    def __call__(self, environ, start_response):
        # Copy: never mutate a reusable server environment or trust a header peer.
        env = environ.copy()
        try:
            trusted = str(address(env.get('REMOTE_ADDR'))) in self.trusted
        except (ValueError, TypeError):
            trusted = False
        headers = {k: v for k, v in env.items() if forwarded(k)}
        for key in headers:
            del env[key]
        if trusted and headers:
            try:
                # RFC Forwarded and X-Forwarded-* cannot be mixed. WSGI servers
                # normally join duplicate fields with commas: reject all lists.
                if 'HTTP_FORWARDED' in headers:
                    raise ValueError('Unsupported/ambiguous Forwarded family')
                for value in headers.values():
                    if not isinstance(value, str) or not value or any(ord(c) < 33 or ord(c) > 126 for c in value) or ',' in value:
                        raise ValueError('Malformed or multi-value forwarded field')
                proto = headers['HTTP_X_FORWARDED_PROTO']
                if proto not in ('http', 'https'):
                    raise ValueError('Invalid forwarded scheme')
                host = authority(headers['HTTP_X_FORWARDED_HOST'])
                if host != authority(env.get('HTTP_HOST')):
                    raise ValueError('Host disagreement')
                if 'HTTP_X_FORWARDED_FOR' in headers:
                    address(headers['HTTP_X_FORWARDED_FOR'])
                if 'HTTP_X_FORWARDED_PORT' in headers:
                    port = headers['HTTP_X_FORWARDED_PORT']
                    if not port.isascii() or not port.isdigit() or int(port) != (host[1] or (443 if proto == 'https' else 80)):
                        raise ValueError('Port disagreement')
                env['wsgi.url_scheme'] = proto
                # Never replace REMOTE_ADDR. Plugins/audit see the socket peer,
                # not a caller-supplied XFF chain or claimed user address.
            except (KeyError, TypeError, ValueError):
                body = b'Invalid proxy context\n'
                start_response('400 Bad Request', [('Content-Type', 'text/plain'), ('Content-Length', str(len(body)))])
                return [body]
        return self.application(env, start_response)


if __name__ == 'netbox.granian':
    from netbox.wsgi import application as django_application
    from django.conf import settings
    # NetBox 4.6.10 hard-codes these in settings.py: configuration.py values do
    # not override them. Apply only after Django initializes, in the web entry
    # module, never in workers/housekeeping/synchronizer configuration.
    settings.SECURE_PROXY_SSL_HEADER = None
    settings.USE_X_FORWARDED_HOST = False
    settings.USE_X_FORWARDED_PORT = False
    application = ProxyBoundary(django_application, json.loads(os.environ['IOP_NETBOX_TRUSTED_PROXY_PEERS']))
