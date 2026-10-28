"""Pure inventory/installed-policy validation for the NetBox web boundary."""
import ipaddress
import json
import copy
from urllib.parse import urlsplit


def exact_peers(values):
    if not isinstance(values, list) or not values:
        raise ValueError('Set a nonempty list of exact proxy IPs (no CIDRs/hostnames)')
    result = []
    for value in values:
        if not isinstance(value, str) or '/' in value or '%' in value:
            raise ValueError('Only exact proxy IPs are allowed')
        ip = ipaddress.ip_address(value)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if ip.is_unspecified or ip.is_multicast or str(ip) in result:
            raise ValueError('Invalid or duplicate normalized proxy peer')
        result.append(str(ip))
    return result


def policy(enabled, secure_cookies, trusted, hosts, origins):
    if not isinstance(enabled, bool) or (enabled and not isinstance(secure_cookies, bool)):
        raise ValueError('Security switches must be YAML booleans')
    if enabled:
        exact_peers(trusted)
        if not secure_cookies or not isinstance(hosts, list) or not hosts or any(not isinstance(h, str) or not h or '*' in h or h.startswith('.') or any(c.isspace() for c in h) for h in hosts):
            raise ValueError('Boundary requires Secure cookies and explicit allowed hosts')
        if not isinstance(origins, list) or not origins:
            raise ValueError('Boundary requires explicit HTTPS CSRF origins')
        for origin in origins:
            parsed = urlsplit(origin)
            if (parsed.scheme != 'https' or not parsed.hostname or '*' in origin
                    or parsed.username or parsed.password or parsed.path
                    or parsed.query or parsed.fragment or any(c.isspace() for c in origin)):
                raise ValueError('Use explicit HTTPS CSRF origins without credentials/path')
    elif trusted:
        raise ValueError('Proxy peers configured while boundary is disabled')
    return True


class FilterModule:
    def filters(self):
        return {'iop_netbox_exact_peers': exact_peers, 'iop_netbox_proxy_policy': policy,
                'iop_netbox_preserve_proxy': preserve, 'iop_netbox_secure_web_compose': secure_web_compose,
                'iop_netbox_web_launcher': supported_launcher}


def supported_launcher(compose):
    command = (compose or {}).get('services', {}).get('netbox', {}).get('command')
    if command == ['/opt/netbox/launch-netbox.sh']:
        return True
    if (isinstance(command, list) and len(command) == 3 and
            command[:2] == ['/bin/bash', '-lc'] and isinstance(command[2], str) and
            'source /opt/netbox/launch-netbox.sh' in command[2] and
            'netbox.wsgi:' not in command[2]):
        return True
    raise ValueError('Review custom web launcher before replacing the Granian trust boundary')


def preserve(compose, enabled, cookies, trusted):
    web = (compose or {}).get('services', {}).get('netbox', {})
    mounts = web.get('volumes', [])
    targets = [m.get('target', '') if isinstance(m, dict) else m.split(':')[1]
               for m in mounts]
    environment = web.get('environment', {}) or {}
    if isinstance(environment, list):
        environment = dict(x.split('=', 1) for x in environment if '=' in x)
    marked = 'IOP_NETBOX_TRUSTED_PROXY_PEERS' in environment
    boundary = '/opt/netbox/netbox/netbox/granian.py' in targets
    settings = '/etc/netbox/config/zz-iop-proxy-security.py' in targets
    cookie = '/etc/netbox/config/zz-iop-cookie-security.py' in targets
    if marked or boundary or settings:
        if not (marked and boundary and cookie and enabled and cookies):
            raise ValueError('Incomplete installed boundary or silent security removal')
        old = json.loads(environment['IOP_NETBOX_TRUSTED_PROXY_PEERS'])
        if set(exact_peers(old)) != set(exact_peers(trusted)):
            raise ValueError('Installed exact proxy peer set changed; review migration explicitly')
    return True


def secure_web_compose(compose, trusted):
    """Patch only web mounts/environment, preserving all other installed state."""
    result = copy.deepcopy(compose)
    # Break YAML-anchor aliases: changing a shared common/environment/volume
    # mapping must never mutate worker or housekeeping through the alias.
    web = copy.deepcopy(result['services']['netbox'])
    result['services']['netbox'] = web
    wanted = {
        '/etc/netbox/config/zz-iop-cookie-security.py': './cookie-security.py',
        '/opt/netbox/netbox/netbox/granian.py': './proxy-boundary.py',
    }
    mounts = web.setdefault('volumes', [])
    for target, source in wanted.items():
        present = []
        for mount in mounts:
            if isinstance(mount, dict):
                if mount.get('target') == target:
                    if mount.get('source') != source or not mount.get('read_only'):
                        raise ValueError('Conflicting installed security mount')
                    present.append(mount)
            else:
                parts = mount.split(':')
                if len(parts) > 1 and parts[1] == target:
                    if parts[0] != source or len(parts) != 3 or 'ro' not in parts[2].split(','):
                        raise ValueError('Conflicting installed security mount')
                    present.append(mount)
        if len(present) > 1:
            raise ValueError('Duplicate security target')
        if not present:
            mounts.append(f'{source}:{target}:ro,Z')
    env = web.get('environment', {}) or {}
    if isinstance(env, list):
        if any('=' not in x for x in env):
            raise ValueError('Resolve inherited environment entries explicitly before web patch')
        pairs = [x.split('=', 1) for x in env]
        if len({x[0] for x in pairs}) != len(pairs):
            raise ValueError('Duplicate installed environment entries')
        env = dict(pairs)
    env['IOP_NETBOX_TRUSTED_PROXY_PEERS'] = json.dumps(exact_peers(trusted))
    web['environment'] = env
    return result
