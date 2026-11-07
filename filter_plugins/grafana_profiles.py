"""Pure rendering and validation. No environment access or deployment."""
import copy
import re
import ssl
from urllib.parse import urlsplit


def grafana_profiles_admin_endpoint(url):
    parsed = urlsplit(url)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query
            or parsed.fragment or parsed.path not in {'', '/'}):
        raise ValueError('Explicit Grafana administrative endpoint required')
    if parsed.scheme == 'https':
        return True
    if parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1', '::1'}:
        return True
    raise ValueError('Administrative HTTP is allowed only over loopback')


def grafana_profiles_policy(image, network, url, ca, username, password):
    if not re.fullmatch(r'(?:sha256:[a-f0-9]{64}|[a-zA-Z0-9._/:-]+@sha256:[a-f0-9]{64})', image):
        raise ValueError('Grafana plugin image must be immutable')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}', network) or network in {'host', 'bridge', 'none'}:
        raise ValueError('Explicit TLS network required')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path != '/api_jsonrpc.php':
        raise ValueError('Explicit HTTPS API hostname required')
    if 'PRIVATE KEY' in ca:
        raise ValueError('Only public CA certificates may be delivered')
    ssl.create_default_context(cadata=ca)
    if not username or username.lower() in {'admin', 'guest'} or len(password) < 24:
        raise ValueError('Dedicated reader credential required')
    return True


def grafana_profile_dashboard(dashboard, label):
    result = copy.deepcopy(dashboard)
    if result['uid'] not in {'iop-profiles-overview', 'iop-profiles-linux', 'iop-profiles-windows', 'iop-profiles-icmp'}:
        raise ValueError('Unexpected dashboard identity')
    if not isinstance(label, str) or not label.strip() or len(label) > 180:
        raise ValueError('Explicit environment label required')
    result['tags'] = [t for t in result.get('tags', []) if t != 'candidate']
    for panel in result.get('panels', []):
        options = panel.get('options', {})
        if panel.get('type') == 'text' and 'content' in options:
            options['content'] = options['content'].replace('LABORATÓRIO SINTÉTICO · PLUGIN OFICIAL ASSINADO', label)
        if panel.get('type') == 'state-timeline' and panel.get('title') == 'Serviços Windows · estado':
            # Many discovered services make a fixed-height timeline unreadable.
            # Reduce only the presentation; query, item identity and history stay intact.
            panel['type'] = 'table'
            panel['gridPos']['h'] = 14
            panel['description'] = 'Último estado coletado por serviço. Parado não equivale automaticamente a falha. Histórico preservado no Zabbix.'
            panel['transformations'] = [
                {'id': 'reduce', 'options': {'reducers': ['lastNotNull'], 'includeTimeField': False, 'mode': 'seriesToRows'}},
                {'id': 'organize', 'options': {'renameByName': {'Field': 'Serviço', 'Last *': 'Estado'}}},
            ]
            panel['options'] = {'showHeader': True, 'cellHeight': 'sm', 'enablePagination': True,
                                'footer': {'show': False}, 'sortBy': [{'displayName': 'Serviço', 'desc': False}]}
            panel['fieldConfig']['defaults']['custom'] = {'align': 'left', 'cellOptions': {'type': 'auto'}, 'filterable': True}
            for mapping in panel['fieldConfig']['defaults'].get('mappings', []):
                if mapping.get('type') == 'value' and '6' in mapping.get('options', {}):
                    mapping['options']['6']['color'] = 'gray'
            panel['fieldConfig']['overrides'] = [
                {'matcher': {'id': 'byName', 'options': 'Estado'}, 'properties': [
                    {'id': 'custom.width', 'value': 150},
                    {'id': 'custom.cellOptions', 'value': {'type': 'color-text'}},
                ]},
            ]
    return result


class FilterModule:
    def filters(self):
        return {'grafana_profiles_policy': grafana_profiles_policy,
                'grafana_profiles_admin_endpoint': grafana_profiles_admin_endpoint,
                'grafana_profile_dashboard': grafana_profile_dashboard}
