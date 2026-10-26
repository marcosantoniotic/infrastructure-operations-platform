"""Pure TLS policy checks. No network, secrets or installed-file reads."""
import re
from urllib.parse import urlsplit


def validate_targets(targets, certificate='', network=''):
    if not isinstance(targets, list):
        raise ValueError('Blackbox targets must be a list')
    names = set()
    if network and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', network):
        raise ValueError('Invalid private TLS network name')
    if certificate and not (certificate.strip().startswith('-----BEGIN CERTIFICATE-----')
                            and certificate.strip().endswith('-----END CERTIFICATE-----')):
        raise ValueError('Public CA must be a PEM certificate, never a key')
    if certificate and certificate.count('-----BEGIN CERTIFICATE-----') != 1:
        raise ValueError('Use one explicitly validated root CA; the server supplies its intermediate chain')
    if 'PRIVATE KEY' in certificate:
        raise ValueError('A public CA certificate, not a private key, is required')
    for target in targets:
        name = target.get('name', '')
        module = re.sub('[^A-Za-z0-9_]', '_', name)
        if not module or module in names:
            raise ValueError('Blackbox module names must be nonempty and unique after normalization')
        names.add(module)
        for field in ('require_https', 'private_ca', 'tls_insecure'):
            if field in target and not isinstance(target[field], bool):
                raise ValueError(f'{field} must be a boolean')
        url = urlsplit(target.get('url', ''))
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            raise ValueError('Target requires an HTTP(S) URL without credentials')
        secure = target.get('require_https', False)
        private = target.get('private_ca', False)
        if (secure or private) and (url.scheme != 'https' or target.get('tls_insecure', False)):
            raise ValueError('Protected targets require HTTPS with chain and hostname verification')
        if (secure or private) and target.get('host_header', url.hostname) != url.hostname:
            raise ValueError('Use a URL hostname matching DNS, Host and certificate SNI')
        if 'tls_server_name' in target:
            raise ValueError('Use the certificate DNS name in the URL, not an SNI override')
        if private and (not secure or not certificate or not network):
            raise ValueError('Private CA targets require HTTPS enforcement, CA and internal network')
    return True


def preserve_policy(installed, targets, network='', installed_network=''):
    """Refuse removal of recognized protected targets; explicit rollback is separate."""
    current = {'http_' + re.sub('[^A-Za-z0-9_]', '_', t['name']): t for t in targets}
    for module, config in (installed or {}).get('modules', {}).items():
        http = config.get('http', {})
        tls = http.get('tls_config', {})
        protected = http.get('fail_if_not_ssl', False) or tls.get('ca_file')
        if not protected:
            continue
        target = current.get(module)
        if not target or not target.get('require_https') or target.get('tls_insecure', False):
            raise ValueError('Installed protected target cannot be removed or downgraded silently')
        if tls.get('ca_file') and not target.get('private_ca'):
            raise ValueError('Installed private CA trust must be preserved')
    if installed_network and installed_network != network:
        raise ValueError('Installed private TLS network must be preserved')
    return True


class FilterModule:
    def filters(self):
        return {'iop_blackbox_tls_targets': validate_targets,
                'iop_blackbox_preserve_tls': preserve_policy}
