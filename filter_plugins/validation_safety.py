"""Small, deterministic validation helpers; never read hosts or secret files."""
import ipaddress


def trusted_proxy_cidr(value):
    try:
        net = ipaddress.IPv4Network(value, strict=True)
        return 8 <= net.prefixlen <= 32 and not (
            net.network_address.is_unspecified or net.network_address.is_multicast
        )
    except (ValueError, TypeError):
        return False


def installed_features(compose, service):
    config = (compose or {}).get('services', {}).get(service, {})
    mounts = config.get('volumes', []) or []
    targets = []
    for mount in mounts:
        if isinstance(mount, dict):
            targets.append(mount.get('target', ''))
        elif isinstance(mount, str) and ':' in mount:
            targets.append(mount.split(':')[1])
    return {
        'php_security': any(t.endswith(('zzz-lab01-security.ini', 'zzz-iop-security.ini')) for t in targets),
        'https_cookies': any(t.endswith('proxy-https.conf') for t in targets),
        'netbox_cookies': any(t.endswith('cookie-security.py') for t in targets),
        'zabbix_https': any(t.endswith('cookie-context.conf') for t in targets),
    }


def external_volume_name(volume):
    if not isinstance(volume, dict):
        raise ValueError('Installed volume definition must be a mapping')
    external = volume.get('external', False)
    if isinstance(external, dict):
        name = external.get('name') or volume.get('name')
    elif external is True:
        name = volume.get('name') or 'mysql_data'
    elif external is False or external is None:
        return ''
    else:
        raise ValueError('Installed volume external flag must be a boolean or mapping')
    if not isinstance(name, str) or not name:
        raise ValueError('Installed external volume needs an explicit identity')
    return name


class FilterModule:
    def filters(self):
        return {'iop_trusted_proxy_cidr': trusted_proxy_cidr,
                'iop_installed_features': installed_features,
                'iop_external_volume_name': external_volume_name}
