import importlib.util
from pathlib import Path
import unittest
import os
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = load('boundary', 'roles/netbox/files/proxy_boundary.py')
policy = load('policy', 'filter_plugins/netbox_proxy.py')


class BoundaryTests(unittest.TestCase):
    def call(self, peer='192.0.2.10', **headers):
        seen = {}
        status = []
        def app(env, start):
            seen.update(env)
            start('200 OK', [])
            return [b'ok']
        env = dict(REMOTE_ADDR=peer, HTTP_HOST='inventory.example.test', **{'wsgi.url_scheme': 'http'})
        env.update(headers)
        runtime.ProxyBoundary(app, ['192.0.2.10'])(env, lambda s, h: status.append(s))
        return status[0], seen

    def test_exact_and_mapped_peer(self):
        for peer in ['192.0.2.10', '::ffff:192.0.2.10']:
            status, env = self.call(peer, HTTP_X_FORWARDED_PROTO='https', HTTP_X_FORWARDED_HOST='inventory.example.test', HTTP_X_FORWARDED_FOR='198.51.100.8', HTTP_X_FORWARDED_PORT='443')
            self.assertEqual(status, '200 OK')
            self.assertEqual(env['wsgi.url_scheme'], 'https')
            self.assertEqual(env['REMOTE_ADDR'], peer)
            self.assertFalse(any(runtime.forwarded(k) for k in env))

    def test_untrusted_spoof_stripped(self):
        for peer in ['192.0.2.11', '::ffff:192.0.2.11', None, 'not-an-ip']:
            status, env = self.call(peer, HTTP_X_FORWARDED_PROTO='https', HTTP_X_FORWARDED_FOR='192.0.2.10', HTTP_X_FORWARDED_HOST='attacker.test', HTTP_FORWARDED='for=192.0.2.10;proto=https', HTTP_X_REAL_IP='192.0.2.10')
            self.assertEqual(status, '200 OK')
            self.assertEqual(env['wsgi.url_scheme'], 'http')
            self.assertEqual(env['HTTP_HOST'], 'inventory.example.test')
            self.assertFalse(any(runtime.forwarded(k) for k in env))

    def test_health_without_headers(self):
        self.assertEqual(self.call()[0], '200 OK')
        self.assertEqual(self.call('127.0.0.1')[0], '200 OK')

    def test_trusted_bad_context(self):
        base = dict(HTTP_X_FORWARDED_PROTO='https', HTTP_X_FORWARDED_HOST='inventory.example.test')
        cases = [dict(HTTP_X_FORWARDED_PROTO='https,http'), dict(HTTP_X_FORWARDED_PROTO='HTTPS'),
                 dict(HTTP_X_FORWARDED_HOST='evil.test'), dict(HTTP_HOST='invalid.test'),
                 dict(HTTP_X_FORWARDED_HOST='inventory.example.test\r\nX:bad'),
                 dict(HTTP_X_FORWARDED_FOR='198.51.100.1,192.0.2.10'),
                 dict(HTTP_X_FORWARDED_FOR='garbage'), dict(HTTP_X_FORWARDED_PORT='80'),
                 dict(HTTP_X_FORWARDED_PORT='0'), dict(HTTP_FORWARDED='proto=https'),
                 dict(HTTP_X_FORWARDED_PROTO=''), dict(HTTP_X_FORWARDED_PROTO=' https')]
        for changed in cases:
            with self.subTest(changed=changed):
                self.assertEqual(self.call(**dict(base, **changed))[0], '400 Bad Request')
        self.assertEqual(self.call(HTTP_X_FORWARDED_PROTO='https')[0], '400 Bad Request')

    def test_ipv6_and_authority(self):
        self.assertEqual(runtime.authority('[2001:db8::1]:443'), ('[2001:db8::1]', 443))
        for bad in ['x:0', 'x:65536', 'x,evil', 'x@evil', 'x/y', 'x..test', 'x:abc']:
            with self.assertRaises(ValueError): runtime.authority(bad)

    def test_inventory(self):
        self.assertTrue(policy.policy(False, False, [], ['localhost'], []))
        self.assertTrue(policy.policy(False, 'false', [], ['localhost'], []))
        self.assertTrue(policy.policy(True, True, ['192.0.2.10'], ['inventory.example.test'], ['https://inventory.example.test']))
        for peers in [[], ['*'], ['192.0.2.0/24'], ['192.0.2.10/32'], ['0.0.0.0'], ['::'], ['proxy'], ['fe80::1%eth0'], ['192.0.2.10', '::ffff:192.0.2.10']]:
            with self.subTest(peers=peers), self.assertRaises(ValueError):
                policy.policy(True, True, peers, ['inventory.example.test'], ['https://inventory.example.test'])
        for cookies, hosts, origins in [(False, ['x'], ['https://x']), (True, ['*'], ['https://x']), (True, ['x'], []), (True, ['x'], ['http://x'])]:
            with self.assertRaises(ValueError): policy.policy(True, cookies, ['192.0.2.10'], hosts, origins)

    def test_installed_guard(self):
        web = {'volumes': ['./proxy-boundary.py:/opt/netbox/netbox/netbox/granian.py:ro', './cookie-security.py:/etc/netbox/config/zz-iop-cookie-security.py:ro'], 'environment': {'IOP_NETBOX_TRUSTED_PROXY_PEERS': '["192.0.2.10"]'}}
        installed = {'services': {'netbox': web}}
        self.assertTrue(policy.preserve(installed, True, True, ['192.0.2.10']))
        for enabled, cookies, peers in [(False, True, ['192.0.2.10']), (True, False, ['192.0.2.10']), (True, True, ['192.0.2.11'])]:
            with self.assertRaises(ValueError): policy.preserve(installed, enabled, cookies, peers)
        self.assertTrue(policy.preserve({}, False, False, []))

    def test_web_patch_preserves_media_and_other_services(self):
        original = {'services': {'netbox': {'image': 'exact-test-image', 'ports': ['127.0.0.1:8000:8080'], 'volumes': ['media_data:/opt/netbox/netbox/media'], 'env_file': ['.env']},
                    'netbox-worker': {'volumes': ['media_data:/opt/netbox/netbox/media']},
                    'netbox-housekeeping': {'command': '/opt/netbox/housekeeping.sh'}},
                    'volumes': {'media_data': {}, 'postgres_data': {}}}
        changed = policy.secure_web_compose(original, ['192.0.2.10'])
        self.assertEqual(changed['services']['netbox-worker'], original['services']['netbox-worker'])
        self.assertEqual(changed['services']['netbox-housekeeping'], original['services']['netbox-housekeeping'])
        self.assertEqual(changed['volumes'], original['volumes'])
        for key in ['image', 'ports', 'env_file']:
            self.assertEqual(changed['services']['netbox'][key], original['services']['netbox'][key])
        self.assertIn('media_data:/opt/netbox/netbox/media', changed['services']['netbox']['volumes'])
        self.assertEqual(policy.secure_web_compose(changed, ['192.0.2.10']), changed)
        self.assertEqual(len(original['services']['netbox']['volumes']), 1)

    def test_patch_conflicting_mount(self):
        for mount in ['./different.py:/opt/netbox/netbox/netbox/granian.py:ro', './proxy-boundary.py:/opt/netbox/netbox/netbox/granian.py:rw']:
            with self.assertRaises(ValueError):
                policy.secure_web_compose({'services': {'netbox': {'volumes': [mount]}}}, ['192.0.2.10'])

    def test_shared_yaml_aliases_never_change_workers(self):
        shared = {'environment': {'EXISTING': 'preserve'}, 'volumes': ['media:/opt/netbox/netbox/media']}
        original = {'x-common': shared, 'services': {'netbox': shared, 'netbox-worker': shared, 'netbox-housekeeping': shared}}
        changed = policy.secure_web_compose(original, ['192.0.2.10'])
        self.assertEqual(changed['x-common'], shared)
        self.assertEqual(changed['services']['netbox-worker'], shared)
        self.assertEqual(changed['services']['netbox-housekeeping'], shared)
        self.assertNotEqual(changed['services']['netbox'], shared)

    def test_cookies_do_not_override_existing_policy(self):
        text = (ROOT/'roles/netbox/templates/cookie-security.py.j2').read_text()
        self.assertIn('CSRF_COOKIE_SECURE = True', text)
        self.assertIn('SESSION_COOKIE_SECURE = True', text)
        for setting in ['HTTPONLY', 'SAMESITE', 'CSRF_TRUSTED_ORIGINS', 'MEDIA_ROOT']:
            self.assertNotIn(setting, text)

    def test_only_reviewed_launchers(self):
        for cmd in [['/opt/netbox/launch-netbox.sh'], ['/bin/bash', '-lc', 'GRANIAN_EXTRA_ARGS=( --static-path-route /media ); source /opt/netbox/launch-netbox.sh']]:
            self.assertTrue(policy.supported_launcher({'services': {'netbox': {'command': cmd}}}))
        for cmd in [None, ['granian', 'netbox.wsgi:application'], 'custom-web-server']:
            with self.assertRaises(ValueError): policy.supported_launcher({'services': {'netbox': {'command': cmd}}})

    def test_web_entry_overrides_hardcoded_django_after_initialization(self):
        settings = types.SimpleNamespace(SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'), USE_X_FORWARDED_HOST=True, USE_X_FORWARDED_PORT=True)
        conf = types.ModuleType('django.conf'); conf.settings = settings
        django = types.ModuleType('django'); django.conf = conf
        netbox = types.ModuleType('netbox'); netbox.__path__ = []
        wsgi = types.ModuleType('netbox.wsgi'); wsgi.application = lambda env, start: []
        with patch.dict(sys.modules, {'django': django, 'django.conf': conf, 'netbox': netbox, 'netbox.wsgi': wsgi}), patch.dict(os.environ, {'IOP_NETBOX_TRUSTED_PROXY_PEERS': '["192.0.2.10"]'}):
            module = load('netbox.granian', 'roles/netbox/files/proxy_boundary.py')
            self.assertIsInstance(module.application, module.ProxyBoundary)
        self.assertIsNone(settings.SECURE_PROXY_SSL_HEADER)
        self.assertFalse(settings.USE_X_FORWARDED_HOST)
        self.assertFalse(settings.USE_X_FORWARDED_PORT)


if __name__ == '__main__': unittest.main()
