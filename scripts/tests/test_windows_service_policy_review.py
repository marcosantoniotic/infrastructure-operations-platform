"""Blocking draft regressions; in-memory API only, never an environment probe.

These contracts intentionally expose review findings until the policy is fixed.
Do not skip/xfail them to make a draft CI green. Native reader acceptance does
not cover these notification/ownership-drift cases.
"""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'wsp_contracts', Path(__file__).with_name('test_windows_service_policy.py'))
contracts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contracts)


class BlockingReviewContracts(unittest.TestCase):
    def setUp(self):
        self.api = contracts.FakeAPI()
        self.config = contracts.config()
        self.ledger = {}
        contracts.wsp.reconcile(self.api, self.config, self.ledger,
                                apply=True, now=contracts.NOW)
        self.api.writes.clear()

    def test_trigger_ticket_tag_must_refuse_cutover_before_writes(self):
        self.api.triggers[2]['tags'].append({'tag': 'glpi', 'value': 'ticket'})
        self.api.actions = [{
            'actionid': '1', 'status': '0', 'eventsource': '0',
            'filter': {'evaltype': '0', 'conditions': [{
                'conditiontype': '26', 'operator': '0',
                'value': 'glpi', 'value2': 'ticket'}]}}]
        self.config.update(phase='enforce', cutover_approved=True)
        with self.assertRaises(ValueError):
            contracts.wsp.reconcile(self.api, self.config, self.ledger,
                                    apply=True, now=contracts.NOW)
        self.assertEqual(self.api.writes, [])

    def test_recorded_trigger_losing_owner_tag_must_not_be_duplicated(self):
        original_id = self.api.triggers[2]['triggerid']
        self.api.triggers[2]['tags'] = [
            tag for tag in self.api.triggers[2]['tags']
            if tag['tag'] != contracts.wsp.OWNER['tag']]
        with self.assertRaises(ValueError):
            contracts.wsp.reconcile(self.api, self.config, self.ledger,
                                    apply=True, now=contracts.NOW)
        self.assertEqual(self.api.writes, [])
        self.assertEqual(self.ledger['hosts']['9001']['triggers'][
            self.api.triggers[2]['description']], original_id)


if __name__ == '__main__':
    unittest.main()
