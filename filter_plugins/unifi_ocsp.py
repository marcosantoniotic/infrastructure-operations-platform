"""Fail-closed inventory and installed-state guards; no network side effects."""
import copy
import ipaddress
import re
from urllib.parse import urlsplit


def policy(enabled, poller, verify, image, url, settings):
    if not isinstance(enabled, bool):
        raise ValueError('OCSP opt-in must be a boolean')
    if not enabled:
        return True
    origin = urlsplit(url)
    responder = urlsplit(settings.get('responder_url', ''))
    if (poller is not True or verify is not True or
            not re.fullmatch(r'(?:[^\s]+@)?sha256:[a-f0-9]{64}', image) or
            origin.scheme != 'https' or not origin.hostname or origin.username or origin.password or
            origin.path not in ('', '/') or origin.query or origin.fragment or
            responder.scheme not in ('http', 'https') or not responder.hostname or
            responder.username or responder.password or not responder.path or responder.query or responder.fragment):
        raise ValueError('Coordinated verified HTTPS, immutable image and explicit OCSP endpoint required')
    for key in ['responder_address', 'controller_address']:
        address = ipaddress.ip_address(settings[key])
        if address.is_unspecified or address.is_multicast:
            raise ValueError('Explicit unicast destination addresses required')
    origin.port
    responder.port
    for name, low, high in [('timeout_seconds', 1, 5), ('response_limit', 1, 65536),
                            ('cache_entries', 1, 128), ('clock_skew_seconds', 0, 120),
                            ('max_age_seconds', 1, 3600), ('cache_ttl_seconds', 1, 300)]:
        value = settings.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError('Missing or excessive bounded OCSP policy')
    if settings['cache_ttl_seconds'] > settings['max_age_seconds']:
        raise ValueError('Cache cannot outlive response age policy')
    return True


def preserve(compose, enabled, image, previous_image=''):
    services = (compose or {}).get('services', {})
    protected = []
    for name in ['unifi-poller', 'unifi-ap-counts']:
        service = services.get(name, {})
        env = service.get('environment', {}) or {}
        if isinstance(env, list):
            env = dict(v.split('=', 1) for v in env if '=' in v)
        protected.append(bool(env.get('IOP_UNIFI_OCSP_POLICY')))
    if any(protected) and (not all(protected) or not enabled):
        raise ValueError('Cannot remove or partially disable installed OCSP')
    if any(protected):
        for name in ['unifi-poller', 'unifi-ap-counts']:
            if services[name].get('image') != image and services[name].get('image') != previous_image:
                raise ValueError('Review coordinated OCSP-capable image replacement explicitly')
    return True


def compose_patch(compose, image, metrics_dir='./unifi-ocsp/metrics'):
    result = copy.deepcopy(compose)
    poller = copy.deepcopy(result['services']['unifi-poller'])
    result['services']['unifi-poller'] = poller
    env = poller.get('environment', {}) or {}
    if not isinstance(env, dict):
        raise ValueError('Resolve list or inherited environment before OCSP migration')
    if str(env.get('UP_UNIFI_DEFAULT_VERIFY_SSL', '')).lower() != 'true':
        raise ValueError('Preserve normal TLS verification')
    if any('cert' in str(key).lower() or 'remote' in str(key).lower() for key in env):
        raise ValueError('Pinning/remote modes need explicit review and are not supported')
    poller['image'] = image
    poller.pop('build', None)
    env.update(IOP_UNIFI_OCSP_POLICY='/etc/iop-ocsp/policy.json',
               IOP_UNIFI_OCSP_PYTHON='/usr/local/bin/python3',
               IOP_UNIFI_OCSP_VERIFIER='/opt/iop/unifi_ocsp.py',
               IOP_UNIFI_OCSP_CA_FILE='/etc/iop-ocsp/ca.pem')
    # Address is supplied separately by the reviewed deployment task.
    poller['environment'] = env
    mounts = poller.setdefault('volumes', [])
    additions = ['./unifi-ocsp/unpoller:/etc/iop-ocsp:ro,Z',
                 './unifi-ocsp/unpoller-state:/var/lib/iop-ocsp:rw,Z',
                 metrics_dir + ':/metrics:rw,Z']
    for mount in additions:
        target = mount.split(':')[1]
        existing = [m for m in mounts if (m.get('target') if isinstance(m, dict) else m.split(':')[1]) == target]
        if existing and existing != [mount]:
            raise ValueError('Conflicting OCSP mount')
        if not existing:
            mounts.append(mount)
    ap = copy.deepcopy(poller)
    ap['entrypoint'] = ['/usr/local/bin/python3', '/opt/iop/unifi-ap-counts.py']
    ap['command'] = ['--interval', '60']
    ap['volumes'] = ['./unifi-ocsp/ap:/etc/iop-ocsp:ro,Z',
                     './unifi-ocsp/ap/config.json:/etc/iop-unifi-ap-counts.json:ro,Z',
                     './unifi-ocsp/ap-state:/var/lib/iop-ocsp:rw,Z',
                     './secrets/unifi_password:/run/secrets/unifi_password:ro,Z',
                     metrics_dir + ':/metrics:rw,Z']
    for key in ['ports', 'healthcheck', 'labels', 'container_name']:
        ap.pop(key, None)
    if 'unifi-ap-counts' in result['services']:
        previous = copy.deepcopy(result['services']['unifi-ap-counts'])
        previous['image'] = image  # Previous digest is attested by preserve().
        if previous != ap:
            raise ValueError('Review existing AP collector service before replacing')
    result['services']['unifi-ap-counts'] = ap
    return result


class FilterModule:
    def filters(self):
        return {'iop_unifi_ocsp_policy': policy, 'iop_unifi_ocsp_preserve': preserve,
                'iop_unifi_ocsp_compose': compose_patch}
