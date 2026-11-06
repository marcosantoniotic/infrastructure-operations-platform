"""Offline contracts only; not proof of Windows WMI/eventlog collection."""
import copy
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[2] / 'roles/windows_service_policy/files/windows_service_policy.py'
spec = importlib.util.spec_from_file_location('wsp', SOURCE)
wsp = importlib.util.module_from_spec(spec); spec.loader.exec_module(wsp)
NOW = 2000000000


def config():
    return {'enabled': True, 'phase': 'observe', 'cutover_approved': False, 'interval': 60,
            'fault_window': 600, 'stuck_window': 600, 'stale_window': 300,
            'targets': [{'hostid': '9001', 'host': 'synthetic-win-a', 'netbox_id': '77',
                         'object_type': 'virtualization.virtualmachine', 'services': [
                             {'name': 'AppXSvc', 'display_name': 'Synthetic AppX service', 'legacy_triggerid': '8001'},
                             {'name': 'InventorySvc', 'display_name': 'Synthetic inventory service', 'legacy_triggerid': '8002'}]}]}


class FakeAPI:
    def __init__(self):
        self.host = {'hostid': '9001', 'host': 'synthetic-win-a', 'status': '0', 'tls_accept': '2',
                     'tags': [{'tag': k, 'value': v} for k, v in {'source': 'netbox', 'netbox_id': '77', 'netbox_object_type': 'virtualization.virtualmachine', 'netbox_monitoring_profile': 'windows-active', 'local': 'keep'}.items()],
                     'parentTemplates': [{'templateid': '10351', 'name': 'Windows by Zabbix agent active'}]}
        self.items = []; self.triggers = []; self.writes = []; self.actions = []
        self.template_tags = []; self.nextid = 10000; self.source_history_count = 3
        self.history = {'7001': [42], '7002': [6]}
        for i, service in enumerate(config()['targets'][0]['services']):
            key = 'service.info["' + service['name'] + '",state]'
            self.items.append({'itemid': str(7001+i), 'key_': key, 'hostid': '9001', 'tags': [], 'history': '31d'})
            self.triggers.append({'triggerid': service['legacy_triggerid'], 'expression': f'min(/synthetic-win-a/{key},#3)<>0',
                                  'status': '0', 'flags': '4', 'tags': [], 'functions': [{'itemid': str(7001+i)}]})

    def call(self, method, params):
        if method == 'host.get': return [copy.deepcopy(self.host)] if params['hostids'] == ['9001'] else []
        if method == 'template.get': return [{'templateid': '10351', 'tags': self.template_tags, 'parentTemplates': []}]
        if method == 'action.get': return copy.deepcopy(self.actions)
        if method == 'item.get': return copy.deepcopy(self.items)
        if method == 'trigger.get': return copy.deepcopy(self.triggers)
        if method == 'history.get': return [{'clock':str(NOW-60*i)} for i in range(self.source_history_count)]
        assert method in {'item.create', 'trigger.create', 'trigger.update'}, method
        self.writes.append((method, copy.deepcopy(params)))
        if method == 'trigger.update':
            assert set(params) == {'triggerid', 'status'}
            row = next(t for t in self.triggers if t['triggerid'] == params['triggerid']); row['status'] = str(params['status'])
            return {'triggerids': [row['triggerid']]}
        self.nextid += 1; iid = str(self.nextid); row = copy.deepcopy(params)
        if method == 'item.create':
            row.update(itemid=iid, type=str(row['type']), value_type=str(row['value_type']), master_itemid=str(row.get('master_itemid','0')), status='0', state='0', lastclock=str(NOW), lastvalue='1' if row['key_'].endswith(',clean]') or row['key_'].endswith(',present]') else '0')
            self.items.append(row); return {'itemids': [iid]}
        row.update(triggerid=iid, status=str(row['status']), flags='0'); self.triggers.append(row); return {'triggerids': [iid]}


class ServicePolicyTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI(); self.config = config(); self.ledger = {}
        self.initial_host = copy.deepcopy(self.api.host); self.old_items = copy.deepcopy(self.api.items)
        self.old_history = copy.deepcopy(self.api.history)

    def run_policy(self, **kwargs):
        return wsp.reconcile(self.api, self.config, self.ledger, apply=True, now=NOW, **kwargs)

    def observe(self):
        self.run_policy(); self.api.writes.clear()

    def enforce(self):
        self.config.update(phase='enforce', cutover_approved=True)

    def test_disabled_no_api_and_no_changes(self):
        c = config(); c.update(enabled=False, targets=[])
        self.assertEqual(wsp.reconcile(None,c,{}), {'disabled':True,'changes':0,'writes':0})

    def test_dry_run_no_objects_or_ledger_written(self):
        r = wsp.reconcile(self.api,self.config,self.ledger,now=NOW)
        self.assertEqual(r['changes'],25); self.assertEqual(r['writes'],0); self.assertEqual(self.ledger,{})

    def test_observe_preserves_history_host_and_legacy(self):
        r = self.run_policy(); self.assertEqual(r['writes'],25)
        self.assertEqual(self.api.host,self.initial_host); self.assertEqual(self.api.items[:2],self.old_items)
        self.assertEqual(self.api.history,self.old_history)
        self.assertTrue(all(t['status']=='0' for t in self.api.triggers[:2]))
        self.assertTrue(all(t['status']=='1' for t in self.api.triggers[2:]))

    def test_observe_repeat_idempotent(self):
        self.observe(); self.assertEqual(self.run_policy()['writes'],0)

    def test_failure_recovery_requires_three_clean_running_observations(self):
        _,triggers=wsp.definitions(self.config['targets'][0],self.config)
        for service in ('AppXSvc','InventorySvc'):
            failure=next(t for t in triggers if t['description']==f'IOP WSP {service}: failure')
            self.assertIn(f'count(/synthetic-win-a/iop.wsp[{service},clean],#3,"eq",1)=3',failure['recovery_expression'])
            self.assertIn(f'count(/synthetic-win-a/iop.wsp[{service},state],#3,"eq",0)=3',failure['recovery_expression'])

    def test_cutover_repeats_and_rollback_keep_all_ids_and_data(self):
        self.observe(); ids=[i['itemid'] for i in self.api.items]; self.enforce()
        self.assertEqual(self.run_policy()['writes'],12); self.assertEqual(self.run_policy()['writes'],0)
        self.assertEqual(self.run_policy(rollback=True)['writes'],12)
        self.assertEqual(self.run_policy(rollback=True)['writes'],0)
        self.assertEqual(ids,[i['itemid'] for i in self.api.items]); self.assertEqual(self.old_history,self.api.history)
        self.assertTrue(all(t['status']=='0' for t in self.api.triggers[:2]))

    def test_no_cutover_without_approval(self):
        self.config['phase']='enforce'
        with self.assertRaises(ValueError):self.run_policy()
        self.assertFalse(self.api.writes)

    def test_no_cutover_before_observe(self):
        self.enforce()
        with self.assertRaises(ValueError):self.run_policy()
        self.assertFalse(self.api.writes)

    def test_stale_and_unsupported_samples_refuse_before_any_write(self):
        for field,value in [('lastclock','1'),('state','1')]:
            with self.subTest(field=field):
                self.setUp();self.observe();self.enforce();self.api.items[2][field]=value
                with self.assertRaises(ValueError):self.run_policy()
                self.assertFalse(self.api.writes)

    def test_unclean_cutover_refused(self):
        self.observe();self.enforce();next(i for i in self.api.items if i['key_'].endswith(',clean]'))['lastvalue']='0'
        with self.assertRaises(ValueError):self.run_policy()
        self.assertFalse(self.api.writes)

    def test_new_failure_at_cutover_refused(self):
        self.observe();self.enforce();next(i for i in self.api.items if i['key_'].startswith('eventlog.count['))['lastvalue']='1'
        with self.assertRaises(ValueError):self.run_policy()
        self.assertFalse(self.api.writes)

    def test_cutover_requires_history_not_only_a_fresh_lastvalue(self):
        self.observe();self.enforce();self.api.source_history_count=1
        with self.assertRaises(ValueError):self.run_policy()
        self.assertFalse(self.api.writes)

    def test_plaintext_and_wrong_profile_refused(self):
        for change in ['tls','profile']:
            with self.subTest(change=change):
                self.setUp()
                if change=='tls':self.api.host['tls_accept']='1'
                else:next(t for t in self.api.host['tags'] if t['tag']=='netbox_monitoring_profile')['value']='linux-active'
                with self.assertRaises(ValueError):self.run_policy()
                self.assertFalse(self.api.writes)

    def test_item_key_takeover_refused(self):
        definition=wsp.definitions(self.config['targets'][0],self.config)[0][0]
        self.api.items.append(dict(definition,itemid='9999'))
        with self.assertRaises(ValueError):self.run_policy()
        self.assertFalse(self.api.writes)

    def test_guards_scope_and_installed_timing(self):
        self.observe();self.config['interval']=30
        with self.assertRaises(ValueError):self.run_policy()
        self.assertFalse(self.api.writes)

    def test_disabled_installed_refused(self):
        self.observe();c=config();c.update(enabled=False,targets=[])
        with self.assertRaises(ValueError):wsp.reconcile(None,c,self.ledger)

    def test_outside_manual_trigger_changes_not_overwritten(self):
        self.observe();self.api.triggers[0]['status']='1'
        with self.assertRaises(ValueError):self.run_policy()
        self.assertFalse(self.api.writes)

    def test_all_targets_preflight_before_writes(self):
        other=copy.deepcopy(self.config['targets'][0]);other.update(hostid='9002',host='synthetic-win-b')
        for i,s in enumerate(other['services']):s['legacy_triggerid']=str(8101+i)
        self.config['targets'].append(other)
        with self.assertRaises(ValueError):self.run_policy()
        self.assertFalse(self.api.writes)

    def test_unknown_notification_route_refused(self):
        self.api.actions=[{'actionid':'1','status':'0','eventsource':'0','filter':{'evaltype':'0','conditions':[]}}]
        with self.assertRaises(ValueError):self.run_policy()
        self.assertFalse(self.api.writes)

    def test_inherited_ticket_tag_refused(self):
        self.api.template_tags=[{'tag':'glpi','value':'ticket'}]
        with self.assertRaises(ValueError):self.run_policy()
        self.assertFalse(self.api.writes)

    def test_retained_collector_keys_and_no_service_command(self):
        items,triggers=wsp.definitions(self.config['targets'][0],self.config)
        self.assertEqual(len(items),15);self.assertEqual(len(triggers),10)
        self.assertFalse(any('system.run' in i['key_'] or i['key_']=='service.discovery' for i in items))
        self.assertTrue(all('Service Control Manager' in i['key_'] and '7036' not in i['key_'] for i in items if i['key_'].startswith('eventlog.count[')))
        self.assertTrue(all(t['status']==1 and t['manual_close']==0 for t in triggers))

    def test_recovery_never_only_silence(self):
        _,triggers=wsp.definitions(self.config['targets'][0],self.config)
        for t in triggers:
            if t['description'].endswith(': failure'):
                self.assertIn('clean',t['recovery_expression']);self.assertIn('"eq",0)=3',t['recovery_expression'])
                self.assertIn('sum(',t['recovery_expression']);self.assertIn('nodata(',t['recovery_expression'])

    def test_schema_rejects_broad_scope_and_injection(self):
        for mutate in [lambda c:c['targets'][0].update(host='bad/host'),lambda c:c['targets'][0]['services'][0].update(name='RpcSs'),lambda c:c.update(stale_window=1),lambda c:c.update(enabled='true')]:
            c=config();mutate(c)
            with self.assertRaises(ValueError):wsp.validate(c)

    def test_native_item_parameter_escaping_is_not_json(self):
        self.assertEqual(wsp.quote(r'Service \(AppX\)'), '"Service \\(AppX\\)"')
        self.assertEqual(wsp.quote('Serviço "AppX"'), '"Serviço \\"AppX\\""')
        with self.assertRaises(ValueError):wsp.quote('bad\\')

    def test_partial_cutover_rollback_recovers_pending_status_without_delete(self):
        self.observe();self.enforce();original=self.api.call;updates=[]
        def fail(method,params):
            if method=='trigger.update':
                updates.append(params)
                if len(updates)==4:
                    original(method,params)
                    raise RuntimeError('Synthetic lost response AFTER committed update')
            return original(method,params)
        self.api.call=fail
        with self.assertRaises(RuntimeError):self.run_policy()
        self.assertIn('pending',self.ledger['hosts']['9001'])
        self.api.call=original;self.run_policy(rollback=True)
        self.assertTrue(all(t['status']=='0' for t in self.api.triggers[:2]))
        self.assertTrue(all(t['status']=='1' for t in self.api.triggers[2:]))
        self.assertEqual(self.old_history,self.api.history)


if __name__=='__main__':unittest.main()
