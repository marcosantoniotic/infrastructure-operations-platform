"""Fault injection at the real persistent journal boundary (no network)."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ocsp_durability', ROOT / 'roles/observability/files/unifi_ocsp.py')
ocsp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ocsp)


class DurabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.policy = object.__new__(ocsp.Policy)
        self.policy.state = Path(self.temp.name) / 'state.json'
        self.old = {'version': 1, 'revoked': [], 'cache': {}, 'last_clock': 0}
        self.new = dict(self.old, revoked=['confirmed-test-identity'])
        self.policy.state.write_text(json.dumps(self.old))

    def assert_no_temporary_files(self):
        self.assertEqual([p.name for p in self.policy.state.parent.iterdir()], ['state.json'])

    def test_real_save_and_restart_preserves_denial(self):
        self.policy.save(self.new)
        self.assertEqual(json.loads(self.policy.state.read_text()), self.new)
        self.assert_no_temporary_files()

    def test_file_sync_failure_keeps_old_state_and_raises(self):
        with patch.object(ocsp.os, 'fsync', side_effect=OSError('test fsync failure')):
            with self.assertRaises(OSError):
                self.policy.save(self.new)
        self.assertEqual(json.loads(self.policy.state.read_text()), self.old)
        self.assert_no_temporary_files()

    def test_replace_failure_keeps_old_state_and_raises(self):
        with patch.object(ocsp.os, 'replace', side_effect=OSError('test replace failure')):
            with self.assertRaises(OSError):
                self.policy.save(self.new)
        self.assertEqual(json.loads(self.policy.state.read_text()), self.old)
        self.assert_no_temporary_files()

    @unittest.skipUnless(os.name == 'posix', 'Linux directory durability boundary')
    def test_sync_order_and_directory_failure_cannot_acknowledge(self):
        events = []
        real_sync, real_replace = ocsp.os.fsync, ocsp.os.replace
        def sync(fd):
            events.append('sync')
            return real_sync(fd)
        def replace(src, dst):
            events.append('replace')
            return real_replace(src, dst)
        with patch.object(ocsp.os, 'fsync', side_effect=sync), patch.object(ocsp.os, 'replace', side_effect=replace):
            self.policy.save(self.new)
        self.assertEqual(events, ['sync', 'replace', 'sync'])
        with patch.object(ocsp.os, 'fsync', side_effect=[None, OSError('test directory sync failure')]):
            with self.assertRaises(OSError):
                self.policy.save(self.new)
        # Replacement may already be visible, but must never be reported durable.
        self.assertEqual(json.loads(self.policy.state.read_text()), self.new)
        self.assert_no_temporary_files()


if __name__ == '__main__':
    unittest.main()
