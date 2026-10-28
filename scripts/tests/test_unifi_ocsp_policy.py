import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('unifi_ocsp_filter', ROOT / 'filter_plugins/unifi_ocsp.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.image = 'example.invalid/unpoller-ocsp@sha256:' + 'a' * 64
        self.settings = {'controller_address': '192.0.2.10', 'responder_address': '192.0.2.20',
                         'responder_url': 'http://ocsp.example.test/status', 'timeout_seconds': 5,
                         'response_limit': 65536, 'cache_entries': 128, 'clock_skew_seconds': 120,
                         'max_age_seconds': 3600, 'cache_ttl_seconds': 300}
        self.compose = {'services': {'unifi-poller': {'image': 'old-image',
            'environment': {'UP_UNIFI_DEFAULT_VERIFY_SSL': 'true'},
            'volumes': ['./secrets/password:/run/secrets/unifi_password:ro'], 'networks': ['metrics', 'access']},
            'prometheus': {'image': 'prometheus-pinned', 'volumes': ['data:/prometheus']},
            'grafana': {'image': 'grafana-pinned'}}, 'volumes': {'data': {}}, 'networks': {'metrics': {}, 'access': {}}}

    def validate(self, **change):
        args = dict(enabled=True, poller=True, verify=True, image=self.image,
                    url='https://controller.example.test', settings=self.settings)
        args.update(change)
        return guard.policy(**args)

    def test_disabled_legacy_and_complete_opt_in(self):
        self.assertTrue(guard.policy(False, False, False, '', '', {}))
        self.assertTrue(self.validate())

    def test_bad_settings_refused(self):
        for change in [{'verify': False}, {'poller': False}, {'image': 'tag:mutable'},
                       {'enabled': 'true'}, {'url': 'http://controller.example.test'},
                       {'url': 'https://user:secret@controller.example.test'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate(**change)
        for key, value in [('clock_skew_seconds', 1000), ('cache_entries', 1000),
                           ('cache_ttl_seconds', 9999), ('timeout_seconds', 100),
                           ('response_limit', 1000000), ('controller_address', '0.0.0.0'),
                           ('responder_address', 'host.example.test'),
                           ('responder_url', 'http://user:secret@ocsp.example.test/status')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(settings=dict(self.settings, **{key: value}))

    def test_semantic_patch_preserves_other_services_and_networks(self):
        original = copy.deepcopy(self.compose)
        patched = guard.compose_patch(original, self.image)
        for service in ['prometheus', 'grafana']:
            self.assertEqual(patched['services'][service], original['services'][service])
        for key in ['volumes', 'networks']:
            self.assertEqual(patched[key], original[key])
        self.assertEqual(self.compose, original)
        self.assertNotIn('ports', patched['services']['unifi-ap-counts'])
        self.assertTrue(guard.preserve(patched, True, self.image))
        self.assertEqual(guard.compose_patch(patched, self.image), patched)

    def test_installed_disable_partial_and_image_change_refused(self):
        patched = guard.compose_patch(self.compose, self.image)
        for enabled, image in [(False, self.image), (True, 'other-image')]:
            with self.assertRaises(ValueError):
                guard.preserve(patched, enabled, image)
        self.assertTrue(guard.preserve(patched, True, 'reviewed-new-image', self.image))
        del patched['services']['unifi-ap-counts']
        with self.assertRaises(ValueError):
            guard.preserve(patched, True, self.image)

    def test_insecure_pin_remote_and_mount_conflicts_refused(self):
        for key in ['UP_UNIFI_DEFAULT_CERT', 'UP_UNIFI_REMOTE_API_KEY']:
            compose = copy.deepcopy(self.compose)
            compose['services']['unifi-poller']['environment'][key] = 'unsupported'
            with self.assertRaises(ValueError):
                guard.compose_patch(compose, self.image)
        compose = copy.deepcopy(self.compose)
        compose['services']['unifi-poller']['volumes'].append('./elsewhere:/etc/iop-ocsp:rw')
        with self.assertRaises(ValueError):
            guard.compose_patch(compose, self.image)


if __name__ == '__main__':
    unittest.main()
