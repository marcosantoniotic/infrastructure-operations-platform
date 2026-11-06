"""Mandatory notification/ledger guards; in-memory API only, no environment.

Native reader acceptance alone does not cover these metadata drift cases.
No skip/xfail: rejection must occur before API or ledger writes.
"""
import copy
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

    def prepare(self, mode):
        self.setUp()
        if mode in ('enforce', 'rollback'):
            self.config.update(phase='enforce', cutover_approved=True)
        if mode == 'rollback':
            contracts.wsp.reconcile(self.api, self.config, self.ledger,
                                    apply=True, now=contracts.NOW)
            self.api.writes.clear()

    def refused(self, mode='observe'):
        before = copy.deepcopy(self.ledger)
        persisted = []
        with self.assertRaises(ValueError):
            contracts.wsp.reconcile(self.api, self.config, self.ledger,
                                    persisted.append, apply=mode != 'dry-run',
                                    rollback=mode == 'rollback', now=contracts.NOW)
        self.assertEqual(self.api.writes, [])
        self.assertEqual(persisted, [])
        self.assertEqual(self.ledger, before)

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

    def test_ticket_tags_on_owned_and_legacy_are_refused_in_every_phase(self):
        for mode in ('observe', 'dry-run', 'enforce', 'rollback'):
            for index in (0, 2):
                with self.subTest(mode=mode, index=index):
                    self.prepare(mode)
                    # Multiple values for the same tag must not hide eligibility.
                    self.api.triggers[index]['tags'].extend([
                        {'tag': 'glpi', 'value': 'other'},
                        {'tag': 'glpi', 'value': 'ticket'}])
                    self.refused(mode)

    def test_inherited_and_host_ticket_tags_also_block_rollback(self):
        for mode in ('observe', 'enforce', 'rollback'):
            for where in ('host', 'template'):
                with self.subTest(mode=mode, where=where):
                    self.prepare(mode)
                    tags = self.api.host['tags'] if where == 'host' else self.api.template_tags
                    tags.append({'tag': 'glpi', 'value': 'ticket'})
                    self.refused(mode)

    def test_deleted_or_changed_recorded_trigger_is_never_recreated(self):
        for mode in ('observe', 'enforce', 'rollback'):
            for change in ('deleted', 'id', 'name', 'owner-value', 'duplicate-owner'):
                with self.subTest(mode=mode, change=change):
                    self.prepare(mode)
                    row = self.api.triggers[2]
                    if change == 'deleted': self.api.triggers.pop(2)
                    elif change == 'id': row['triggerid'] = '99901'
                    elif change == 'name': row['description'] = 'External renamed trigger'
                    elif change == 'owner-value': row['tags'][0]['value'] = 'different-owner'
                    else: row['tags'].append(dict(contracts.wsp.OWNER))
                    self.refused(mode)

    def test_recorded_item_missing_or_retagged_is_not_recreated(self):
        for change in ('deleted', 'id', 'removed-owner', 'duplicate-owner'):
            with self.subTest(change=change):
                self.prepare('observe')
                row = self.api.items[2]
                if change == 'deleted': self.api.items.pop(2)
                elif change == 'id': row['itemid'] = '99902'
                elif change == 'removed-owner': row['tags'] = []
                else: row['tags'].append(dict(contracts.wsp.OWNER))
                self.refused()

    def test_initial_manual_name_collision_is_not_adopted_or_duplicated(self):
        self.api = contracts.FakeAPI(); self.config = contracts.config(); self.ledger = {}
        row = copy.deepcopy(contracts.wsp.definitions(self.config['targets'][0], self.config)[1][0])
        row.update(triggerid='99903', tags=[{'tag': 'local', 'value': 'keep'}])
        self.api.triggers.append(row)
        self.refused()

    def test_partial_recorded_creation_can_resume_without_replacing_ids(self):
        self.api = contracts.FakeAPI(); self.config = contracts.config(); self.ledger = {}
        original = self.api.call
        count = 0
        def interrupted(method, params):
            nonlocal count
            if method == 'trigger.create':
                count += 1
                if count == 4: raise RuntimeError('Synthetic interruption BEFORE creation')
            return original(method, params)
        self.api.call = interrupted
        with self.assertRaises(RuntimeError):
            contracts.wsp.reconcile(self.api, self.config, self.ledger,
                                    apply=True, now=contracts.NOW)
        ids = {name: tid for name, tid in self.ledger['hosts']['9001']['triggers'].items()}
        self.api.call = original; self.api.writes.clear()
        result = contracts.wsp.reconcile(self.api, self.config, self.ledger,
                                        apply=True, now=contracts.NOW)
        self.assertEqual(result['writes'], 7)
        for name, tid in ids.items():
            self.assertEqual(self.ledger['hosts']['9001']['triggers'][name], tid)

    def test_local_tags_and_unrelated_ticket_trigger_are_preserved(self):
        self.api.triggers[2]['tags'].append({'tag': 'local', 'value': 'keep'})
        unrelated = {'triggerid': '99904', 'description': 'Unrelated trigger',
                     'status': '0', 'tags': [{'tag': 'glpi', 'value': 'ticket'}]}
        self.api.triggers.append(copy.deepcopy(unrelated))
        self.config.update(phase='enforce', cutover_approved=True)
        result = contracts.wsp.reconcile(self.api, self.config, self.ledger,
                                        apply=True, now=contracts.NOW)
        self.assertEqual(result['writes'], 12)
        contracts.wsp.reconcile(self.api, self.config, self.ledger,
                                apply=True, rollback=True, now=contracts.NOW)
        self.assertEqual(self.api.triggers[-1], unrelated)
        self.assertIn({'tag': 'local', 'value': 'keep'}, self.api.triggers[2]['tags'])

    def test_final_read_barrier_catches_new_ticket_or_lost_owner(self):
        for change in ('ticket', 'lost-owner'):
            with self.subTest(change=change):
                self.prepare('enforce')
                original = self.api.call
                reads = 0
                def changed(method, params):
                    nonlocal reads
                    if method == 'trigger.get':
                        reads += 1
                        if reads == 2:
                            if change == 'ticket':
                                self.api.triggers[2]['tags'].append({'tag': 'glpi', 'value': 'ticket'})
                            else:
                                self.api.triggers[2]['tags'] = []
                    return original(method, params)
                self.api.call = changed
                self.refused('enforce')


if __name__ == '__main__':
    unittest.main()
